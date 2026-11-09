"""Allow optional product images for curated demo catalog.

Revision ID: 0002_product_images
Revises: 0001_initial
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_product_images"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("products", sa.Column("image_url", sa.String(length=255), nullable=True))


def downgrade():
    op.drop_column("products", "image_url")
