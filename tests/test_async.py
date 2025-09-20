import pytest
import asyncio
from aioresponses import aioresponses
from apikeyrotator import AsyncAPIKeyRotator


@pytest.mark.asyncio
async def test_async_successful_get_request():
    url = "https://api.example.com/async_data"

    with aioresponses() as m:
        m.get(url, payload={"status": "ok"}, status=200)

        async with AsyncAPIKeyRotator(api_keys=["test_key"]) as rotator:
            async with await rotator.get(url) as response:
                assert response.status == 200
                data = await response.json()
                assert data == {"status": "ok"}