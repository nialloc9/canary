from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


class Database:
    def __init__(self, url: str, debug: bool = False):
        self._engine = create_async_engine(url, echo=debug, pool_pre_ping=True)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self):
        return self._engine

    async def get_session(self) -> AsyncSession:
        async with self._session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
            finally:
                await session.close()

    async def dispose(self) -> None:
        await self._engine.dispose()

    async def create_all(self) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)


from app.core.config import get_settings as _get_settings

_settings = _get_settings()
db = Database(url=_settings.database_url, debug=_settings.debug)


async def get_db() -> AsyncSession:
    async for session in db.get_session():
        yield session
