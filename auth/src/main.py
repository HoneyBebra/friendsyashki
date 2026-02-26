# ruff: noqa: I001

from contextlib import asynccontextmanager
from typing import AsyncIterator

import grpc
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.responses import ORJSONResponse

from src.api.v1.users import router as users_router
from src.core.config import settings
from src.core.logger import LOGGING
from src.gRPC.protos import user_pb2_grpc
from src.gRPC.server import get_grpc_session


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:

    server = grpc.aio.server()
    user_pb2_grpc.add_UserServicer_to_server(await get_grpc_session(), server)
    server.add_insecure_port(f"[::]:{settings.grpc_port}")

    await server.start()
    yield
    await server.stop()


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
router.include_router(users_router)
app.include_router(router)

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_config=LOGGING,
        log_level="debug",
    )
