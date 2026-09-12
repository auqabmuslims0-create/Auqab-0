from flask import render_template, request, session, redirect, url_for, flash
from datetime import timedelta
from collections import defaultdict
from database import db
from models import User, Store, Product, Order, OrderItem
from sqlalchemy import func
from shared.time_utils import current_time
from shared.decorators import role_required
from . import store_bp


RANGE_OPTIONS = {
    '7': 7,
    '30': 30,
    '90': 90,
    'all': None,
}

RANGE_LABELS = {
    '7': 'آخر 7 أيام',
    '30': 'آخر 30 يوم',
    '90': 'آخر 90 يوم',
    'all': 'كل الفترات',
}


@store_bp.route('/store/stats')
@role_required('owner')
def store_stats():
    user = db.session.get(User, session['user_id'])
    if not user:
        return redirect(url_for('auth.login'))

    all_stores = Store.query.filter_by(owner_id=user.id).all()
    if not all_stores:
        flash('لا يوجد لديك متاجر بعد', 'info')
        return redirect(url_for('store.my_stores'))

    # فلتر متجر معين (اختياري)
    store_filter = request.args.get('store_id', type=int)
    if store_filter:
        stores = [s for s in all_stores if s.id == store_filter]
        if not stores:
            flash('المتجر غير موجود', 'error')
            return redirect(url_for('store.store_stats'))
    else:
        stores = all_stores

    store_ids = [s.id for s in stores]

    # النطاق الزمني
    range_key = request.args.get('range', '30')
    if range_key not in RANGE_OPTIONS:
        range_key = '30'
    days = RANGE_OPTIONS[range_key]

    now = current_time()
    start_date = now - timedelta(days=days) if days else None

    # ====== الطلبات في النطاق ======
    orders_query = Order.query.filter(
        Order.store_id.in_(store_ids),
        Order.status != 'cancelled',
    )
    if start_date:
        orders_query = orders_query.filter(Order.created_at >= start_date)
    orders = orders_query.all()

    # ====== KPIs ======
    total_revenue = sum(o.total or 0 for o in orders)
    orders_count = len(orders)
    avg_order = (total_revenue / orders_count) if orders_count else 0
    active_products_count = Product.query.filter(
        Product.store_id.in_(store_ids)
    ).count()
    total_views = db.session.query(func.sum(Product.views)).filter(
        Product.store_id.in_(store_ids)
    ).scalar() or 0

    # ====== مبيعات يومية (Line chart) ======
    daily_map = defaultdict(lambda: {'revenue': 0.0, 'orders': 0})
    for o in orders:
        if not o.created_at:
            continue
        day = o.created_at.date()
        daily_map[day]['revenue'] += o.total or 0
        daily_map[day]['orders'] += 1

    daily_labels_dates = sorted(daily_map.keys())
    daily_labels = [d.strftime('%m-%d') for d in daily_labels_dates]
    daily_revenue = [round(daily_map[d]['revenue'], 2) for d in daily_labels_dates]
    daily_orders = [daily_map[d]['orders'] for d in daily_labels_dates]

    # ====== أفضل أيام الأسبوع (Bar chart) ======
    # Python weekday(): Mon=0 ... Sun=6
    # نبدأ بالسبت لأن بداية الأسبوع عادةً السبت
    weekday_order = [5, 6, 0, 1, 2, 3, 4]  # Sat, Sun, Mon, Tue, Wed, Thu, Fri
    weekday_names = {
        5: 'السبت', 6: 'الأحد', 0: 'الاثنين',
        1: 'الثلاثاء', 2: 'الأربعاء', 3: 'الخميس', 4: 'الجمعة',
    }
    weekday_stats = {i: {'revenue': 0.0, 'orders': 0} for i in weekday_order}
    for o in orders:
        if not o.created_at:
            continue
        wd = o.created_at.weekday()
        if wd in weekday_stats:
            weekday_stats[wd]['revenue'] += o.total or 0
            weekday_stats[wd]['orders'] += 1

    weekday_labels = [weekday_names[i] for i in weekday_order]
    weekday_revenue = [round(weekday_stats[i]['revenue'], 2) for i in weekday_order]
    weekday_orders = [weekday_stats[i]['orders'] for i in weekday_order]

    # ====== Top 10 الأكثر مبيعاً ======
    top_sellers_query = db.session.query(
        Product.id,
        Product.name,
        Product.main_image,
        Product.price,
        func.sum(OrderItem.quantity).label('total_sold'),
        func.sum(OrderItem.quantity * OrderItem.price).label('total_revenue'),
    ).join(OrderItem, OrderItem.product_id == Product.id) \
     .join(Order, Order.id == OrderItem.order_id) \
     .filter(
        Order.store_id.in_(store_ids),
        Order.status != 'cancelled',
     )
    if start_date:
        top_sellers_query = top_sellers_query.filter(Order.created_at >= start_date)
    top_sellers = top_sellers_query \
        .group_by(Product.id) \
        .order_by(func.sum(OrderItem.quantity).desc()) \
        .limit(10).all()

    # ====== Top 10 الأكثر مشاهدة ======
    top_viewed = Product.query.filter(
        Product.store_id.in_(store_ids)
    ).order_by(Product.views.desc()).limit(10).all()

    return render_template('store_owner/store_stats.html',
                           stores=stores,
                           all_stores=all_stores,
                           selected_store_id=store_filter,
                           range_key=range_key,
                           range_label=RANGE_LABELS[range_key],
                           days=days,
                           total_revenue=total_revenue,
                           orders_count=orders_count,
                           avg_order=avg_order,
                           active_products_count=active_products_count,
                           total_views=total_views,
                           # Line
                           daily_labels=daily_labels,
                           daily_revenue=daily_revenue,
                           daily_orders=daily_orders,
                           # Bar
                           weekday_labels=weekday_labels,
                           weekday_revenue=weekday_revenue,
                           weekday_orders=weekday_orders,
                           # Tables
                           top_sellers=top_sellers,
                           top_viewed=top_viewed)
