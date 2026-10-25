"""Add one-time broker OAuth state and provider account identifiers."""
from alembic import op
import sqlalchemy as sa


revision = "a71c0e683d42"
down_revision = "d29a4bd61c87"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("broker_connection", sa.Column("provider_account_id", sa.String(length=100), nullable=True))
    op.create_table(
        "broker_authorization_attempt",
        sa.Column("state_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=30), nullable=False),
        sa.Column("provider_request_id", sa.String(length=100), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("state_hash"),
    )
    op.create_index(
        "ix_broker_authorization_attempt_user_id",
        "broker_authorization_attempt",
        ["user_id"],
    )


def downgrade():
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT COUNT(*) FROM broker_authorization_attempt")).scalar_one():
        raise RuntimeError("Cannot remove active or historical broker authorization attempts")
    op.drop_index("ix_broker_authorization_attempt_user_id", table_name="broker_authorization_attempt")
    op.drop_table("broker_authorization_attempt")
    op.drop_column("broker_connection", "provider_account_id")
