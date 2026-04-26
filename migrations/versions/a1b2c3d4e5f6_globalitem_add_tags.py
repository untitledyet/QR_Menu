"""Add tags column to GlobalItems

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
Create Date: 2026-04-26 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'a1b2c3d4e5f6'
down_revision = 'f6a7b8c9d0e1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('GlobalItems') as batch_op:
        batch_op.add_column(sa.Column('tags', sa.Text(), nullable=True))


def downgrade():
    with op.batch_alter_table('GlobalItems') as batch_op:
        batch_op.drop_column('tags')
