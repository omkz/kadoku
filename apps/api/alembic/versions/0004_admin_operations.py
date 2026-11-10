"""Add operational fulfillment state, event audit and optional product SKUs.

Revision ID: 0004_admin_operations
Revises: 0003_order_shipping_address
Create Date: 2026-11-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_admin_operations"
down_revision = "0003_order_shipping_address"
branch_labels = None
depends_on = None


def upgrade():
    # Existing orders have no shipping progress; payment state is unchanged.
    op.add_column("orders", sa.Column(
        "fulfillment_status", sa.String(24),
        nullable=False, server_default="unfulfilled",
    ))
    op.add_column("orders", sa.Column("tracking_carrier", sa.String(80), nullable=True))
    op.add_column("orders", sa.Column("tracking_number", sa.String(120), nullable=True))
    op.add_column("orders", sa.Column("shipped_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("orders", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("products", sa.Column("sku", sa.String(64), nullable=True))
    op.create_index("ix_products_sku", "products", ["sku"], unique=True)
    op.create_table(
        "fulfillment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("from_status", sa.String(24), nullable=False),
        sa.Column("to_status", sa.String(24), nullable=False),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_fulfillment_events_order_id", "fulfillment_events", ["order_id"])


def downgrade():
    op.drop_index("ix_fulfillment_events_order_id", table_name="fulfillment_events")
    op.drop_table("fulfillment_events")
    op.drop_index("ix_products_sku", table_name="products")
    op.drop_column("products", "sku")
    op.drop_column("orders", "delivered_at")
    op.drop_column("orders", "shipped_at")
    op.drop_column("orders", "tracking_number")
    op.drop_column("orders", "tracking_carrier")
    op.drop_column("orders", "fulfillment_status")
