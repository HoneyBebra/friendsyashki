import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

os.environ.setdefault("APP_NAME", "messenger-test")
os.environ.setdefault("APP_DESCRIPTION", "test")
os.environ.setdefault("APP_VERSION", "0.0.1")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test_messenger")
os.environ.setdefault("POSTGRES_HOST", "localhost")
os.environ.setdefault("POSTGRES_PORT", "5432")
os.environ.setdefault("POSTGRES_ECHO", "false")
os.environ.setdefault("AUTH_GRPC_HOST", "localhost")
os.environ.setdefault("AUTH_GRPC_PORT", "50051")

import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]  # noqa: E402

from src.main import app  # noqa: E402

MESSENGER_ROOT = Path(__file__).parent.parent


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    with PostgresContainer("postgres:17.4") as pg:
        yield pg


@pytest.fixture(scope="session")
def postgres_dsn(postgres_container: PostgresContainer) -> str:
    pg = postgres_container
    host = pg.get_container_host_ip()
    port = pg.get_exposed_port(5432)
    return f"postgresql+asyncpg://{pg.username}:{pg.password}" f"@{host}:{port}/{pg.dbname}"


@pytest.fixture(scope="session")
def alembic_env(postgres_container: PostgresContainer) -> dict[str, str]:
    pg = postgres_container
    host = pg.get_container_host_ip()
    port = pg.get_exposed_port(5432)
    env = os.environ.copy()
    env.update(
        {
            "POSTGRES_USER": pg.username,
            "POSTGRES_PASSWORD": pg.password,
            "POSTGRES_DB": pg.dbname,
            "POSTGRES_HOST": host,
            "POSTGRES_PORT": str(port),
            "POSTGRES_ECHO": "false",
            "APP_NAME": "messenger-test",
            "APP_DESCRIPTION": "test",
            "APP_VERSION": "0.0.1",
        }
    )
    return env


@pytest.fixture(scope="session")
def apply_migrations(alembic_env: dict[str, str]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(MESSENGER_ROOT),
        env=alembic_env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"Migration failed: {result.stderr}"


@pytest_asyncio.fixture
async def db_session(postgres_dsn: str, apply_migrations: None) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(postgres_dsn, echo=False)
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def db_client(postgres_dsn: str, apply_migrations: None) -> AsyncIterator[AsyncClient]:
    from src.db.postgres import get_session as _orig_get_session  # noqa: F811

    test_engine = create_async_engine(postgres_dsn, echo=False)
    test_factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        async with test_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[_orig_get_session] = _override_get_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.pop(_orig_get_session, None)
    await test_engine.dispose()
