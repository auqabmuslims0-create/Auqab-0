"""
اختبارات أمان رفع الملفات (A1–A7).

تغطي:
- magic bytes detection لـ JPEG/PNG/GIF/WebP/MP4/AVI.
- رفض الملفات النصية بامتداد صورة.
- رفض الملفات التي لا تُعالجها Pillow (بدل تخزين البايتات الأصلية).
- منع path traversal في delete_local_file.
- Rate limit على مسارات الرفع.
"""
import io
import os

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from database import db
from shared.utils import (
    _validate_image_magic,
    _validate_video_magic,
    save_image,
    save_video,
    delete_local_file,
)


# ═══════════════════════════════════════════════════════════════
# أدوات: توليد ملفات صالحة/خبيثة
# ═══════════════════════════════════════════════════════════════
def _make_jpeg_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), color='red').save(buf, 'JPEG')
    buf.seek(0)
    return buf.getvalue()


def _make_png_bytes():
    buf = io.BytesIO()
    Image.new('RGBA', (20, 20), color=(255, 0, 0, 128)).save(buf, 'PNG')
    buf.seek(0)
    return buf.getvalue()


def _make_gif_bytes():
    buf = io.BytesIO()
    Image.new('P', (20, 20)).save(buf, 'GIF')
    buf.seek(0)
    return buf.getvalue()


def _make_webp_bytes():
    buf = io.BytesIO()
    Image.new('RGB', (20, 20), color='blue').save(buf, 'WEBP')
    buf.seek(0)
    return buf.getvalue()


def _make_fake_mp4_bytes():
    """ملف بأول 4 بايتات حجم ثم 'ftyp' ثم brand — توقيع ISO Base Media."""
    return b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 200


def _make_fake_avi_bytes():
    """RIFF + 4 بايت حجم + 'AVI ' + باقي المحتوى."""
    return b'RIFF\x00\x00\x00\x00AVI ' + b'\x00' * 200


def _make_fs(content, filename, content_type):
    return FileStorage(
        stream=io.BytesIO(content),
        filename=filename,
        content_type=content_type,
    )


@pytest.fixture
def temp_static_folder(app, tmp_path, monkeypatch):
    """
    يُوجّه static_folder إلى مجلد مؤقت — يمنع تلويث المشروع بملفات الاختبار.
    ينشئ uploads/images و uploads/videos داخله.
    """
    original = app.static_folder
    monkeypatch.setattr(app, 'static_folder', str(tmp_path))
    os.makedirs(os.path.join(str(tmp_path), 'uploads', 'images'), exist_ok=True)
    os.makedirs(os.path.join(str(tmp_path), 'uploads', 'videos'), exist_ok=True)
    yield tmp_path
    # monkeypatch يعيد القيمة تلقائيًا


# ═══════════════════════════════════════════════════════════════
# A1: magic bytes detection (unit)
# ═══════════════════════════════════════════════════════════════
def test_image_magic_accepts_jpeg():
    assert _validate_image_magic(io.BytesIO(_make_jpeg_bytes())) is True


def test_image_magic_accepts_png():
    assert _validate_image_magic(io.BytesIO(_make_png_bytes())) is True


def test_image_magic_accepts_gif():
    assert _validate_image_magic(io.BytesIO(_make_gif_bytes())) is True


def test_image_magic_accepts_webp():
    assert _validate_image_magic(io.BytesIO(_make_webp_bytes())) is True


def test_image_magic_rejects_text():
    assert _validate_image_magic(io.BytesIO(b'Hello, not an image!')) is False


def test_image_magic_rejects_html():
    assert _validate_image_magic(io.BytesIO(b'<html><body>x</body></html>')) is False


def test_image_magic_rejects_empty():
    assert _validate_image_magic(io.BytesIO(b'')) is False


def test_video_magic_accepts_mp4():
    assert _validate_video_magic(io.BytesIO(_make_fake_mp4_bytes())) is True


def test_video_magic_accepts_avi():
    assert _validate_video_magic(io.BytesIO(_make_fake_avi_bytes())) is True


def test_video_magic_rejects_text():
    assert _validate_video_magic(io.BytesIO(b'Not a video at all!')) is False


# ═══════════════════════════════════════════════════════════════
# A2: _secure_file يرفض الملفات المزيفة
# ═══════════════════════════════════════════════════════════════
def test_save_image_rejects_fake_jpeg(app, temp_static_folder):
    """نص بامتداد .jpg + Content-Type صورة → يجب أن يُرفض."""
    with app.app_context():
        fs = _make_fs(b'This is not an image, just text', 'fake.jpg', 'image/jpeg')
        with pytest.raises(ValueError, match='صيغة'):
            save_image(fs)


def test_save_image_rejects_html_with_jpg_ext(app, temp_static_folder):
    with app.app_context():
        fs = _make_fs(b'<html>evil</html>', 'evil.jpg', 'image/jpeg')
        with pytest.raises(ValueError, match='صيغة'):
            save_image(fs)


def test_save_image_rejects_disallowed_extension(app, temp_static_folder):
    """امتداد غير مسموح (svg) — يُرفض من فحص الامتداد."""
    with app.app_context():
        fs = _make_fs(b'<svg></svg>', 'image.svg', 'image/svg+xml')
        with pytest.raises(ValueError, match='صيغة'):
            save_image(fs)


def test_save_image_accepts_real_jpeg(app, temp_static_folder):
    with app.app_context():
        fs = _make_fs(_make_jpeg_bytes(), 'real.jpg', 'image/jpeg')
        result = save_image(fs)
        assert result is not None
        assert 'uploads' in result


def test_save_image_accepts_real_png(app, temp_static_folder):
    with app.app_context():
        fs = _make_fs(_make_png_bytes(), 'real.png', 'image/png')
        result = save_image(fs)
        assert result is not None


# ═══════════════════════════════════════════════════════════════
# A3: fallback → raise (لا تخزين ملفات خبيثة عند فشل Pillow)
# ═══════════════════════════════════════════════════════════════
def test_save_image_raises_on_corrupted_image(app, temp_static_folder, monkeypatch):
    """
    صورة صحيحة البايتات السحرية لكن محتواها تالف → Pillow يفشل →
    يجب أن نرفع استثناء بدل تخزين البايتات الأصلية.
    """
    # نبني JPEG صحيح، ثم نُشوّه داخله (بعد magic bytes) — Pillow سيفشل
    valid = bytearray(_make_jpeg_bytes())
    # نخرّب كل شيء بعد أول 12 بايت
    for i in range(12, min(200, len(valid))):
        valid[i] = 0x00
    corrupted = bytes(valid)

    with app.app_context():
        fs = _make_fs(corrupted, 'corrupt.jpg', 'image/jpeg')
        with pytest.raises(ValueError, match='تعذر معالجة|فشل حفظ'):
            save_image(fs)


# ═══════════════════════════════════════════════════════════════
# A5: delete_local_file يرفض path traversal
# ═══════════════════════════════════════════════════════════════
def test_delete_local_file_ignores_path_traversal(app, temp_static_folder):
    """محاولة حذف خارج static/uploads → يتجاهل بصمت."""
    with app.app_context():
        # ملف في المجلد المؤقت لكن خارج uploads/
        outside = os.path.join(str(temp_static_folder), 'outside.txt')
        with open(outside, 'w') as f:
            f.write('do not delete')

        # محاولة استهدافه عبر path traversal
        delete_local_file('uploads/../outside.txt')

        # الملف يجب أن يبقى
        assert os.path.exists(outside), 'path traversal نجح — ثغرة!'


def test_delete_local_file_deletes_inside_uploads(app, temp_static_folder):
    """حذف ملف داخل uploads/images يعمل بشكل طبيعي."""
    with app.app_context():
        target_dir = os.path.join(str(temp_static_folder), 'uploads', 'images')
        target = os.path.join(target_dir, 'to_delete.jpg')
        with open(target, 'w') as f:
            f.write('x')

        delete_local_file('uploads/images/to_delete.jpg')
        assert not os.path.exists(target)


def test_delete_local_file_ignores_nonexistent(app, temp_static_folder):
    """لا خطأ عند حذف ملف غير موجود."""
    with app.app_context():
        # لا استثناء
        delete_local_file('uploads/images/never_existed.jpg')


# ═══════════════════════════════════════════════════════════════
# A6: rate limit على API الرفع
# ═══════════════════════════════════════════════════════════════
def _jwt_token(app, user_id):
    with app.app_context():
        from blueprints.api.helpers import encode_auth_token
        return encode_auth_token(user_id)


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def test_upload_rate_limit_returns_429_after_20(
    client, app, make_user, make_active_store, temp_static_folder
):
    """21 رفع متتالي من نفس IP → الرفع 21 يجب أن يُرفض بـ 429."""
    # إعادة تصفير العدّاد لضمان بداية نظيفة
    from blueprints.api.stores import _upload_attempts
    _upload_attempts.clear()

    owner = make_user(username='rl_owner', role='owner')
    s = make_active_store(owner_id=owner['id'])
    token = _jwt_token(app, owner['id'])

    jpeg = _make_jpeg_bytes()

    # 20 رفع ناجح
    for i in range(20):
        data = {'files': (io.BytesIO(jpeg), f'img_{i}.jpg')}
        r = client.post(
            f'/api/stores/{s["id"]}/upload-images',
            data=data,
            content_type='multipart/form-data',
            headers=_auth(token),
        )
        assert r.status_code == 200, f'رفع #{i+1} فشل: {r.status_code} {r.get_data(as_text=True)[:200]}'

    # الرفع 21 → 429
    data = {'files': (io.BytesIO(jpeg), 'img_21.jpg')}
    r = client.post(
        f'/api/stores/{s["id"]}/upload-images',
        data=data,
        content_type='multipart/form-data',
        headers=_auth(token),
    )
    assert r.status_code == 429
    body = r.get_json()
    assert 'حد الرفع' in body['message']
