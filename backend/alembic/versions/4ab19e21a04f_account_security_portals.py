"""Add account security, preferences and administration data."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4ab19e21a04f"
down_revision: Union[str, Sequence[str], None] = "2487f776f72d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("user", sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user", sa.Column("theme", sa.String(length=12), nullable=False, server_default="system"))
    op.add_column("user", sa.Column("mfa_secret", sa.String(length=512), nullable=True))
    op.add_column("user", sa.Column("mfa_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(sa.text('UPDATE "user" SET email_verified = true'))
    op.add_column("browser_session", sa.Column("created_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("browser_session", sa.Column("ip_address", sa.String(length=64), nullable=True))
    op.add_column("browser_session", sa.Column("user_agent", sa.String(length=512), nullable=True))
    op.execute(sa.text("UPDATE browser_session SET created_at = CURRENT_TIMESTAMP WHERE created_at IS NULL"))
    with op.batch_alter_table("browser_session") as batch:
        batch.alter_column("created_at", existing_type=sa.DateTime(timezone=True), nullable=False)

    op.create_table(
        "email_verification_token",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_verification_token_user_id", "email_verification_token", ["user_id"])
    op.create_index("ix_email_verification_token_token_hash", "email_verification_token", ["token_hash"], unique=True)

    op.create_table(
        "login_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ip_address", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=512), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_login_history_user_id", "login_history", ["user_id"])

    op.create_table(
        "system_setting",
        sa.Column("key", sa.String(length=80), nullable=False),
        sa.Column("value", sa.String(length=1000), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("system_setting")
    op.drop_index("ix_login_history_user_id", table_name="login_history")
    op.drop_table("login_history")
    op.drop_index("ix_email_verification_token_token_hash", table_name="email_verification_token")
    op.drop_index("ix_email_verification_token_user_id", table_name="email_verification_token")
    op.drop_table("email_verification_token")
    op.drop_column("browser_session", "user_agent")
    op.drop_column("browser_session", "ip_address")
    op.drop_column("browser_session", "created_at")
    op.drop_column("user", "mfa_enabled")
    op.drop_column("user", "mfa_secret")
    op.drop_column("user", "theme")
    op.drop_column("user", "email_verified")
