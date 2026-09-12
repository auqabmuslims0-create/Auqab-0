"""drop users.last_seen (moved to user_activity)

Revision ID: 6d82e6ac58e5
Revises: cf4f737c16a4
Create Date: 2026-09-12

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '6d82e6ac58e5'
down_revision = 'cf4f737c16a4'
branch_labels = None
depends_on = None


def upgrade():
    """
    حذف users.last_seen إن وُجد.
    - SQLite محلي (مطبَّق سابقاً): غير موجود → نتخطى
    - PostgreSQL Railway: موجود → يُحذف بسلاسة
    """
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('users')]

    if 'last_seen' not in columns:
        print('  -> users.last_seen not present, skipping')
        return

    with op.batch_alter_table('users', schema=None) as batch_op:
        indexes = [i['name'] for i in insp.get_indexes('users')]
        if 'ix_users_last_seen' in indexes:
            try:
                batch_op.drop_index('ix_users_last_seen')
            except Exception as e:
                print(f'  -> failed to drop index (skip): {e}')
        try:
            batch_op.drop_column('last_seen')
        except Exception as e:
            print(f'  -> failed to drop column: {e}')


def downgrade():
    """إعادة العمود إن لم يكن موجوداً."""
    bind = op.get_bind()
    insp = inspect(bind)
    columns = [c['name'] for c in insp.get_columns('users')]

    if 'last_seen' in columns:
        return  # موجود بالفعل

    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('last_seen', sa.DateTime(), nullable=True))
        batch_op.create_index('ix_users_last_seen', ['last_seen'], unique=False)
