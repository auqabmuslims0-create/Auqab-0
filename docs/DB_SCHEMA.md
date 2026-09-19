# Database Schema — سوق الحسينية

## Stack

- ORM: SQLAlchemy 2.x (Flask-SQLAlchemy)
- Migrations: Flask-Migrate (Alembic)
- Prod: PostgreSQL 14+ (Railway)
- Dev/Test: SQLite 3

## الجداول (17)

### users

- id: Integer PK
- username: String(80) UNIQUE INDEX
- email: String(120) UNIQUE INDEX
- phone: String(20) — بصيغة +963XXXXXXXXX
- password_hash: String(200) — werkzeug (scrypt)
- avatar: String(300)
- bio: Text
- role: String(20) INDEX — admin/owner/customer/delivery
- is_active: Boolean
- is_available: Boolean — للمندوبين
- dark_mode: Boolean
- public_id: String(20) UNIQUE — A-XXXX-XXXX
- shift_start_time / shift_end_time: Time — للمندوبين
- max_active_orders: Integer — للمندوبين
- created_at: DateTime

Relationships: stores, orders, delivery_orders, reviews, favorites,
notifications, subscriptions, cart_items, payments, push_subscriptions,
reels_reactions, product_comments.

### stores

- id: Integer PK
- owner_id: FK users.id NOT NULL
- name: String(100) INDEX
- description: Text
- logo_url: String(300)
- phone / address: String
- working_hours: String(100) — "HH:MM - HH:MM"
- latitude / longitude: Float
- has_delivery: Boolean
- subscription_status: String(20) INDEX — pending/active/suspended/cancelled/expired
- subscription_expiry: DateTime
- custom_subscription_price: Float — override من admin
- custom_subscription_duration_days: Integer
- subscription_grace_days: Integer — أيام سماح بعد الانتهاء
- subscription_notes: Text
- auto_renew: Boolean NOT NULL
- pending_deletion_at: DateTime — حذف مؤجل 48 ساعة
- created_at: DateTime

Check: subscription_status IN (pending, active, suspended, cancelled, expired).

### categories

تصنيف داخل متجر. parent_id لدعم الهرمية. مرتبط بـ store_id.

### products

- store_id: FK stores.id NOT NULL INDEX
- category_id: FK categories.id NULL
- name: String(120) INDEX
- product_code: String(50)
- description: Text
- price: Float NOT NULL
- is_offer: Boolean INDEX
- offer_price / original_price: Float NULL
- offer_description: Text
- stock_quantity: Integer
- options: Text (JSON نصي)
- main_image / sub_images / video: String
- views: Integer INDEX
- hide_price: Boolean NOT NULL — حصرًا من المتجر
- created_at: DateTime INDEX

Properties: effective_price (offer_price إن وُجد)، images (main+sub مجمّعة).
Indexes: (store_id, created_at), (is_offer, created_at), (store_id, is_offer).

### orders

- customer_id: FK users.id NOT NULL INDEX
- store_id: FK stores.id NOT NULL INDEX
- delivery_person_id: FK users.id NULL INDEX
- status: String(20) INDEX
- total / delivery_fee: Float
- delivery_code / pickup_code: String(6)
- delivery_address / latitude / longitude
- is_cancelled: Boolean
- payment_method: String(30)
- customer_note: Text
- delivered_at: DateTime
- created_at / updated_at: DateTime INDEX

Indexes: (store_id, created_at), (customer_id, created_at),
(delivery_person_id, created_at), (store_id, status), (customer_id, status).

### order_items

order_id, product_id, quantity, price, options_selected.

### order_status_history

order_id, from_status, to_status, changed_by (nullable FK), note, created_at.

### subscriptions

- user_id: FK users.id NULL INDEX
- store_id: FK stores.id NULL INDEX
- start_date / end_date: DateTime NOT NULL end
- amount: Float NOT NULL
- status: pending/paid/cancelled/expired/suspended
- payment_method: cash/wallet/bank_transfer/manual_delivery
- payment_ref / proof_image
- confirmation_code: String(20)
- confirmation_attempts / confirmation_expiry
- duration_days / renewal_count: Integer
- expiry_notified: Boolean
- admin_note: Text

Checks: amount >= 0, status IN (...), user_id OR store_id NOT NULL,
payment_method IN (...).

### payments

user_id, order_id, store_id, subscription_id, amount, method, status,
reference, proof_image, notes.

### cart_items

user_id, product_id, store_id, quantity.

### favorites

user_id + (product_id أو store_id).

### reviews

user_id + product_id, rating (1-5), comment.

### product_comments

user_id + product_id, text.

### product_reactions

user_id + product_id UNIQUE, reaction_type في {like, love, wow, sad, angry}.

### reels

store_id, product_id (nullable), video_url, thumbnail_url, caption,
views, is_active, created_at.

Indexes: (store_id, created_at), (is_active, created_at), (is_active, views).

### reel_reactions

reel_id + user_id UNIQUE, نفس reaction_type.

### notifications

- user_id: FK users.id INDEX
- title: String(200)
- message: String(200) NOT NULL
- link: String(200)
- is_read: Boolean INDEX
- type: String(50) INDEX — info/order/subscription/delivery/message/alert
- priority: String(20) — normal/important/urgent
- icon: String(50)
- is_global: Boolean
- extra_data: Text (JSON)
- entity_type / entity_id: INDEX — order/product/store/reel/subscription
- read_at / expires_at: DateTime
- created_at: DateTime

Indexes: (user_id, is_read), (user_id, type), (expires_at),
(entity_type, entity_id).

### push_subscriptions

user_id, endpoint UNIQUE NOT NULL, p256dh String(200), auth String(100).

### settings

جدول key/value عام. يُستخدم لـ: delivery_fee, subscription_price,
subscription_duration_days, wallet_number, vapid_public_key,
vapid_private_key, vapid_subject.

### login_attempts

ip_address String(50) INDEX, user_id FK NULL INDEX, attempted_at DateTime INDEX.
Index: (ip_address, attempted_at).

### password_resets

user_id NOT NULL, token String(100) UNIQUE (SHA256-hashed), expires_at.

### password_reset_attempts

email INDEX, ip_address INDEX, attempted_at INDEX.
Indexes: (email, attempted_at), (ip_address, attempted_at).

### user_activity

user_id PK (FK users.id), last_seen DateTime INDEX.
يُحدَّث كل 5 دقائق لكل مستخدم نشط.

### chat_messages

sender_id, receiver_id, message, is_read, created_at.

## Migration History

- 9bfb6bc2028e: initial_migration
- 9315065eaac3: add_last_seen_to_users
- 6d82e6ac58e5: drop_users_last_seen_moved_to_user_activity
- 6071984a9653: create_user_activity_table
- 2b3dd6c56674: remove_reel_comments_table_and_feature
- 789fa42b8b7c: add_index_on_products_views
- cf4f737c16a4: add_indexes_on_reels_views
- a1b2c3d4e5f6: add_subscription_overrides
- c3d4e5f6a7b8: add_auto_renew_to_stores
- d4e5f6a7b8c9: add_orders_v2_and_hide_price

## أوامر مفيدة

flask db migrate -m "وصف التعديل"    توليد migration جديد
flask db upgrade                      تطبيق
flask db current                      الحالة الحالية
flask db heads                        أحدث مراجعة
flask db downgrade                    تراجع خطوة
