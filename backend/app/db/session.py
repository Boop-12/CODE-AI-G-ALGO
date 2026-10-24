from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from app.core.config import settings

engine = create_async_engine(
    settings.SQLALCHEMY_DATABASE_URI, pool_pre_ping=True,
    **({"poolclass": NullPool} if settings.ENVIRONMENT == "test" else {}),
)
AsyncSessionLocal = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
