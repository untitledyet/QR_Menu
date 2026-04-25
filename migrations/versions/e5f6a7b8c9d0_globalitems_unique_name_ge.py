"""GlobalItems: unique constraint on name_ge

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-25 17:00:00.000000

"""
from alembic import op

revision = 'e5f6a7b8c9d0'
down_revision = 'd4e5f6a7b8c9'
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint('uq_globalitems_name_ge', 'GlobalItems', ['name_ge'])


def downgrade():
    op.drop_constraint('uq_globalitems_name_ge', 'GlobalItems', type_='unique')
