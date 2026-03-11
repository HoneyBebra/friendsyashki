from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from src.api.v1.dialogs import router as dialogs_router
from src.api.v1.health import router as health_router
from src.api.v1.messages import router as messages_router
from src.core.config import settings
from src.core.logger import LOGGING
from src.db.postgres import engine
from src.gRPC.client import close_auth_grpc_channel, open_auth_grpc_channel
from src.ws.manager import ws_manager
from src.ws.pubsub import RedisPubSub
from src.ws.router import router as ws_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await open_auth_grpc_channel()

    pubsub = RedisPubSub(
        redis_url=settings.redis_url,
        manager=ws_manager,
    )
    ws_manager.set_pubsub(pubsub)
    await pubsub.start()

    yield

    await pubsub.stop()
    await close_auth_grpc_channel()
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

router = APIRouter(prefix=settings.api_v1_prefix)
router.include_router(health_router)
router.include_router(dialogs_router)
router.include_router(messages_router)
app.include_router(router)
app.include_router(ws_router, prefix="/messenger")

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING,
        log_level=settings.log_level,
    )
