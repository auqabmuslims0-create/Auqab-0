"""add indexes on reels.views

Revision ID: cf4f737c16a4
Revises: 789fa42b8b7c
Create Date: 2026-09-12

"""
from alembic import op
import sqlalchemy as sa


revision = 'cf4f737c16a4'
down_revision = '789fa42b8b7c'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('reels', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_reels_views'), ['views'], unique=False)
        batch_op.create_index(batch_op.f('ix_reel_active_views'), ['is_active', 'views'], unique=False)


def downgrade():
    with op.batch_alter_table('reels', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_reel_active_views'))
        batch_op.drop_index(batch_op.f('ix_reels_views'))
