from flask import render_template, request, redirect, url_for, session, flash
from sqlalchemy import func, and_, or_
from database import db
from models import User, ChatMessage
from shared.services.notification_service import NotificationService
from shared.decorators import role_required
from . import admin_bp
from datetime import datetime

@admin_bp.route('/admin/chats')
@role_required('admin')
def admin_chats():
    admin_user = db.session.get(User, session['user_id'])

    all_messages = ChatMessage.query.filter(
        (ChatMessage.sender_id == admin_user.id) | (ChatMessage.receiver_id == admin_user.id)
    ).all()

    user_ids = set()
    for msg in all_messages:
        if msg.sender_id != admin_user.id:
            user_ids.add(msg.sender_id)
        if msg.receiver_id != admin_user.id:
            user_ids.add(msg.receiver_id)

    users = User.query.filter(User.id.in_(user_ids)).all() if user_ids else []

    last_message_time = {}
    for msg in all_messages:
        other_id = msg.sender_id if msg.sender_id != admin_user.id else msg.receiver_id
        if other_id not in last_message_time or msg.created_at > last_message_time[other_id]:
            last_message_time[other_id] = msg.created_at

    users.sort(key=lambda u: last_message_time.get(u.id, datetime.min), reverse=True)

    unread_counts = {}
    if users:
        unread_counts_query = db.session.query(
            ChatMessage.sender_id,
            func.count(ChatMessage.id)
        ).filter(
            ChatMessage.receiver_id == admin_user.id,
            ChatMessage.is_read == False
        ).group_by(ChatMessage.sender_id).all()
        unread_counts = dict(unread_counts_query)

    return render_template('admin/admin_chats.html', users=users, unread_counts=unread_counts)

@admin_bp.route('/admin/chats/<int:user_id>')
@role_required('admin')
def admin_chat_view(user_id):
    admin_user = db.session.get(User, session['user_id'])
    target_user = User.query.get_or_404(user_id)

    messages = ChatMessage.query.filter(
        or_(
            and_(ChatMessage.sender_id == user_id, ChatMessage.receiver_id == admin_user.id),
            and_(ChatMessage.sender_id == admin_user.id, ChatMessage.receiver_id == user_id)
        )
    ).order_by(ChatMessage.created_at.asc()).all()

    for msg in messages:
        if msg.sender_id == user_id and not msg.is_read:
            msg.is_read = True
    db.session.commit()

    return render_template('admin/admin_chat_view.html', messages=messages, target_user=target_user, admin_id=admin_user.id)

@admin_bp.route('/admin/chats/send', methods=['POST'])
@role_required('admin')
def admin_send_message():
    admin_user = db.session.get(User, session['user_id'])

    user_id = request.form.get('user_id', type=int)
    message = request.form.get('message', '').strip()
    if not user_id or not message:
        flash('المستخدم أو الرسالة غير صحيحة', 'error')
        return redirect(url_for('admin.admin_chats'))

    msg = ChatMessage(
        sender_id=admin_user.id,
        receiver_id=user_id,
        message=message,
        is_read=False
    )
    db.session.add(msg)
    try:
        db.session.commit()
        NotificationService.send_to_user(
            user_id=user_id,
            title='رسالة جديدة من الدعم',
            message=message,
            link=url_for('services.support'),
            type_=NotificationService.TYPE_MESSAGE
        )
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('حدث خطأ أثناء إرسال الرسالة', 'error')
    return redirect(url_for('admin.admin_chat_view', user_id=user_id))
