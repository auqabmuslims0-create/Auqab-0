from flask import Blueprint, render_template, request, jsonify, session, url_for, make_response
from shared.decorators import api_login_required
from shared.services.reel_service import ReelService
from shared.repositories.reel_repository import DEFAULT_SORT, SORT_OPTIONS

reels_bp = Blueprint('reels', __name__)


def _wants_json():
    return (request.args.get('format') == 'json'
            or request.headers.get('X-Requested-With') == 'XMLHttpRequest')


@reels_bp.route('/reels')
def reels_page():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    user_id = session.get('user_id')

    sort = request.args.get('sort', DEFAULT_SORT)
    if sort not in SORT_OPTIONS:
        sort = DEFAULT_SORT

    reels, pagination, user_reaction_map = ReelService.get_feed(
        page=page, per_page=per_page, user_id=user_id, sort_key=sort
    )

    # ===== استجابة AJAX: HTML fragment للريلز التالية =====
    if _wants_json():
        html = render_template('customer/_reel_slides.html',
                               reels=reels,
                               user_reaction_map=user_reaction_map)
        resp = make_response(jsonify({
            'html': html,
            'has_next': pagination.has_next,
            'next_page': pagination.next_num if pagination.has_next else None,
        }))
        resp.headers['Cache-Control'] = 'private, max-age=0, no-store'
        return resp
    # =====================================================

    sort_urls = {key: url_for('reels.reels_page', sort=key) for key in SORT_OPTIONS}

    return render_template('customer/reels.html',
                           reels=reels,
                           pagination=pagination,
                           user_reaction_map=user_reaction_map,
                           current_sort=sort,
                           sort_urls=sort_urls)


@reels_bp.route('/api/reels')
def api_get_reels():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    user_id = session.get('user_id')

    sort = request.args.get('sort', DEFAULT_SORT)
    if sort not in SORT_OPTIONS:
        sort = DEFAULT_SORT

    reels, pagination, user_reaction_map = ReelService.get_feed(
        page=page, per_page=per_page, user_id=user_id, sort_key=sort
    )
    reels_data = [ReelService.serialize_reel(reel) for reel in reels]
    return jsonify({
        'reels': reels_data,
        'has_next': pagination.has_next,
        'next_page': pagination.next_num if pagination.has_next else None,
        'sort': sort,
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
