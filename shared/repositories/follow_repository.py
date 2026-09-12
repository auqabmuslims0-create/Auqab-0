"""
FollowRepository — التمثيل الفعلي لـ "المتابعة" في هذا المشروع.

الاستراتيجية المختارة: "المفضلة = المتابعة"
- عندما يضيف مستخدم متجراً إلى مفضلته (Favorite.store_id = store_id)، فهو "يتابعه".
- إشعارات "عرض جديد / ريل جديد" تُرسل لكل من أضاف المتجر إلى مفضلته.
- المفضلة على منتج محدد (Favorite.product_id) لا تُعتبر متابعة للمتجر.
"""
from database import db
from models import Favorite


class FollowRepository:
    @staticmethod
    def get_store_followers_ids(store_id):
        """إرجاع IDs المستخدمين الذين أضافوا المتجر إلى مفضلتهم (= يتابعونه)."""
        if not store_id:
            return []
        rows = (
            db.session.query(Favorite.user_id)
            .filter(Favorite.store_id == store_id)
            .distinct()
            .all()
        )
        return [r[0] for r in rows]

    @staticmethod
    def get_store_followers_count(store_id):
        """عدد متابعي المتجر (للعرض في الواجهة مستقبلاً)."""
        if not store_id:
            return 0
        return (
            db.session.query(Favorite.user_id)
            .filter(Favorite.store_id == store_id)
            .distinct()
            .count()
        )

    @staticmethod
    def is_following(user_id, store_id):
        """هل يتابع المستخدم هذا المتجر؟"""
        if not user_id or not store_id:
            return False
        return db.session.query(
            Favorite.query.filter_by(user_id=user_id, store_id=store_id).exists()
        ).scalar()

    @staticmethod
    def get_followed_stores_ids(user_id):
        """قائمة IDs المتاجر التي يتابعها المستخدم."""
        if not user_id:
            return []
        rows = (
            db.session.query(Favorite.store_id)
            .filter(Favorite.user_id == user_id, Favorite.store_id.isnot(None))
            .distinct()
            .all()
        )
        return [r[0] for r in rows]
