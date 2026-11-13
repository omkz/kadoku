"""Track idempotent PayPal Sandbox refund attempts.

Revision ID: 0005_payment_refunds
Revises: 0004_admin_operations
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_payment_refunds"
down_revision = "0004_admin_operations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_refunds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("order_id", sa.String(36), sa.ForeignKey("orders.id"), nullable=False),
        sa.Column("request_key", sa.String(36), nullable=False),
        sa.Column("actor_user_id", sa.String(128), nullable=False),
        sa.Column("amount_minor", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("paypal_refund_id", sa.String(64), unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("order_id", "request_key", name="uq_refund_order_request"),
    )
    op.create_index("ix_payment_refunds_order_id", "payment_refunds", ["order_id"])


def downgrade():
    op.drop_index("ix_payment_refunds_order_id", table_name="payment_refunds")
    op.drop_table("payment_refunds")
