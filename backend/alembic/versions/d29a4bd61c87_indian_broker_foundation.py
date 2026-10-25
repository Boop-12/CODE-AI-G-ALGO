"""Add mock broker connections and exchange-aware paper instruments."""
from alembic import op
import sqlalchemy as sa


revision = "d29a4bd61c87"
down_revision = "b0134feca221"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "paper_order",
        sa.Column("exchange", sa.String(length=4), nullable=False, server_default="NSE"),
    )

    op.create_table(
        "paper_position_exchange_new",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("exchange", sa.String(length=4), nullable=False, server_default="NSE"),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "exchange", "symbol", name="uq_paper_position_user_exchange_symbol"),
    )
    op.execute(sa.text(
        "INSERT INTO paper_position_exchange_new "
        "(id, user_id, exchange, symbol, quantity, average_price) "
        "SELECT id, user_id, 'NSE', symbol, quantity, average_price FROM paper_position"
    ))
    op.drop_index("ix_paper_position_user_id", table_name="paper_position")
    op.drop_table("paper_position")
    op.rename_table("paper_position_exchange_new", "paper_position")
    op.create_index("ix_paper_position_user_id", "paper_position", ["user_id"])

    op.create_table(
        "broker_connection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="disconnected"),
        sa.Column("account_label", sa.String(length=100), nullable=False, server_default="GNK Mock Paper"),
        sa.Column("encrypted_access_token", sa.Text(), nullable=True),
        sa.Column("credential_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_health_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_sync_status", sa.String(length=20), nullable=True),
        sa.Column("last_sync_error", sa.String(length=120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_broker_connection_user_provider"),
    )
    op.create_index("ix_broker_connection_user_id", "broker_connection", ["user_id"])


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text(
        "SELECT COUNT(*) FROM broker_connection"
    )).scalar_one():
        raise RuntimeError("Cannot remove broker connection records during downgrade")
    if bind.execute(sa.text(
        "SELECT COUNT(*) FROM paper_order WHERE exchange != 'NSE'"
    )).scalar_one() or bind.execute(sa.text(
        "SELECT COUNT(*) FROM paper_position WHERE exchange != 'NSE'"
    )).scalar_one():
        raise RuntimeError("Cannot downgrade while BSE paper orders or positions exist")

    op.drop_index("ix_broker_connection_user_id", table_name="broker_connection")
    op.drop_table("broker_connection")
    op.drop_index("ix_paper_position_user_id", table_name="paper_position")
    op.create_table(
        "paper_position_nse_new",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("average_price", sa.Numeric(precision=18, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "symbol"),
    )
    op.execute(sa.text(
        "INSERT INTO paper_position_nse_new "
        "(id, user_id, symbol, quantity, average_price) "
        "SELECT id, user_id, symbol, quantity, average_price FROM paper_position"
    ))
    op.drop_table("paper_position")
    op.rename_table("paper_position_nse_new", "paper_position")
    op.create_index("ix_paper_position_user_id", "paper_position", ["user_id"])
    op.drop_column("paper_order", "exchange")
