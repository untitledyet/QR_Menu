"""Category system v2 — global taxonomy, sort_order, is_hidden, venue_type

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-28 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = 'h8i9j0k1l2m3'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('Categories') as batch_op:
        batch_op.add_column(sa.Column('global_category_id', sa.Integer(),
                                      sa.ForeignKey('GlobalCategories.id'), nullable=True))
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('icon_custom', sa.String(300), nullable=True))
        batch_op.create_index('idx_categories_global', ['global_category_id'])

    with op.batch_alter_table('Subcategories') as batch_op:
        batch_op.add_column(sa.Column('global_subcategory_id', sa.Integer(),
                                      sa.ForeignKey('GlobalSubcategories.id'), nullable=True))
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))
        batch_op.add_column(sa.Column('is_hidden', sa.Boolean(), nullable=False, server_default='0'))

    with op.batch_alter_table('GlobalSubcategories') as batch_op:
        batch_op.add_column(sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'))

    with op.batch_alter_table('Venues') as batch_op:
        batch_op.add_column(sa.Column('venue_type', sa.String(30), nullable=False, server_default='restaurant'))


def downgrade():
    with op.batch_alter_table('Venues') as batch_op:
        batch_op.drop_column('venue_type')

    with op.batch_alter_table('GlobalSubcategories') as batch_op:
        batch_op.drop_column('sort_order')

    with op.batch_alter_table('Subcategories') as batch_op:
        batch_op.drop_column('is_hidden')
        batch_op.drop_column('sort_order')
        batch_op.drop_column('global_subcategory_id')

    with op.batch_alter_table('Categories') as batch_op:
        batch_op.drop_index('idx_categories_global')
        batch_op.drop_column('icon_custom')
        batch_op.drop_column('is_hidden')
        batch_op.drop_column('sort_order')
        batch_op.drop_column('global_category_id')
