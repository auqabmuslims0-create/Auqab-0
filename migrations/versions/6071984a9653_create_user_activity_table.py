"""create user_activity table (idempotent)

Revision ID: 6071984a9653
Revises: 2b3dd6c56674
Create Date: 2026-09-17 12:29:12.253341

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = '6071984a9653'
down_revision = '2b3dd6c56674'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'user_activity' not in existing_tables:
        op.create_table(
            'user_activity',
            sa.Column('user_id', sa.Integer(), nullable=False),
            sa.Column('last_seen', sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(['user_id'], ['users.id']),
            sa.PrimaryKeyConstraint('user_id'),
        )
        print(">>> user_activity table created")
    else:
        print(">>> user_activity table already exists, skipping create")

    existing_indexes = [i['name'] for i in inspector.get_indexes('user_activity')]
    if 'ix_user_activity_last_seen' not in existing_indexes:
        with op.batch_alter_table('user_activity', schema=None) as batch_op:
            batch_op.create_index(
                batch_op.f('ix_user_activity_last_seen'),
                ['last_seen'],
                unique=False,
            )
        print(">>> ix_user_activity_last_seen index created")
    else:
        print(">>> ix_user_activity_last_seen already exists, skipping")


def downgrade():
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if 'user_activity' in existing_tables:
        existing_indexes = [i['name'] for i in inspector.get_indexes('user_activity')]
        if 'ix_user_activity_last_seen' in existing_indexes:
            with op.batch_alter_table('user_activity', schema=None) as batch_op:
                batch_op.drop_index(batch_op.f('ix_user_activity_last_seen'))
        op.drop_table('user_activity')
