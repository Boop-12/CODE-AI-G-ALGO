"""Local browser-test API: always creates a new disposable SQLite database."""
import asyncio
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="gnk-browser-test-") as temporary:
        os.environ.update({
            "DATABASE_URL": "sqlite+aiosqlite:///" + str(Path(temporary) / "browser.db").replace("\\", "/"),
            "ENVIRONMENT": "test",
            "SECRET_KEY": "browser-test-only-key-never-for-production-123456789",
            "COOKIE_SECURE": "false",
            "ALLOWED_ORIGINS": "http://127.0.0.1:13000",
            "APP_BASE_URL": "http://127.0.0.1:13000",
            "SMTP_HOST": "", "SMTP_USER": "", "SMTP_PASSWORD": "", "SMTP_FROM": "",
        })
        from app.db.session import Base, engine
        from app.main import app
        import uvicorn

        async def initialize():
            async with engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)
            await engine.dispose()

        asyncio.run(initialize())
        uvicorn.run(app, host="127.0.0.1", port=18080, log_level="warning")
