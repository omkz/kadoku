"""Store recipient shipping address snapshot on demo orders.

Revision ID: 0003_order_shipping_address
Revises: 0002_product_images
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_order_shipping_address"
down_revision = "0002_product_images"
branch_labels = None
depends_on = None


def upgrade():
    # Old Sandbox orders intentionally remain address-less.
    op.add_column("orders", sa.Column("shipping_address", sa.JSON(), nullable=True))


def downgrade():
    op.drop_column("orders", "shipping_address")
