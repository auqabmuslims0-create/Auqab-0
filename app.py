import sys
import os
import secrets
import time
import signal
from datetime import timedelta
from urllib.parse import urlparse, urlunparse
from dotenv import load_dotenv

# إضافة مسار المشروع إلى sys.path لضمان العثور على الوحدات
sys.path.insert(0, os.path.dirname(__file__))

from flask import Flask, render_template, request, redirect, url_for, session, flash, abort, g
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix
from database import db
from flask_migrate import Migrate
import models
from werkzeug.security import generate_password_hash
from flask_wtf.csrf import CSRFProtect

load_dotenv()

from auth import auth_bp
from admin import admin_bp
from blueprints.api import api_bp
from blueprints.social import social_bp
from store_owner import store_bp
from blueprints.delivery import delivery_bp

from customer.market import market_bp
from blueprints.reels import reels_bp
from customer.stores import stores_bp
from customer.offers import offers_bp
from customer.services import services_bp
from customer.account import account_bp
from customer.cart import cart_bp

from notifications import notifications_bp

app = Flask(__name__)
app.config['WTF_CSRF_SSL_STRICT'] = False

# تفعيل ProxyFix إذا كنا خلف بروكسي (مثل nginx) وتم تفعيل المتغير
if os.environ.get('TRUST_PROXY_HEADERS', '0') == '1':
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config['RATELIMIT_STORAGE_URI'] = 'memory://'
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["1000 per day", "100 per hour"],
    enabled=not app.debug
)

app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('FLASK_DEBUG', 'False').lower() != 'true'
app.config['SESSION_COOKIE_DOMAIN'] = None
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['PERMANENT_SESSION_LIFETIME'] = 7 * 24 * 60 * 60  # أسبوع
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

csp_policy = (
    "default-src 'self'; "
    "img-src 'self' data: https:; "
    "style-src 'self' 'unsafe-inline' https://unpkg.com; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "font-src 'self'; "
    "connect-src 'self' https://*.tile.openstreetmap.org https://router.project-osrm.org https://server.arcgisonline.com ; "
    "media-src 'self' https:; "   # ← تم التعديل: السماح بتحميل الفيديو من أي مصدر https
    "frame-src 'self'"
)
Talisman(app, content_security_policy=csp_policy, force_https=os.environ.get('FLASK_DEBUG', 'False').lower() != 'true')

# تفعيل CSRF
csrf = CSRFProtect(app)
# استثناء جميع الـ Blueprints التي تحتوي API routes
for bp in [api_bp, social_bp, reels_bp, delivery_bp, notifications_bp]:
    csrf.exempt(bp)

def get_secret_key():
    key = os.environ.get('SECRET_KEY')
    if key:
        return key
    if os.environ.get('FLASK_DEBUG', 'False').lower() == 'true':
        key_file = os.path.join(app.instance_path, '.secret_key')
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                return f.read().strip()
        key = secrets.token_hex(32)
        os.makedirs(app.instance_path, exist_ok=True)
        with open(key_file, 'w') as f:
            f.write(key)
        os.chmod(key_file, 0o600)
        return key
    raise RuntimeError('SECRET_KEY must be set in production environment')

app.config['SECRET_KEY'] = get_secret_key()

def get_jwt_secret_key():
    key = os.environ.get('JWT_SECRET_KEY')
    if key:
        return key
    if os.environ.get('FLASK_DEBUG', 'False').lower() == 'true':
        key_file = os.path.join(app.instance_path, '.jwt_secret_key')
        if os.path.exists(key_file):
            with open(key_file, 'r') as f:
                return f.read().strip()
        key = secrets.token_hex(32)
        os.makedirs(app.instance_path, exist_ok=True)
        with open(key_file, 'w') as f:
            f.write(key)
        os.chmod(key_file, 0o600)
        return key
    raise RuntimeError('JWT_SECRET_KEY must be set in production environment')

app.config['JWT_SECRET_KEY'] = get_jwt_secret_key()

# ====== معالجة DATABASE_URL بشكل آمن ======
database_url = os.environ.get('DATABASE_URL')

if database_url:
    database_url = database_url.strip()
    # تحويل postgres:// إلى postgresql:// (لتوافق SQLAlchemy)
    if database_url.startswith('postgres://'):
        database_url = database_url.replace('postgres://', 'postgresql://', 1)
else:
    database_url = 'sqlite:///' + os.path.join(os.path.dirname(__file__), 'husayniyyah.db')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(app.root_path, 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 15 * 1024 * 1024  # 15MB

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# ====== إعداد Cloudinary (اختياري) ======
cloudinary_enabled = os.environ.get('CLOUDINARY_CLOUD_NAME') and os.environ.get('CLOUDINARY_API_KEY') and os.environ.get('CLOUDINARY_API_SECRET')
if cloudinary_enabled:
    import cloudinary
    import cloudinary.uploader
    import cloudinary.api
    cloudinary.config(
        cloud_name=os.environ.get('CLOUDINARY_CLOUD_NAME'),
        api_key=os.environ.get('CLOUDINARY_API_KEY'),
        api_secret=os.environ.get('CLOUDINARY_API_SECRET'),
        secure=True
    )
    app.config['CLOUDINARY_ENABLED'] = True
else:
    app.config['CLOUDINARY_ENABLED'] = False

db.init_app(app)
migrate = Migrate(app, db)

with app.app_context():
    db.create_all()

# تسجيل Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(store_bp)
app.register_blueprint(delivery_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(api_bp, url_prefix='/api')
app.register_blueprint(social_bp)

app.register_blueprint(market_bp)
app.register_blueprint(reels_bp)
app.register_blueprint(stores_bp)
app.register_blueprint(offers_bp)
app.register_blueprint(services_bp)
app.register_blueprint(account_bp)
app.register_blueprint(cart_bp)
app.register_blueprint(notifications_bp)

@app.cli.command("create-admin")
def create_admin_command():
    """إنشاء المدير الافتراضي إذا لم يكن موجوداً."""
    ensure_admin()

def ensure_admin():
    with app.app_context():
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_phone = os.environ.get('ADMIN_PHONE')
        admin_password = os.environ.get('ADMIN_PASSWORD')
        if not all([admin_username, admin_email, admin_phone, admin_password]):
            app.logger.warning('لم يتم توفير بيانات المدير عبر .env، تخطي الإنشاء التلقائي.')
            return

        admin = models.User.query.filter_by(role='admin').first()
        if not admin:
            admin = models.User(
                username=admin_username,
                email=admin_email,
                phone=admin_phone,
                password_hash=generate_password_hash(admin_password),
                role='admin',
                is_active=True,
                public_id=secrets.token_hex(4).upper()
            )
            db.session.add(admin)
            db.session.commit()
            print("تم إنشاء المدير الافتراضي.")
        else:
            print("المدير موجود بالفعل.")

@app.before_request
def before_request_checks():
    g.user = None
    if 'user_id' in session:
        g.user = db.session.get(models.User, session['user_id'])

    if request.path.startswith('/api/') or request.endpoint is None:
        return

    if request.path == '/.well-known/assetlinks.json':
        return

    public_endpoints = [
        'auth.login', 'auth.register', 'auth.forgot_password', 'auth.confirm_identity',
        'auth.reset_password', 'auth.show_public_id', 'static',
        'market.home', 'market.market', 'market.search', 'market.search_suggestions',
        'stores.stores_page', 'stores.store_public', 'stores.product_public',
        'offers.offers_page', 'reels.reels_page', 'services.services_page', 'services.contact',
        'onboarding'
    ]
    if g.user is None:
        if request.endpoint not in public_endpoints:
            flash('يجب تسجيل الدخول أولاً')
            return redirect(url_for('auth.login'))

_notifications_cache = {}
_offers_cache = {}
CACHE_TIMEOUT = 30

@app.context_processor
def inject_notifications_count():
    if request.path.startswith('/api/') or request.path.startswith('/static/'):
        return dict(unread_notifications=0)
    if g.user is None:
        return dict(unread_notifications=0)

    user_id = g.user.id
    current_time = time.time()
    cached = _notifications_cache.get(user_id)
    if cached and (current_time - cached['timestamp'] < CACHE_TIMEOUT):
        return dict(unread_notifications=cached['count'])

    from shared.services.notification_service import NotificationService
    unread_count = NotificationService.get_unread_count(user_id)
    _notifications_cache[user_id] = {'count': unread_count, 'timestamp': current_time}
    return dict(unread_notifications=unread_count)

@app.context_processor
def inject_offers_count():
    if request.endpoint not in ['market.market', 'offers.offers_page', 'stores.stores_page']:
        return dict(offers_count=0)

    current_time = time.time()
    cached = _offers_cache.get('global')
    if cached and (current_time - cached['timestamp'] < CACHE_TIMEOUT):
        return dict(offers_count=cached['count'])

    offer_count = models.Product.query.filter_by(is_offer=True).count()
    _offers_cache['global'] = {'count': offer_count, 'timestamp': current_time}
    return dict(offers_count=offer_count)

@app.context_processor
def inject_current_user():
    return dict(current_user=g.user)

@app.context_processor
def inject_csrf_token():
    from flask_wtf.csrf import generate_csrf
    return dict(csrf_token=generate_csrf())

@app.context_processor
def inject_nav_items():
    """توليد عناصر القائمة الجانبية بناءً على دور المستخدم والصفحة الحالية."""
    user = g.user
    endpoint = request.endpoint

    if request.path.startswith('/api/') or request.path.startswith('/static/') or endpoint is None:
        return dict(nav_items=[])

    nav_items = []

    if user is None:
        nav_items.append({'type': 'link', 'url': url_for('auth.login'), 'label': 'تسجيل الدخول', 'icon': 'bi-box-arrow-in-right', 'active': endpoint == 'auth.login'})
        nav_items.append({'type': 'link', 'url': url_for('services.services_page'), 'label': 'حول / خدمات', 'icon': 'bi-info-circle', 'active': endpoint == 'services.services_page'})
        return dict(nav_items=nav_items)

    if user.role == 'admin':
        nav_items.append({'type': 'link', 'url': url_for('admin.admin_dashboard'), 'label': 'لوحة المدير', 'icon': 'bi-speedometer2', 'active': endpoint == 'admin.admin_dashboard'})
        nav_items.append({'type': 'divider'})
        nav_items.append({'type': 'link', 'url': url_for('notifications.notifications'), 'label': 'الإشعارات', 'icon': 'bi-bell', 'badge': g.get('unread_notifications', 0), 'active': endpoint == 'notifications.notifications'})
        nav_items.append({'type': 'link', 'url': url_for('auth.account'), 'label': 'الإعدادات', 'icon': 'bi-gear', 'active': endpoint == 'auth.account'})
    elif user.role == 'owner':
        nav_items.append({'type': 'link', 'url': url_for('store.my_stores'), 'label': 'متاجري', 'icon': 'bi-shop', 'active': endpoint == 'store.my_stores'})
        nav_items.append({'type': 'link', 'url': url_for('market.market'), 'label': 'السوق', 'icon': 'bi-shop', 'active': endpoint == 'market.market'})
        nav_items.append({'type': 'divider'})
        nav_items.append({'type': 'link', 'url': url_for('notifications.notifications'), 'label': 'الإشعارات', 'icon': 'bi-bell', 'badge': g.get('unread_notifications', 0), 'active': endpoint == 'notifications.notifications'})
        nav_items.append({'type': 'link', 'url': url_for('auth.account'), 'label': 'الإعدادات', 'icon': 'bi-gear', 'active': endpoint == 'auth.account'})
    elif user.role == 'delivery':
        nav_items.append({'type': 'link', 'url': url_for('delivery.delivery_dashboard'), 'label': 'لوحة المندوب', 'icon': 'bi-truck', 'active': endpoint == 'delivery.delivery_dashboard'})
        nav_items.append({'type': 'divider'})
        nav_items.append({'type': 'link', 'url': url_for('notifications.notifications'), 'label': 'الإشعارات', 'icon': 'bi-bell', 'badge': g.get('unread_notifications', 0), 'active': endpoint == 'notifications.notifications'})
        nav_items.append({'type': 'link', 'url': url_for('auth.account'), 'label': 'الإعدادات', 'icon': 'bi-gear', 'active': endpoint == 'auth.account'})
    elif user.role == 'customer':
        nav_items.append({'type': 'link', 'url': url_for('market.market'), 'label': 'السوق', 'icon': 'bi-shop', 'active': endpoint == 'market.market'})
        nav_items.append({'type': 'link', 'url': url_for('cart.cart'), 'label': 'سلة المشتريات', 'icon': 'bi-cart', 'active': endpoint == 'cart.cart'})
        nav_items.append({'type': 'link', 'url': url_for('account.favorites'), 'label': 'المفضلة', 'icon': 'bi-heart', 'active': endpoint == 'account.favorites'})
        nav_items.append({'type': 'link', 'url': url_for('notifications.notifications'), 'label': 'الإشعارات', 'icon': 'bi-bell', 'badge': g.get('unread_notifications', 0), 'active': endpoint == 'notifications.notifications'})
        nav_items.append({'type': 'link', 'url': url_for('auth.account'), 'label': 'الإعدادات', 'icon': 'bi-gear', 'active': endpoint == 'auth.account'})
        nav_items.append({'type': 'link', 'url': url_for('services.services_page'), 'label': 'حول / خدمات', 'icon': 'bi-info-circle', 'active': endpoint == 'services.services_page'})
    else:
        nav_items.append({'type': 'link', 'url': url_for('auth.account'), 'label': 'الإعدادات', 'icon': 'bi-gear', 'active': endpoint == 'auth.account'})

    nav_items.append({'type': 'divider'})
    nav_items.append({'type': 'button', 'id': 'sidebarThemeToggle', 'label': 'الوضع الداكن', 'icon': 'bi-moon-stars'})
    nav_items.append({'type': 'link', 'url': url_for('auth.logout'), 'label': 'تسجيل الخروج', 'icon': 'bi-box-arrow-left', 'active': False})

    return dict(nav_items=nav_items)

@app.context_processor
def inject_show_bottom_nav():
    """تحديد إظهار الشريط السفلي حسب الدور والصفحة."""
    user = g.user
    endpoint = request.endpoint

    if request.path.startswith('/api/') or request.path.startswith('/static/') or endpoint is None:
        return dict(show_bottom_nav=False)

    allowed_customer_endpoints = [
        'market.market',
        'reels.reels_page',
        'cart.cart',
        'offers.offers_page',
        'stores.stores_page',
        'stores.store_public',
        'stores.product_public',
        'notifications.notifications',
        'account.favorites'
    ]

    public_endpoints = [
        'market.market', 'reels.reels_page', 'offers.offers_page', 'stores.stores_page',
        'stores.store_public', 'stores.product_public', 'services.services_page'
    ]

    show = False
    if user:
        if user.role == 'customer' and endpoint in allowed_customer_endpoints:
            show = True
        elif user.role == 'owner' and endpoint == 'market.market':
            show = True
    else:
        if endpoint in public_endpoints:
            show = True

    return dict(show_bottom_nav=show)

@app.template_filter('format_price')
def format_price(value):
    try:
        return f"{float(value):,.0f}"
    except (ValueError, TypeError):
        return value

@app.template_filter('get_image_url')
def get_image_url(filename):
    if not filename:
        return ''
    if filename.startswith('http'):
        return filename
    if filename.startswith('static/'):
        return url_for('static', filename=filename[7:])
    if filename.startswith('uploads/'):
        return url_for('static', filename=filename)
    return url_for('static', filename='uploads/' + filename)

@app.route('/sw.js')
def service_worker():
    response = app.send_static_file('sw.js')
    response.headers['Content-Type'] = 'application/javascript'
    return response

@app.route('/onboarding')
def onboarding():
    return render_template('onboarding.html')

@app.errorhandler(403)
def forbidden(e):
    return render_template('shared/error.html', code=403, message='غير مسموح بالوصول إلى هذه الصفحة'), 403

@app.errorhandler(404)
def page_not_found(e):
    return render_template('shared/error.html', code=404, message='الصفحة غير موجودة'), 404

@app.errorhandler(500)
def internal_error(e):
    app.logger.exception('حدث خطأ 500')
    return render_template('shared/error.html', code=500, message='حدث خطأ داخلي في الخادم، يرجى المحاولة لاحقاً'), 500

@app.route('/.well-known/assetlinks.json')
def assetlinks():
    return app.send_static_file('.well-known/assetlinks.json')

def _handle_sigterm(signum, frame):
    from scheduler import shutdown_scheduler
    shutdown_scheduler()
    sys.exit(0)

if __name__ == '__main__':
    ensure_admin()

    from scheduler import init_scheduler
    init_scheduler(app)

    signal.signal(signal.SIGTERM, _handle_sigterm)
    signal.signal(signal.SIGINT, _handle_sigterm)

    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    port = int(os.environ.get('PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=debug_mode)
