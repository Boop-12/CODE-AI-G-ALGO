"""Exercise additive migrations only on a newly created pytest SQLite file."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys


def test_additive_legacy_migration_preserves_records_and_protects_provenance(tmp_path):
    database = tmp_path / "migration-test.db"
    assert not database.exists()
    backend = Path(__file__).resolve().parents[1]
    environment = dict(os.environ, DATABASE_URL="sqlite+aiosqlite:///" + database.as_posix(),
                       ENVIRONMENT="test", SMTP_HOST="", SECRET_KEY="migration-test-only-key-12345678901234567890")

    def alembic(*arguments, success=True):
        result = subprocess.run([sys.executable, "-m", "alembic", *arguments],
                                cwd=backend, env=environment, capture_output=True, text=True)
        assert (result.returncode == 0) == success, result.stderr
        return result

    alembic("upgrade", "4ab19e21a04f")
    user_id = "0123456789abcdef0123456789abcdef"
    with sqlite3.connect(database) as connection:
        connection.execute('INSERT INTO "user" (id, email, name, hashed_password, is_active) VALUES (?, ?, ?, ?, ?)',
                           (user_id, "migration-test@example.com", "Preserved Trader", "preserved-password-hash", True))
    alembic("upgrade", "head")
    alembic("check")
    with sqlite3.connect(database) as connection:
        assert connection.execute('SELECT hashed_password FROM "user" WHERE id=?', (user_id,)).fetchone() == ("preserved-password-hash",)
    alembic("downgrade", "4ab19e21a04f")
    alembic("upgrade", "head")
    with sqlite3.connect(database) as connection:
        connection.execute("INSERT INTO legacy_account_import VALUES (?, ?, CURRENT_TIMESTAMP)", (42, user_id))
    result = alembic("downgrade", "4ab19e21a04f", success=False)
    assert "Cannot remove legacy provenance" in result.stderr
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT legacy_user_id FROM legacy_account_import").fetchall() == [(42,)]
        assert connection.execute('SELECT COUNT(*) FROM "user"').fetchone() == (1,)
