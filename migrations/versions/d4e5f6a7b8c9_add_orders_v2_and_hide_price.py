"""add orders v2 fields (pickup_code, customer_note, updated_at) + products.hide_price

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-09-11

الوصف:
- orders.pickup_code: كود استلام من المتجر يؤكده المندوب
- orders.customer_note: ملاحظة الزبون على الطلب
- orders.updated_at: آخر تحديث للطلب
- products.hide_price: إخفاء السعر — يمنع التوصيل
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd4e5f6a7b8c9'
down_revision = 'c3d4e5f6a7b8'
branch_labels = None
depends_on = None


def upgrade():
    # orders: pickup_code
    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pickup_code', sa.String(length=6), nullable=True))
        batch_op.add_column(sa.Column('customer_note', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('updated_at', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_orders_pickup_code', ['pickup_code'], unique=False)

    # products: hide_price (default false)
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('hide_price', sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade():
    with op.batch_alter_table('products', schema=None) as batch_op:
        batch_op.drop_column('hide_price')

    with op.batch_alter_table('orders', schema=None) as batch_op:
        batch_op.drop_index('ix_orders_pickup_code')
        batch_op.drop_column('updated_at')
        batch_op.drop_column('customer_note')
        batch_op.drop_column('pickup_code')
