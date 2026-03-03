from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.responses import ORJSONResponse

from src.api.v1.health import router as health_router
from src.core.config import settings
from src.core.logger import LOGGING
from src.db.postgres import engine


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    description=settings.app_description,
    version=settings.app_version,
    docs_url=f"{settings.api_v1_prefix}/openapi",
    openapi_url=f"{settings.api_v1_prefix}/openapi.json",
    default_response_class=ORJSONResponse,
    lifespan=lifespan,
)

router = APIRouter(prefix=settings.api_v1_prefix)
router.include_router(health_router)
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING,
        log_level="debug",
    )
