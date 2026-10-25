"""Opt-in account import when legacy users and target user coexist in one database.

Default is read-only dry-run. Never copies sessions, administrator privileges or
plaintext passwords; never updates/deletes a legacy record or an existing user.
"""
import argparse
import asyncio
import json
import uuid
from collections import Counter
from datetime import datetime, timezone
from pydantic import EmailStr, TypeAdapter, ValidationError

from argon2 import extract_parameters
from argon2.exceptions import InvalidHashError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, engine
from app.models import Account, AuditLog, LegacyAccountImport, User


class ImportConflict(ValueError):
    """Sanitized validation failure: never include credentials or personal data."""


def supported_password_hash(value: str) -> bool:
    if not isinstance(value, str) or not value.startswith("$argon2id$"):
        return False
    try:
        parameters = extract_parameters(value)
        return (8192 <= parameters.memory_cost <= 262144 and 1 <= parameters.time_cost <= 10
                and 1 <= parameters.parallelism <= 8 and parameters.hash_len >= 16
                and parameters.salt_len >= 16)
    except (InvalidHashError, ValueError):
        return False


def legacy_created_at(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime):
        raise ValueError("Invalid creation time")
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def valid_record(row) -> bool:
    try:
        TypeAdapter(EmailStr).validate_python(str(row["email"]).strip())
        legacy_created_at(row["created_at"])
        return (supported_password_hash(row["password_hash"]) and bool(str(row["name"]).strip())
                and isinstance(row["id"], int) and isinstance(row["is_active"], (bool, int))
                and row["is_active"] in (0, 1))
    except (ValueError, TypeError, ValidationError):
        return False


async def import_accounts(db: AsyncSession, *, apply: bool = False) -> dict[str, int | bool]:
    # PostgreSQL transaction lock serializes importer instances. Existing user email
    # uniqueness and the provenance primary key remain the final concurrency guards.
    if apply and db.bind.dialect.name == "postgresql":
        await db.execute(text("SELECT pg_advisory_xact_lock(5746532201)"))
    rows = list((await db.execute(text(
        "SELECT id, name, email, password_hash, is_active, created_at FROM users ORDER BY id"
    ))).mappings())
    mappings = {row.legacy_user_id: row.user_id for row in (await db.execute(select(LegacyAccountImport))).scalars()}
    existing_emails = set((await db.execute(select(func.lower(User.email)))).scalars())
    pending = [row for row in rows if row["id"] not in mappings]
    normalized = [str(row["email"]).strip().lower() for row in pending]
    collisions = sum(email in existing_emails for email in normalized)
    collisions += sum(count - 1 for count in Counter(normalized).values() if count > 1)
    invalid = sum(not valid_record(row) for row in pending)
    report = {"dry_run": not apply, "source_records": len(rows), "already_imported": len(rows) - len(pending),
              "eligible": len(pending), "email_conflicts": collisions, "invalid_records": invalid, "imported": 0}
    if not apply:
        return report
    if collisions or invalid:
        raise ImportConflict("Import refused: resolve email conflicts or invalid legacy records before applying")
    # Reconcile identities explicitly. No source admin/authority grants are copied.
    # The target's existing PostgreSQL records and all legacy tables remain intact.
    for row, email in zip(pending, normalized):
        user = User(id=uuid.uuid4(), name=str(row["name"]).strip(), email=email,
                    hashed_password=row["password_hash"], is_active=bool(row["is_active"]),
                    email_verified=False, mfa_enabled=False, theme="system",
                    created_at=legacy_created_at(row["created_at"]))
        db.add(user)
        await db.flush()
        db.add(Account(user_id=user.id))
        db.add(LegacyAccountImport(legacy_user_id=row["id"], user_id=user.id))
        db.add(AuditLog(user_id=user.id, action="account.legacy_imported", detail="Legacy identity mapped; no roles or sessions transferred"))
    await db.flush()
    report["imported"] = len(pending)
    return report


async def main(apply: bool):
    # The operational command targets the configured single PostgreSQL database.
    # SQLite is supported only by automated tests of the transaction logic.
    if engine.dialect.name != "postgresql":
        raise ImportConflict("Operational import requires the configured PostgreSQL database")
    try:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                report = await import_accounts(db, apply=apply)
                if not apply:
                    await db.rollback()
        print(json.dumps(report, sort_keys=True))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Write additive identities after a clean dry-run and verified backup")
    arguments = parser.parse_args()
    try:
        asyncio.run(main(arguments.apply))
    except ImportConflict as error:
        parser.exit(1, str(error) + "\n")
    except Exception:
        parser.exit(1, "Import could not complete; transaction rolled back. Check schema availability privately; no database details are printed.\n")
