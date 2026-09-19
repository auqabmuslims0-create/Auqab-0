import os
import uuid
import re
import io
import subprocess
import tempfile
import shutil
from PIL import Image
from werkzeug.utils import secure_filename
from flask import current_app, request
from shared.time_utils import current_time
from database import db
from shared.validators import is_strong_password, is_valid_email, is_valid_phone_syrian


# ═══════════════════════════════════════════════════════════════
# A4: حماية من decompression bombs
# ═══════════════════════════════════════════════════════════════
# Pillow يطلق DecompressionBombWarning عند هذا الحد، و DecompressionBombError
# عند 2× الحد. بضبط 50M بكسل → الرفض الصارم عند 100M بكسل (= 10000×10000)
# وهو أكبر من أي صورة واقعية (8000×6000 = 48M).
Image.MAX_IMAGE_PIXELS = 50_000_000


# ========== دوال عامة ==========

def generate_public_id():
    """توليد معرف عام فريد للمستخدم."""
    import string
    import secrets
    from models import User
    chars = string.ascii_uppercase + string.digits
    while True:
        pid = f"A-{''.join(secrets.choice(chars) for _ in range(4))}-{''.join(secrets.choice(chars) for _ in range(4))}"
        if not User.query.filter_by(public_id=pid).first():
            return pid

def get_upload_path(filename):
    """تحويل اسم الملف المخزن إلى مسار مطلق (للملفات المحلية القديمة)."""
    if not filename:
        return None
    if filename.startswith('http'):
        return None
    if filename.startswith('uploads/'):
        return os.path.join(current_app.config['UPLOAD_FOLDER'], filename[len('uploads/'):])
    return os.path.join(current_app.config['UPLOAD_FOLDER'], filename)

def get_setting(key, default=None):
    """جلب قيمة إعداد من جدول الإعدادات."""
    from models import Setting
    setting = Setting.query.filter_by(key=key).first()
    return setting.value if setting else default

def set_setting(key, value):
    """تحديث أو إنشاء إعداد."""
    from models import Setting
    setting = Setting.query.filter_by(key=key).first()
    if setting:
        setting.value = value
    else:
        setting = Setting(key=key, value=value)
        db.session.add(setting)
    try:
        db.session.commit()
        return True
    except Exception:
        db.session.rollback()
        raise
    return True

def is_store_open(store):
    """التحقق من أن المتجر مفتوح الآن وفقًا لساعات العمل."""
    if not store.working_hours or '-' not in store.working_hours:
        return False
    try:
        parts = store.working_hours.split('-')
        if len(parts) != 2:
            return False
        open_time = parts[0].strip()
        close_time = parts[1].strip()

        def time_to_minutes(t):
            h, m = t.split(':')
            return int(h) * 60 + int(m)

        open_min = time_to_minutes(open_time)
        close_min = time_to_minutes(close_time)
        now = current_time()
        current_min = now.hour * 60 + now.minute

        if open_min <= close_min:
            return open_min <= current_min <= close_min
        else:
            return current_min >= open_min or current_min <= close_min
    except (ValueError, AttributeError):
        return False

def is_store_active(store):
    """التحقق من أن المتجر نشط ولديه اشتراك ساري المفعول."""
    from models import Subscription
    if store.subscription_status != 'active':
        return False
    paid_sub = Subscription.query.filter_by(store_id=store.id, status='paid') \
        .order_by(Subscription.end_date.desc()).first()
    if not paid_sub or paid_sub.end_date < current_time():
        return False
    return True

def safe_redirect_target(target):
    """التحقق من أن رابط إعادة التوجيه آمن."""
    if target and target.startswith('/') and not target.startswith('//'):
        return target
    return None

def safe_referrer():
    """إرجاع رابط الرجوع الآمن إذا كان من نفس الموقع."""
    from urllib.parse import urlparse
    referrer = request.referrer
    if not referrer:
        return None
    parsed = urlparse(referrer)
    if parsed.netloc == request.host or parsed.netloc == '':
        path = parsed.path
        if path.startswith('/') and not path.startswith('//'):
            if parsed.query:
                return f"{path}?{parsed.query}"
            return path
    return None

# ========== حفظ الملفات (محلي أو Cloudinary) ==========

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
ALLOWED_VIDEO_EXTENSIONS = {'mp4', 'mov', 'avi'}
MAX_IMAGE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_VIDEO_SIZE = 50 * 1024 * 1024  # 50MB


# ═══════════════════════════════════════════════════════════════
# A1: فحص magic bytes — لا نثق بالامتداد ولا بـ Content-Type
# ═══════════════════════════════════════════════════════════════
def _validate_image_magic(file):
    """
    التحقق من البايتات السحرية للصورة.
    يقرأ أول 12 بايت ثم يُعيد المؤشر إلى 0.
    يعيد True إذا كان التوقيع مطابقًا لـ JPEG/PNG/GIF/WebP.
    """
    try:
        header = file.read(12)
    except Exception:
        return False
    finally:
        try:
            file.seek(0)
        except Exception:
            pass

    if not header or len(header) < 8:
        return False
    # JPEG: FF D8 FF
    if header[:3] == b'\xff\xd8\xff':
        return True
    # PNG: 89 50 4E 47 0D 0A 1A 0A
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return True
    # GIF: GIF87a أو GIF89a
    if header[:6] in (b'GIF87a', b'GIF89a'):
        return True
    # WebP: RIFF .... WEBP
    if header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return True
    return False


def _validate_video_magic(file):
    """
    التحقق من البايتات السحرية للفيديو.
    - MP4/MOV: بايتات 4-8 == b'ftyp' (ISO Base Media).
    - AVI: RIFF ... AVI .
    """
    try:
        header = file.read(12)
    except Exception:
        return False
    finally:
        try:
            file.seek(0)
        except Exception:
            pass

    if not header or len(header) < 12:
        return False
    if header[4:8] == b'ftyp':
        return True
    if header[:4] == b'RIFF' and header[8:12] == b'AVI ':
        return True
    return False


# ═══════════════════════════════════════════════════════════════
# A2: _secure_file — امتداد + mimetype + magic bytes + الحجم
# ═══════════════════════════════════════════════════════════════
def _secure_file(file, allowed_extensions, max_size):
    if not file or not file.filename or file.filename == '':
        return None
    original_filename = file.filename
    if '.' in original_filename:
        ext = original_filename.rsplit('.', 1)[1].lower()
    else:
        ext = ''
    if ext not in allowed_extensions:
        return None
    mimetype = file.mimetype or ''
    if mimetype.startswith('image/') and ext not in ALLOWED_IMAGE_EXTENSIONS:
        return None
    if mimetype.startswith('video/') and ext not in ALLOWED_VIDEO_EXTENSIONS:
        return None
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)
    if size > max_size:
        return None

    # A2: الامتداد و Content-Type قابلان للتزوير من العميل. الفحص القاطع
    # هو محتوى الملف (magic bytes) — وإلا رفع مهاجم HTML باسم .jpg مع
    # Content-Type: image/jpeg.
    if ext in ALLOWED_IMAGE_EXTENSIONS:
        if not _validate_image_magic(file):
            return None
    elif ext in ALLOWED_VIDEO_EXTENSIONS:
        if not _validate_video_magic(file):
            return None

    return ext

def _is_cloudinary_enabled():
    """التحقق من تفعيل Cloudinary من إعدادات التطبيق."""
    return current_app.config.get('CLOUDINARY_ENABLED', False)

def _upload_to_cloudinary(file, resource_type='image', **kwargs):
    """رفع ملف إلى Cloudinary مع خيارات إضافية."""
    import cloudinary.uploader
    file.seek(0)
    options = {
        'resource_type': resource_type,
        'folder': 'husayniyyah_market',
        'use_filename': True,
        'unique_filename': True,
    }
    if 'format' in kwargs:
        options['format'] = kwargs.pop('format')
    options.update(kwargs)
    upload_result = cloudinary.uploader.upload(file, **options)
    return upload_result.get('secure_url')

def _delete_from_cloudinary(url):
    """حذف ملف من Cloudinary إذا كان الرابط من Cloudinary."""
    if not url or not url.startswith('http'):
        return
    pattern = r'https?://(?:res\.cloudinary\.com|res-[\w-]+\.cloudinary\.com)/([^/]+)/(image|video|raw)/upload/(?:v\d+/)?(.+?)(?:\.[a-zA-Z0-9]+)?$'
    match = re.match(pattern, url)
    if not match:
        return
    cloud_name = match.group(1)
    resource_type = match.group(2)
    public_id_with_ext = match.group(3)
    public_id = public_id_with_ext.rsplit('.', 1)[0] if '.' in public_id_with_ext else public_id_with_ext
    if not public_id:
        return
    try:
        import cloudinary.uploader
        cloudinary.uploader.destroy(public_id, resource_type=resource_type)
    except Exception as e:
        current_app.logger.warning(f'فشل حذف الملف من Cloudinary: {str(e)}')


# ═══════════════════════════════════════════════════════════════
# A5: delete_local_file — مع منع path traversal
# ═══════════════════════════════════════════════════════════════
def delete_local_file(url):
    """حذف ملف: إذا كان رابط Cloudinary نحذفه من Cloudinary، وإلا نحذف الملف المحلي."""
    if not url:
        return
    if url.startswith('http'):
        _delete_from_cloudinary(url)
        return

    if url.startswith('static/uploads/'):
        relative_path = url[len('static/'):]
    elif url.startswith('uploads/'):
        relative_path = url
    else:
        relative_path = os.path.join('uploads', url.lstrip('/'))

    file_path = os.path.join(current_app.static_folder, relative_path.replace('/', os.sep))

    # A5: منع path traversal — المسار الحقيقي يجب أن يكون داخل static/uploads.
    # مثال هجوم محتمل: url = 'uploads/../../../etc/passwd' → حذف خارج المشروع.
    # هذا دفاع في العمق — الـ URLs تأتي من كودنا، لكن نضمن السلامة حتى لو تسربت.
    try:
        real_target = os.path.realpath(file_path)
        real_base = os.path.realpath(current_app.static_folder)
    except Exception:
        return
    upload_root = os.path.join(real_base, 'uploads')
    if real_target != upload_root and not real_target.startswith(upload_root + os.sep):
        current_app.logger.warning(f'delete_local_file: رفض مسار غير آمن: {url}')
        return

    if os.path.exists(real_target):
        try:
            os.remove(real_target)
        except OSError:
            pass


def _compress_image(file, max_width=1200, max_height=1200, quality=80):
    """
    ضغط الصورة وتقليل حجمها.
    تعيد (bytes_io, output_ext).

    A3: عند فشل المعالجة نرفع ValueError بدل إرجاع البايتات الأصلية
    (كان يُخزِّن أي ملف خبيث تشوَّه بعد فشل Pillow).
    """
    try:
        img = Image.open(file)
        img_format = img.format

        if img_format == 'GIF':
            file.seek(0)
            output = io.BytesIO(file.read())
            output.seek(0)
            return output, 'gif'

        if img.mode in ('RGBA', 'LA', 'P'):
            if img.mode == 'P':
                img = img.convert('RGBA')
            background = Image.new('RGB', img.size, (255, 255, 255))
            background.paste(img, mask=img.split()[-1] if img.mode == 'RGBA' else None)
            img = background
        else:
            img = img.convert('RGB')

        img.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

        output = io.BytesIO()
        img.save(output, format='JPEG', quality=quality, optimize=True)
        output.seek(0)
        return output, 'jpg'

    except Exception as e:
        current_app.logger.warning(f'فشل ضغط الصورة: {str(e)}')
        # A3: بدل إرجاع البايتات الأصلية (سلوك قديم خطير) نرفع استثناء.
        raise ValueError('تعذر معالجة الصورة — قد تكون تالفة أو غير مدعومة')

def _compress_video(file, max_width=720, crf=32):
    """ضغط الفيديو باستخدام ffmpeg إذا كان متاحًا وبسرعة معقولة."""
    if not shutil.which('ffmpeg'):
        return None
    try:
        file.seek(0)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_input:
            file.save(temp_input.name)
            input_path = temp_input.name

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as temp_output:
            output_path = temp_output.name

        cmd = [
            'ffmpeg', '-i', input_path,
            '-vf', f'scale={max_width}:-2',
            '-c:v', 'libx264', '-crf', str(crf),
            '-preset', 'veryfast',
            '-c:a', 'aac', '-b:a', '96k',
            '-movflags', '+faststart',
            output_path,
            '-y'
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
        except subprocess.TimeoutExpired:
            current_app.logger.warning('ffmpeg استغرق أكثر من 60 ثانية، سيتم رفع الفيديو الأصلي')
            os.unlink(input_path)
            os.unlink(output_path)
            return None
        except subprocess.CalledProcessError:
            current_app.logger.warning('ffmpeg فشل، سيتم رفع الفيديو الأصلي')
            if os.path.exists(input_path):
                os.unlink(input_path)
            if os.path.exists(output_path):
                os.unlink(output_path)
            return None

        if os.path.getsize(output_path) < os.path.getsize(input_path):
            os.unlink(input_path)
            return output_path
        else:
            os.unlink(output_path)
            os.unlink(input_path)
            return None
    except Exception as e:
        current_app.logger.warning(f'فشل ضغط الفيديو: {str(e)}')
        for p in [input_path, output_path]:
            if p and os.path.exists(p):
                os.unlink(p)
        return None

def save_image(file, old_url=None):
    """حفظ صورة مع ضغطها ثم رفعها إلى Cloudinary أو تخزينها محليًا."""
    if not file or not file.filename:
        raise ValueError('لم يتم اختيار ملف')
    ext = _secure_file(file, ALLOWED_IMAGE_EXTENSIONS, MAX_IMAGE_SIZE)
    if not ext:
        raise ValueError('صيغة الملف غير مدعومة أو الحجم كبير جداً')
    try:
        compressed_file, output_ext = _compress_image(file)

        if _is_cloudinary_enabled():
            new_url = _upload_to_cloudinary(
                compressed_file,
                resource_type='image',
                format=output_ext
            )
            if new_url and old_url:
                delete_local_file(old_url)
            return new_url
        else:
            original_name = secure_filename(file.filename)
            base_name = os.path.splitext(original_name)[0]
            unique_name = f"{uuid.uuid4().hex}_{base_name}.{output_ext}"
            relative_dir = os.path.join('uploads', 'images')
            full_dir = os.path.join(current_app.static_folder, relative_dir)
            os.makedirs(full_dir, exist_ok=True)
            file_path = os.path.join(full_dir, unique_name)

            with open(file_path, 'wb') as f:
                f.write(compressed_file.read())

            new_url = os.path.join(relative_dir, unique_name).replace('\\', '/')
            if new_url and old_url:
                delete_local_file(old_url)
            return new_url
    except ValueError:
        raise
    except Exception as e:
        current_app.logger.error(f'save_image failed: {str(e)}')
        raise ValueError(f'فشل حفظ الصورة: {str(e)}')

def save_video(file, old_url=None):
    """حفظ فيديو مع ضغطه إن أمكن ثم رفعه إلى Cloudinary أو تخزينه محليًا."""
    if not file or not file.filename:
        raise ValueError('لم يتم اختيار ملف')
    ext = _secure_file(file, ALLOWED_VIDEO_EXTENSIONS, MAX_VIDEO_SIZE)
    if not ext:
        raise ValueError('صيغة الفيديو غير مدعومة أو الحجم كبير جداً')
    try:
        compressed_path = _compress_video(file)
        if _is_cloudinary_enabled():
            if compressed_path:
                with open(compressed_path, 'rb') as f:
                    new_url = _upload_to_cloudinary(f, resource_type='video', format='mp4')
                os.unlink(compressed_path)
            else:
                file.seek(0)
                new_url = _upload_to_cloudinary(
                    file,
                    resource_type='video',
                    quality='auto:good',
                    width=720,
                    crop='limit'
                )
            if new_url and old_url:
                delete_local_file(old_url)
            return new_url
        else:
            if compressed_path:
                filename = secure_filename(file.filename)
                base_name = os.path.splitext(filename)[0]
                unique_name = f"{uuid.uuid4().hex}_{base_name}.mp4"
                relative_dir = os.path.join('uploads', 'videos')
                full_dir = os.path.join(current_app.static_folder, relative_dir)
                os.makedirs(full_dir, exist_ok=True)
                file_path = os.path.join(full_dir, unique_name)
                shutil.move(compressed_path, file_path)
                new_url = os.path.join(relative_dir, unique_name).replace('\\', '/')
            else:
                file.seek(0)
                filename = secure_filename(file.filename)
                unique_name = f"{uuid.uuid4().hex}_{filename}"
                relative_dir = os.path.join('uploads', 'videos')
                full_dir = os.path.join(current_app.static_folder, relative_dir)
                os.makedirs(full_dir, exist_ok=True)
                file_path = os.path.join(full_dir, unique_name)
                file.save(file_path)
                new_url = os.path.join(relative_dir, unique_name).replace('\\', '/')
            if new_url and old_url:
                delete_local_file(old_url)
            return new_url
    except ValueError:
        raise
    except Exception as e:
        current_app.logger.error(f'save_video failed: {str(e)}')
        raise ValueError(f'فشل حفظ الفيديو: {str(e)}')
