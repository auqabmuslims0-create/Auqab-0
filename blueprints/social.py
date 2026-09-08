from flask import Blueprint, request, jsonify, session
from database import db
from shared.decorators import api_login_required
from models import Product, ProductComment, ProductReaction
from sqlalchemy.orm import joinedload

social_bp = Blueprint('social', __name__)

def serialize_comment(c):
    return {
        'id': c.id,
        'user_id': c.user_id,
        'username': c.user.username if c.user else 'مستخدم',
        'text': c.text,
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else None
    }

@social_bp.route('/api/products/<int:product_id>/comments', methods=['GET'])
def get_comments(product_id):
    product = Product.query.options(
        joinedload(Product.comments).joinedload(ProductComment.user)
    ).filter_by(id=product_id).first_or_404()
    comments = sorted(product.comments, key=lambda x: x.created_at, reverse=True)
    return jsonify({'comments': [serialize_comment(c) for c in comments]}), 200

@social_bp.route('/api/products/<int:product_id>/comments', methods=['POST'])
@api_login_required
def add_comment(product_id):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'message': 'التعليق لا يمكن أن يكون فارغاً'}), 400

    product = Product.query.get_or_404(product_id)
    comment = ProductComment(product_id=product.id, user_id=session['user_id'], text=text)
    try:
        db.session.add(comment)
        db.session.commit()
        return jsonify({'message': 'تم إضافة التعليق', 'comment': serialize_comment(comment)}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء إضافة التعليق'}), 500

@social_bp.route('/api/comments/<int:comment_id>', methods=['PUT'])
@api_login_required
def edit_comment(comment_id):
    comment = ProductComment.query.get_or_404(comment_id)
    if comment.user_id != session['user_id']:
        return jsonify({'message': 'غير مسموح'}), 403

    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'message': 'التعليق لا يمكن أن يكون فارغاً'}), 400

    comment.text = text
    try:
        db.session.commit()
        return jsonify({'message': 'تم تعديل التعليق', 'comment': serialize_comment(comment)}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء تعديل التعليق'}), 500

@social_bp.route('/api/comments/<int:comment_id>', methods=['DELETE'])
@api_login_required
def delete_comment(comment_id):
    comment = ProductComment.query.get_or_404(comment_id)
    if comment.user_id != session['user_id']:
        return jsonify({'message': 'غير مسموح'}), 403
    try:
        db.session.delete(comment)
        db.session.commit()
        return jsonify({'message': 'تم حذف التعليق'}), 200
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء حذف التعليق'}), 500

@social_bp.route('/api/products/<int:product_id>/reaction', methods=['POST'])
@api_login_required
def react(product_id):
    data = request.get_json(silent=True) or {}
    reaction_type = (data.get('reaction_type') or '').strip()
    if reaction_type not in ['like', 'love', 'wow', 'sad', 'angry']:
        return jsonify({'message': 'نوع التفاعل غير صالح'}), 400

    product = Product.query.get_or_404(product_id)
    user_id = session['user_id']

    try:
        existing = ProductReaction.query.filter_by(product_id=product.id, user_id=user_id).first()
        if existing and existing.reaction_type == reaction_type:
            db.session.delete(existing)
            db.session.commit()
            return jsonify({'message': 'تم إزالة التفاعل'}), 200
        elif existing:
            existing.reaction_type = reaction_type
            db.session.commit()
            return jsonify({'message': 'تم تحديث التفاعل'}), 200
        else:
            reaction = ProductReaction(product_id=product.id, user_id=user_id, reaction_type=reaction_type)
            db.session.add(reaction)
            db.session.commit()
            return jsonify({'message': 'تم إضافة التفاعل'}), 201
    except Exception:
        db.session.rollback()
        return jsonify({'message': 'حدث خطأ أثناء تحديث التفاعل'}), 500
