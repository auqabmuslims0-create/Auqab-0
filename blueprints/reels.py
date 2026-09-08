from flask import Blueprint, render_template, request, jsonify, session
from shared.decorators import api_login_required
from shared.services.reel_service import ReelService

reels_bp = Blueprint('reels', __name__)

@reels_bp.route('/reels')
def reels_page():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    user_id = session.get('user_id')
    reels, pagination, user_reaction_map = ReelService.get_feed(page=page, per_page=per_page, user_id=user_id)
    return render_template('customer/reels.html',
                           reels=reels,
                           pagination=pagination,
                           user_reaction_map=user_reaction_map)

@reels_bp.route('/api/reels')
def api_get_reels():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    user_id = session.get('user_id')
    reels, pagination, user_reaction_map = ReelService.get_feed(page=page, per_page=per_page, user_id=user_id)
    reels_data = [ReelService.serialize_reel(reel) for reel in reels]
    return jsonify({
        'reels': reels_data,
        'has_next': pagination.has_next,
        'next_page': pagination.next_num if pagination.has_next else None,
    })

@reels_bp.route('/api/reels/<int:reel_id>/view', methods=['POST'])
def api_record_view(reel_id):
    ReelService.increment_view(reel_id)
    return jsonify({'message': 'تم تسجيل المشاهدة'}), 200

@reels_bp.route('/api/reels/<int:reel_id>/reaction', methods=['POST'])
@api_login_required
def api_toggle_reaction(reel_id):
    data = request.get_json(silent=True) or {}
    reaction_type = (data.get('reaction_type') or '').strip()
    valid_types = ['like', 'love', 'wow', 'sad', 'angry']
    if reaction_type not in valid_types:
        return jsonify({'message': 'نوع التفاعل غير صالح'}), 400
    result = ReelService.toggle_reaction(reel_id, session['user_id'], reaction_type)
    return jsonify({'message': 'تم تحديث التفاعل', 'result': result}), 200

@reels_bp.route('/api/reels/<int:reel_id>/comments', methods=['GET'])
def api_get_comments(reel_id):
    reel = ReelService.get_reel_by_id(reel_id)
    if not reel:
        return jsonify({'message': 'الريل غير موجود'}), 404
    comments = sorted(reel.comments, key=lambda c: c.created_at, reverse=True)
    comments_data = [{
        'id': c.id,
        'user_id': c.user_id,
        'username': c.user.username if c.user else 'مستخدم',
        'text': c.text,
        'created_at': c.created_at.strftime('%Y-%m-%d %H:%M') if c.created_at else None
    } for c in comments]
    return jsonify({'comments': comments_data}), 200

@reels_bp.route('/api/reels/<int:reel_id>/comments', methods=['POST'])
@api_login_required
def api_add_comment(reel_id):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'message': 'التعليق لا يمكن أن يكون فارغاً'}), 400
    comment = ReelService.add_comment(reel_id, session['user_id'], text)
    return jsonify({
        'message': 'تم إضافة التعليق',
        'comment': {
            'id': comment.id,
            'user_id': comment.user_id,
            'username': comment.user.username if comment.user else 'مستخدم',
            'text': comment.text,
            'created_at': comment.created_at.strftime('%Y-%m-%d %H:%M')
        }
    }), 201

@reels_bp.route('/api/reels/comments/<int:comment_id>', methods=['PUT'])
@api_login_required
def api_edit_comment(comment_id):
    data = request.get_json(silent=True) or {}
    text = (data.get('text') or '').strip()
    if not text:
        return jsonify({'message': 'التعليق لا يمكن أن يكون فارغاً'}), 400
    comment = ReelService.update_comment(comment_id, session['user_id'], text)
    if comment is None:
        return jsonify({'message': 'غير مسموح أو التعليق غير موجود'}), 403
    return jsonify({'message': 'تم تعديل التعليق'}), 200

@reels_bp.route('/api/reels/comments/<int:comment_id>', methods=['DELETE'])
@api_login_required
def api_delete_comment(comment_id):
    success = ReelService.delete_comment(comment_id, session['user_id'])
    if not success:
        return jsonify({'message': 'غير مسموح أو التعليق غير موجود'}), 403
    return jsonify({'message': 'تم حذف التعليق'}), 200
