from flask import render_template, request, redirect, url_for, flash
from shared.services.payment_service import PaymentService
from shared.decorators import role_required
from . import admin_bp

@admin_bp.route('/admin/payments')
@role_required('admin')
def admin_payments():
    status = request.args.get('status', '').strip()
    method = request.args.get('method', '').strip()
    page = request.args.get('page', 1, type=int)
    per_page = 20

    payments_pagination = PaymentService.get_all_payments(
        status=status if status else None,
        method=method if method else None,
        page=page,
        per_page=per_page
    )

    return render_template('admin/admin_payments.html', payments=payments_pagination.items,
                           pagination=payments_pagination, status=status, method=method)

@admin_bp.route('/admin/payments/<int:payment_id>/status', methods=['POST'])
@role_required('admin')
def admin_update_payment_status(payment_id):
    new_status = request.form.get('new_status')
    if new_status not in ['paid', 'failed', 'refunded', 'pending']:
        flash('حالة غير صالحة', 'error')
        return redirect(url_for('admin.admin_payments'))

    success, msg = PaymentService.update_payment_status(payment_id, new_status)
    flash(msg, 'success' if success else 'error')
    return redirect(url_for('admin.admin_payments'))
