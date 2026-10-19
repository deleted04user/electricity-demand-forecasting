"""HTTP limits must apply to real streamed bytes without breaking API diagnostics."""

import asyncio
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest
from backend.api_models import FutureRequest
from backend.main import create_app
from backend.settings import Settings
from fastapi import Request
from fastapi.testclient import TestClient


def application(limit=1024):
    def forbidden_forecast(*args):
        pytest.fail("Invalid input reached the forecasting service")

    app = create_app(
        replace(Settings.from_env(), max_request_body_bytes=limit, sentry_dsn=None),
        service_factory=lambda settings: SimpleNamespace(
            closed=False, close=lambda: None, future_forecast=forbidden_forecast
        ),
    )

    @app.post("/test-body")
    async def echo(request: Request):
        return {"bytes": len(await request.body())}

    return app


def test_body_limit_boundary_preserves_request_ids_cors_and_expected_error_behavior():
    captured = []
    with TestClient(application()) as client:
        client.app.state.runtime.reporter = SimpleNamespace(
            capture_exception=lambda *args, **kwargs: captured.append(args), close=lambda: None
        )
        assert client.post("/test-body", content=b"x" * 1024).json() == {"bytes": 1024}
        response = client.post(
            "/api/forecast/future",
            content=b"private-body-value" * 100,
            headers={"Origin": "http://localhost:5173", "Content-Type": "application/json"},
        )
        assert response.status_code == 413
        assert len(response.headers["X-Request-ID"]) == 32
        assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:5173"
        assert "private-body-value" not in response.text
        assert captured == []
        assert (
            "413"
            in client.get("/openapi.json").json()["paths"]["/api/forecast/future"]["post"][
                "responses"
            ]
        )


@pytest.mark.parametrize("declared_length", [None, "1"])
def test_streamed_body_cannot_bypass_limit_with_absent_or_dishonest_length(declared_length):
    async def run():
        async def chunks():
            yield b"x" * 600
            yield b"y" * 600

        headers = {} if declared_length is None else {"Content-Length": declared_length}
        async with httpx.AsyncClient(transport=httpx.ASGITransport(application())) as client:
            return await client.post("http://test/test-body", content=chunks(), headers=headers)

    response = asyncio.run(run())
    assert response.status_code == 413
    assert len(response.headers["X-Request-ID"]) == 32
    if declared_length is None:
        assert "content-length" not in response.request.headers


def test_declared_oversize_body_is_rejected_without_consuming_the_stream():
    consumed = []

    async def run():
        async def chunks():
            consumed.append(True)
            yield b"x" * 2048

        async with httpx.AsyncClient(transport=httpx.ASGITransport(application())) as client:
            return await client.post(
                "http://test/test-body", content=chunks(), headers={"Content-Length": "2048"}
            )

    assert asyncio.run(run()).status_code == 413
    assert consumed == []


def test_stream_counts_are_per_request_and_policy_is_per_application():
    async def run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(application())) as client:
            responses = await asyncio.gather(
                client.post("http://test/test-body", content=b"x" * 600),
                client.post("http://test/test-body", content=b"y" * 600),
            )
        assert [response.json() for response in responses] == [{"bytes": 600}, {"bytes": 600}]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(application(2048))) as client:
            assert (
                await client.post("http://test/test-body", content=b"x" * 1500)
            ).status_code == 200

    asyncio.run(run())


@pytest.mark.parametrize("value", [True, False, "20", None])
@pytest.mark.parametrize("field", ["temperature", "humidity"])
def test_weather_values_are_numbers_without_silent_type_coercion(field, value):
    payload = {"start": "2025-01-01", "horizon": 2, "temperature": [20, 21], "humidity": [50, 55]}
    payload[field][0] = value
    with TestClient(application(65536)) as client:
        assert client.post("/api/forecast/future", json=payload).status_code == 422


def test_weather_arrays_accept_integer_and_float_numbers_but_remain_bounded():
    valid = {
        "start": "2025-01-01",
        "horizon": 168,
        "temperature": [20, 20.5] * 84,
        "humidity": [50] * 168,
    }
    request = FutureRequest.model_validate(valid)
    assert request.temperature[:2] == [20.0, 20.5]
    with TestClient(application(65536)) as client:
        assert (
            client.post(
                "/api/forecast/future", json={**valid, "temperature": [20] * 169}
            ).status_code
            == 422
        )


@pytest.mark.parametrize("limit", [0, 1023, 1048577, True, 1.5])
def test_invalid_body_limits_fail_configuration(limit):
    with pytest.raises(ValueError, match="MAX_REQUEST_BODY_BYTES"):
        replace(Settings.from_env(), max_request_body_bytes=limit)


def test_body_limit_is_captured_at_application_creation(monkeypatch):
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "2048")
    app = application(Settings.from_env().max_request_body_bytes)
    monkeypatch.setenv("MAX_REQUEST_BODY_BYTES", "1024")
    with TestClient(app) as client:
        assert client.post("/test-body", content=b"x" * 1500).status_code == 200
