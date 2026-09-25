"""SQLAlchemy 异步引擎与会话。"""

from typing import Any

from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.ai_video.config import settings


def _build_engine() -> AsyncEngine:
    return create_async_engine(
        settings.resolved_database_url,
        echo=settings.debug,
        future=True,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
    )


def _build_session_maker(bind_engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


class _AsyncSessionMakerProxy:
    """可重绑定的 sessionmaker 代理。

    Celery prefork 模式下，worker 子进程不能继续复用父进程里初始化的
    async engine / sessionmaker。这里保持导入对象稳定，同时允许在子进程
    启动后重新绑定底层 sessionmaker。
    """

    def __init__(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def configure(self, maker: async_sessionmaker[AsyncSession]) -> None:
        self._maker = maker

    def __call__(self, *args: Any, **kwargs: Any) -> AsyncSession:
        return self._maker(*args, **kwargs)


engine = _build_engine()
async_session_maker = _AsyncSessionMakerProxy(_build_session_maker(engine))


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""

    pass


def _apply_additive_ai_video_schema_updates(sync_conn: Any) -> None:
    """Apply small additive updates for deployments that predate migrations."""
    inspector = inspect(sync_conn)
    if "project_research" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("project_research")}
    if "entry_mode" not in columns:
        sync_conn.exec_driver_sql(
            "ALTER TABLE project_research "
            "ADD COLUMN entry_mode VARCHAR(16) NOT NULL DEFAULT 'research'"
        )


async def init_db() -> None:
    """创建所有表（开发/迁移用）。"""
    # 确保 ORM 模型已导入，从而注册到 Base.metadata
    import app.ai_video.models.llm  # noqa: F401  # pylint: disable=unused-import
    import app.ai_video.models.integration_hub  # noqa: F401
    import app.ai_video.models.production_control  # noqa: F401
    import app.ai_video.models.production_execution  # noqa: F401
    import app.ai_video.models.studio_products  # noqa: F401
    import app.ai_video.models.studio  # noqa: F401
    import app.ai_video.models.task  # noqa: F401
    import app.ai_video.models.task_links  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_apply_additive_ai_video_schema_updates)
    from app.ai_video.services.llm.builtin_model_catalog import seed_user_approved_models

    async with async_session_maker() as session:
        await seed_user_approved_models(session)
        await session.commit()


async def close_db() -> None:
    """关闭数据库连接。"""
    await engine.dispose()


def reset_db_runtime() -> None:
    """在 Celery worker 子进程中重建 engine 与 sessionmaker。

    这样可以避免 prefork 继承父进程中的 async engine，导致连接对象和事件循环
    绑定错乱，触发 Future attached to a different loop。
    """

    global engine

    engine = _build_engine()
    async_session_maker.configure(_build_session_maker(engine))
