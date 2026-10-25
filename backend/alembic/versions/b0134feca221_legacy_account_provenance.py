"""Add provenance without changing either existing account table or its data."""
from alembic import op
import sqlalchemy as sa

revision = "b0134feca221"
down_revision = "4ab19e21a04f"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "legacy_account_import",
        sa.Column("legacy_user_id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("user.id"), nullable=False, unique=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    # The import ledger is required to avoid duplicate identities on a later retry.
    # Refuse a downgrade after import instead of silently dropping provenance.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM legacy_account_import")).scalar_one():
        raise RuntimeError("Cannot remove legacy provenance after an account import")
    op.drop_table("legacy_account_import")
