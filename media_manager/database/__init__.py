import logging
import os
from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.engine.url import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import declarative_base

from media_manager.database.config import DbConfig

log = logging.getLogger(__name__)

Base = declarative_base()

engine: AsyncEngine | None = None
SessionLocal: async_sessionmaker[AsyncSession] | None = None


def build_db_url(
    user: str,
    password: str,
    host: str,
    port: int | str,
    dbname: str,
) -> URL:
    return URL.create(
        "postgresql+psycopg",
        user,
        password,
        host,
        int(port),
        dbname,
    )


def init_engine(
    db_config: DbConfig | None = None,
    url: str | URL | None = None,
) -> AsyncEngine:
    """
    Initialize the global SQLAlchemy engine and session factory.
    Pass either a DbConfig-like object or a full URL. Only initializes once.
    """
    global engine, SessionLocal
    if engine is not None:
        return engine

    if url is None:
        if db_config is None:
            url = os.getenv("DATABASE_URL")
            if not url:
                msg = "DB config or `DATABASE_URL` must be provided"
                raise RuntimeError(msg)
        else:
            url = build_db_url(
                db_config.user,
                db_config.password,
                db_config.host,
                db_config.port,
                db_config.dbname,
            )

    engine = create_async_engine(
        url,
        echo=False,
        pool_size=10,
        max_overflow=10,
        pool_timeout=30,
        pool_recycle=1800,
    )
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    log.debug("SQLAlchemy engine initialized")
    return engine


async def get_async_session() -> AsyncIterator[AsyncSession]:
    if SessionLocal is None:
        msg = "Session factory not initialized. Call init_engine(...) first."
        raise RuntimeError(msg)
    async with SessionLocal() as db:
        try:
            yield db
            await db.commit()
        except Exception:
            await db.rollback()
            log.critical("", exc_info=True)
            raise


DbSessionDependency = Annotated[AsyncSession, Depends(get_async_session)]
