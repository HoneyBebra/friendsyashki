# ruff: noqa: I001

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import grpc
import uvicorn
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse

from src.api.v1.users import router as users_router
from src.core.config import settings
from src.core.logger import LOGGING
from src.gRPC.protos import user_pb2_grpc
from src.gRPC.server import create_grpc_server

logger = logging.getLogger(__name__)


def _load_grpc_server_credentials() -> grpc.ServerCredentials:
    """Load TLS certificates for gRPC server."""
    cert_path = Path(settings.grpc_tls_cert)
    key_path = Path(settings.grpc_tls_key)
    ca_path = Path(settings.grpc_tls_ca)

    for path, label in [(cert_path, "certificate"), (key_path, "private key"), (ca_path, "CA")]:
        if not path.is_file():
            logger.critical("gRPC TLS %s not found: %s", label, path)
            raise FileNotFoundError(f"gRPC TLS {label} not found: {path}")

    private_key = key_path.read_bytes()
    certificate_chain = cert_path.read_bytes()
    root_ca = ca_path.read_bytes()

    return grpc.ssl_server_credentials(
        private_key_certificate_chain_pairs=[(private_key, certificate_chain)],
        root_certificates=root_ca,
        require_client_auth=True,
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator:
    server = grpc.aio.server()
    user_pb2_grpc.add_UserServicer_to_server(create_grpc_server(), server)

    credentials = _load_grpc_server_credentials()
    server.add_secure_port(f"[::]:{settings.grpc_port}", credentials)
    logger.info("gRPC server starting with TLS on port %s", settings.grpc_port)

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

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
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
        log_level=settings.log_level,
    )
