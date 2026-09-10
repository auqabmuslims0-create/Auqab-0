"""add subscription overrides to stores and admin_note to subscriptions

Revision ID: a1b2c3d4e5f6
Revises: 9315065eaac3
Create Date: 2026-09-10 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '9315065eaac3'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('stores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('custom_subscription_price', sa.Float(), nullable=True))
        batch_op.add_column(sa.Column('custom_subscription_duration_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('subscription_grace_days', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('subscription_notes', sa.Text(), nullable=True))

    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.add_column(sa.Column('admin_note', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('subscriptions', schema=None) as batch_op:
        batch_op.drop_column('admin_note')

    with op.batch_alter_table('stores', schema=None) as batch_op:
        batch_op.drop_column('subscription_notes')
        batch_op.drop_column('subscription_grace_days')
        batch_op.drop_column('custom_subscription_duration_days')
        batch_op.drop_column('custom_subscription_price')
