"""
خدمة السلة — مصدر واحد للحقيقة في عمليات CartItem.

تفصل منطق الأعمال عن HTTP (session + request context)، فيبقى الـ blueprint
مسؤولاً عن الجلسة والاستجابات، وهذه الخدمة عن عمليات قاعدة البيانات
والتحقق من المخزون.
"""
from database import db
from models import CartItem, Product


class CartService:
    # ═══════════════════════════════════════════════════════════════
    # أدوات تحويل/تنظيف
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def sanitize_client_cart(local_cart):
        """
        تحويل dict قادم من العميل إلى {int(pid): int(qty)} مع فلترة القيم غير الصالحة.
        """
        clean = {}
        for pid_str, qty in (local_cart or {}).items():
            try:
                pid = int(pid_str)
                q = int(qty)
                if q >= 1:
                    clean[pid] = q
            except (ValueError, TypeError):
                continue
        return clean

    # ═══════════════════════════════════════════════════════════════
    # دمج سلة الجلسة مع قاعدة البيانات
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def merge_session_with_db(user_id, session_cart):
        """
        دمج سلة الجلسة مع سلة قاعدة البيانات.

        - تُحدَّث صفوف CartItem (insert/update) دون commit — المتصل يقرر.
        - تُعاد سلة موحّدة {str(pid): qty} جاهزة لوضعها في session.
        - إذا لم يكن user_id موجوداً، تُعاد session_cart كما هي.
        """
        if not user_id:
            return session_cart

        merged = {}
        for pid, qty in (session_cart or {}).items():
            try:
                merged[int(pid)] = int(qty)
            except (ValueError, TypeError):
                continue

        db_items = CartItem.query.filter_by(user_id=user_id).all()
        db_item_map = {item.product_id: item for item in db_items}

        for pid, item in db_item_map.items():
            merged[pid] = max(merged.get(pid, 0), item.quantity)

        if not merged:
            return {}

        product_map = {
            p.id: p for p in
            Product.query.filter(Product.id.in_(merged.keys())).all()
        }

        for product_id, qty in merged.items():
            product = product_map.get(product_id)
            if not product:
                continue
            new_qty = min(qty, product.stock_quantity)
            existing = db_item_map.get(product_id)
            if existing:
                existing.quantity = new_qty
            else:
                db.session.add(CartItem(
                    user_id=user_id,
                    product_id=product_id,
                    store_id=product.store_id,
                    quantity=new_qty
                ))

        return {
            str(pid): min(merged[pid], product_map[pid].stock_quantity)
            for pid in merged if pid in product_map
        }

    # ═══════════════════════════════════════════════════════════════
    # مزامنة كاملة من العميل (استبدال)
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def sync_from_client(user_id, local_cart):
        """
        استبدال سلة المستخدم في قاعدة البيانات بمحتوى local_cart.

        - يحذف كل CartItem قديم للمستخدم.
        - يُضيف الجديد مع تطبيق سقف المخزون.
        - يعيد {str(pid): qty} للسلة الناتجة.
        - لا يُنفّذ commit — المتصل يقرر.
        """
        CartItem.query.filter_by(user_id=user_id).delete()

        clean = CartService.sanitize_client_cart(local_cart)
        if not clean:
            return {}

        product_map = {
            p.id: p for p in
            Product.query.filter(Product.id.in_(clean.keys())).all()
        }

        new_cart = {}
        for pid, qty in clean.items():
            product = product_map.get(pid)
            if not product:
                continue
            final_qty = min(qty, product.stock_quantity)
            db.session.add(CartItem(
                user_id=user_id,
                product_id=pid,
                store_id=product.store_id,
                quantity=final_qty
            ))
            new_cart[str(pid)] = final_qty

        return new_cart

    # ═══════════════════════════════════════════════════════════════
    # عمليات عنصر واحد
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def add_to_db_cart(user_id, product, quantity):
        """
        إضافة/زيادة كمية في سلة المستخدم.
        يعيد السلة الكاملة بعد العملية {str(pid): qty}. يُنفّذ commit داخلياً.
        """
        existing = CartItem.query.filter_by(
            user_id=user_id, product_id=product.id
        ).first()
        if existing:
            existing.quantity = min(existing.quantity + quantity, product.stock_quantity)
        else:
            db.session.add(CartItem(
                user_id=user_id,
                product_id=product.id,
                store_id=product.store_id,
                quantity=min(quantity, product.stock_quantity)
            ))
        db.session.commit()

        db_items = CartItem.query.filter_by(user_id=user_id).all()
        return {str(item.product_id): item.quantity for item in db_items}

    @staticmethod
    def set_quantity(user_id, product, new_quantity):
        """
        تعيين كمية محددة (أو حذف إن كانت <= 0). يُنفّذ commit.
        - new_quantity < 1: حذف الصف.
        - new_quantity > stock: يُقصّ إلى stock.
        """
        if new_quantity < 1:
            CartService.remove_from_db_cart(user_id, product.id)
            return
        clamped_qty = min(new_quantity, product.stock_quantity)
        existing = CartItem.query.filter_by(
            user_id=user_id, product_id=product.id
        ).first()
        if existing:
            existing.quantity = clamped_qty
        else:
            db.session.add(CartItem(
                user_id=user_id,
                product_id=product.id,
                store_id=product.store_id,
                quantity=clamped_qty
            ))
        db.session.commit()

    @staticmethod
    def remove_from_db_cart(user_id, product_id):
        """حذف عنصر محدد. يُنفّذ commit."""
        CartItem.query.filter_by(
            user_id=user_id, product_id=product_id
        ).delete()
        db.session.commit()

    @staticmethod
    def remove_products_from_db_cart(user_id, product_ids):
        """حذف مجموعة عناصر دفعة واحدة (لا commit — المتصل يقرر)."""
        if not product_ids:
            return
        CartItem.query.filter(
            CartItem.user_id == user_id,
            CartItem.product_id.in_(product_ids)
        ).delete(synchronize_session=False)

    # ═══════════════════════════════════════════════════════════════
    # عمليات السلة كاملة
    # ═══════════════════════════════════════════════════════════════
    @staticmethod
    def clear_user_cart(user_id):
        """حذف كل عناصر سلة المستخدم. يُنفّذ commit."""
        CartItem.query.filter_by(user_id=user_id).delete()
        db.session.commit()

    @staticmethod
    def clear_store_cart(user_id, store_id):
        """
        حذف كل عناصر متجر محدد من سلة المستخدم. يُنفّذ commit.

        ملاحظة تقنية: SQLAlchemy لا يسمح بـ Query.delete() على استعلام
        يحتوي join() — لذلك نجلب معرّفات المنتجات أولاً في استعلام منفصل،
        ثم نحذف CartItem بـ IN على الجدول الواحد.
        """
        product_ids = [
            pid for (pid,) in
            db.session.query(Product.id).filter(Product.store_id == store_id).all()
        ]
        if product_ids:
            CartItem.query.filter(
                CartItem.user_id == user_id,
                CartItem.product_id.in_(product_ids)
            ).delete(synchronize_session=False)
        db.session.commit()

    @staticmethod
    def get_store_product_ids(store_id):
        """قائمة معرّفات منتجات المتجر (نصوص) — لتنظيف session cart."""
        return [
            str(pid) for (pid,) in
            db.session.query(Product.id).filter(Product.store_id == store_id).all()
        ]
