"""Widen FoodItem text columns to prevent import truncation errors

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-25 21:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f6a7b8c9d0e1'
down_revision = 'e5f6a7b8c9d0'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('FoodItems') as batch_op:
        batch_op.alter_column('FoodName',    existing_type=sa.String(50),  type_=sa.String(150), nullable=False)
        batch_op.alter_column('FoodName_en', existing_type=sa.String(50),  type_=sa.String(150), nullable=True)
        batch_op.alter_column('ImageFilename', existing_type=sa.String(100), type_=sa.String(500), nullable=True)
        batch_op.alter_column('Ingredients',   existing_type=sa.String(200), type_=sa.String(500), nullable=False)
        batch_op.alter_column('Ingredients_en', existing_type=sa.String(200), type_=sa.String(500), nullable=True)
        batch_op.alter_column('Description',   existing_type=sa.String(200), type_=sa.String(500), nullable=False)
        batch_op.alter_column('Description_en', existing_type=sa.String(200), type_=sa.String(500), nullable=True)

    with op.batch_alter_table('Categories') as batch_op:
        batch_op.alter_column('CategoryName',    existing_type=sa.String(50), type_=sa.String(150), nullable=False)
        batch_op.alter_column('CategoryName_en', existing_type=sa.String(50), type_=sa.String(150), nullable=True)

    with op.batch_alter_table('Subcategories') as batch_op:
        batch_op.alter_column('SubcategoryName',    existing_type=sa.String(50), type_=sa.String(150), nullable=False)
        batch_op.alter_column('SubcategoryName_en', existing_type=sa.String(50), type_=sa.String(150), nullable=True)


def downgrade():
    with op.batch_alter_table('FoodItems') as batch_op:
        batch_op.alter_column('FoodName',       existing_type=sa.String(150), type_=sa.String(50),  nullable=False)
        batch_op.alter_column('FoodName_en',    existing_type=sa.String(150), type_=sa.String(50),  nullable=True)
        batch_op.alter_column('ImageFilename',  existing_type=sa.String(500), type_=sa.String(100), nullable=True)
        batch_op.alter_column('Ingredients',    existing_type=sa.String(500), type_=sa.String(200), nullable=False)
        batch_op.alter_column('Ingredients_en', existing_type=sa.String(500), type_=sa.String(200), nullable=True)
        batch_op.alter_column('Description',    existing_type=sa.String(500), type_=sa.String(200), nullable=False)
        batch_op.alter_column('Description_en', existing_type=sa.String(500), type_=sa.String(200), nullable=True)

    with op.batch_alter_table('Categories') as batch_op:
        batch_op.alter_column('CategoryName',    existing_type=sa.String(150), type_=sa.String(50), nullable=False)
        batch_op.alter_column('CategoryName_en', existing_type=sa.String(150), type_=sa.String(50), nullable=True)

    with op.batch_alter_table('Subcategories') as batch_op:
        batch_op.alter_column('SubcategoryName',    existing_type=sa.String(150), type_=sa.String(50), nullable=False)
        batch_op.alter_column('SubcategoryName_en', existing_type=sa.String(150), type_=sa.String(50), nullable=True)
