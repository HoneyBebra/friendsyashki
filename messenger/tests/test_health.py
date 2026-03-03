import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/messenger/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
