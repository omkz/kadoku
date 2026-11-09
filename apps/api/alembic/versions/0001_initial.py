"""Initial Kadoku product, profile, recommendation quota, and payment tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-11-09
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "products",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("price_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3)),
        sa.Column("stock", sa.Integer()),
        sa.Column("active", sa.Boolean()),
        sa.Column("interests", sa.JSON()),
        sa.Column("occasions", sa.JSON()),
        sa.Column("styles", sa.JSON()),
        sa.Column("emoji", sa.String(12)),
        sa.Column("demo_only", sa.Boolean()),
    )
    op.create_index("ix_products_category", "products", ["category"])
    op.create_table(
        "recipients",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("relationship", sa.String(80)),
        sa.Column("interests", sa.JSON()),
        sa.Column("avoids", sa.JSON()),
        sa.Column("usual_budget_minor", sa.Integer()),
    )
    op.create_index("ix_recipients_user_id", "recipients", ["user_id"])
    op.create_table(
        "occasions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("recipient_id", sa.String(36), sa.ForeignKey("recipients.id", ondelete="CASCADE")),
        sa.Column("kind", sa.String(40)),
        sa.Column("month", sa.Integer()),
        sa.Column("day", sa.Integer()),
        sa.Column("year", sa.Integer()),
        sa.Column("reminder_enabled", sa.Boolean()),
    )
    op.create_index("ix_occasions_recipient_id", "occasions", ["recipient_id"])
    op.create_table(
        "recommendation_usage",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("subject", sa.String(128)),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer()),
        sa.UniqueConstraint("subject", "day", name="uq_usage_subject_day"),
    )
    op.create_index("ix_recommendation_usage_subject", "recommendation_usage", ["subject"])
    op.create_table(
        "orders",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(128)),
        sa.Column("product_id", sa.String(36), sa.ForeignKey("products.id")),
        sa.Column("price_snapshot_minor", sa.Integer()),
        sa.Column("currency", sa.String(3)),
        sa.Column("status", sa.String(24)),
        sa.Column("paypal_order_id", sa.String(64), unique=True),
        sa.Column("paypal_capture_id", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_table(
        "payment_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("provider_event_id", sa.String(128), unique=True),
        sa.Column("event_type", sa.String(128)),
        sa.Column("processed_at", sa.DateTime(timezone=True)),
    )


def downgrade():
    for table in ["payment_events", "orders", "recommendation_usage", "occasions", "recipients", "products"]:
        op.drop_table(table)
