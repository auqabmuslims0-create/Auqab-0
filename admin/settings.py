from flask import render_template, request, redirect, url_for, flash
from shared.utils import get_setting, set_setting
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/settings', methods=['GET', 'POST'])
@role_required('admin')
def admin_settings():
    if request.method == 'POST':
        subscription_price = request.form.get('subscription_price', '').strip()
        subscription_duration_days = request.form.get('subscription_duration_days', '').strip()
        wallet_number = request.form.get('wallet_number', '').strip()
        delivery_fee = request.form.get('delivery_fee', '').strip()

        if subscription_price:
            try:
                price = float(subscription_price)
                if price <= 0:
                    flash('يجب أن يكون سعر الاشتراك أكبر من صفر', 'error')
                else:
                    set_setting('subscription_price', str(price))
                    flash('تم تحديث سعر الاشتراك', 'success')
            except ValueError:
                flash('قيمة غير صالحة لسعر الاشتراك', 'error')

        if subscription_duration_days:
            try:
                duration = int(subscription_duration_days)
                if duration <= 0:
                    flash('يجب أن تكون مدة الاشتراك أكبر من صفر', 'error')
                else:
                    set_setting('subscription_duration_days', str(duration))
                    flash('تم تحديث مدة الاشتراك', 'success')
            except ValueError:
                flash('قيمة غير صالحة لمدة الاشتراك', 'error')

        if wallet_number:
            set_setting('wallet_number', wallet_number)
            flash('تم تحديث رقم المحفظة', 'success')

        if delivery_fee:
            try:
                fee = float(delivery_fee)
                if fee < 0:
                    flash('رسوم التوصيل لا يمكن أن تكون سالبة', 'error')
                else:
                    set_setting('delivery_fee', str(fee))
                    flash('تم تحديث رسوم التوصيل', 'success')
            except ValueError:
                flash('قيمة غير صالحة لرسوم التوصيل', 'error')

        return redirect(url_for('admin.admin_settings'))

    current_price = get_setting('subscription_price', '500')
    try:
        current_price = float(current_price)
    except (TypeError, ValueError):
        current_price = 500.0

    duration_days = get_setting('subscription_duration_days', '30')
    try:
        duration_days = int(duration_days)
    except (TypeError, ValueError):
        duration_days = 30

    wallet_number = get_setting('wallet_number', '0995680223')

    delivery_fee = get_setting('delivery_fee', '100')
    try:
        delivery_fee = float(delivery_fee)
    except (TypeError, ValueError):
        delivery_fee = 100.0

    return render_template('admin/admin_settings.html',
                           subscription_price=current_price,
                           subscription_duration_days=duration_days,
                           wallet_number=wallet_number,
                           delivery_fee=delivery_fee)
