"""Exercise the real SDK with an in-memory transport; no Sentry account or network."""

import builtins
import json
from dataclasses import replace
from types import SimpleNamespace

import pytest
import sentry_sdk
from backend.error_reporting import create_error_reporter
from backend.main import create_app
from backend.settings import Settings
from fastapi.testclient import TestClient
from sentry_sdk.client import Client
from sentry_sdk.transport import Transport


class MemoryTransport(Transport):
    def __init__(self, options):
        super().__init__(options)
        self.events = []
        self.closed = False
        self.flush_timeouts = []

    def capture_envelope(self, envelope):
        for item in envelope.items:
            event = item.get_event()
            if event is not None:
                self.events.append(event)

    def flush(self, timeout, callback=None):
        self.flush_timeouts.append(timeout)

    def kill(self):
        self.closed = True


@pytest.fixture
def sdk_clients(monkeypatch):
    original = sentry_sdk.Client
    clients = []

    def in_memory_client(**options):
        client = original(**options, transport=MemoryTransport)
        clients.append(client)
        return client

    monkeypatch.setattr(sentry_sdk, "Client", in_memory_client)
    return clients


def failing_forecast(*args):
    raise RuntimeError("secret-exception-message")


def service_factory(settings):
    return SimpleNamespace(
        closed=False,
        close=lambda: None,
        future_forecast=failing_forecast,
        forecast=failing_forecast,
    )


def configured_app(**changes):
    settings = replace(
        Settings.from_env(),
        sentry_dsn="https://public@example.invalid/1",
        sentry_environment="test",
        **changes,
    )
    return create_app(settings, service_factory=service_factory)


def test_disabled_reporter_does_not_import_sdk_or_create_transport(monkeypatch, sdk_clients):
    monkeypatch.setenv("SENTRY_DSN", "  ")
    original_import = builtins.__import__

    def guarded_import(name, *args, **kwargs):
        if name == "sentry_sdk":
            pytest.fail("Disabled error reporting imported the SDK")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)
    application = create_app(service_factory=service_factory)
    assert application.state.runtime.reporter is None
    with TestClient(application) as client:
        assert application.state.runtime.reporter is None
        response = client.get("/api/forecast?date=2024-12-31&hour=12")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert len(response.headers["X-Request-ID"]) == 32
    assert sdk_clients == []


def test_capture_is_once_correlated_private_and_does_not_change_global_client(sdk_clients):
    original_global_client = sentry_sdk.Scope.get_global_scope().client
    application = configured_app()
    # The factory itself does not create a transport; resources start in lifespan.
    assert sdk_clients == []
    with sentry_sdk.new_scope() as unrelated_scope:
        unrelated_client = Client(
            dsn="", default_integrations=False, auto_enabling_integrations=False
        )
        unrelated_scope.set_client(unrelated_client)
        unrelated_scope.set_user({"email": "private-scope-user@example.com"})
        unrelated_scope.set_extra("private_scope_data", "private-scope-extra")
        unrelated_scope.set_tag("private_scope_tag", "private-scope-tag-value")
        with TestClient(application) as client:
            response = client.post(
                "/api/forecast/future?token=private-query-value",
                json={"start": "2025-01-02T03:04:05", "horizon": 13, "temperature": [17.12345]},
                headers={
                    "Authorization": "Bearer private-auth-value",
                    "Cookie": "session=private-cookie-value",
                    "X-Request-ID": "private-user-request-id",
                },
            )
            assert response.status_code == 500
            assert response.json() == {"detail": "Internal server error"}
            sdk_client = sdk_clients[0]
            transport = sdk_client.transport
            assert len(transport.events) == 1
            event = transport.events[0]
            assert event["tags"] == {
                "request_id": response.headers["X-Request-ID"],
                "method": "POST",
                "route": "/api/forecast/future",
            }
            exception = event["exception"]["values"][0]
            assert exception["type"] == "RuntimeError"
            frames = exception["stacktrace"]["frames"]
            assert any(frame["module"] == "backend.main" for frame in frames)
            assert all("vars" not in frame and "context_line" not in frame for frame in frames)
            for field in ("request", "user", "extra", "breadcrumbs", "contexts"):
                assert field not in event
            event_json = json.dumps(event, default=str)
            for private_value in (
                "secret-exception-message",
                "private-query-value",
                "2025-01-02T03:04:05",
                "17.12345",
                "private-auth-value",
                "private-cookie-value",
                "private-user-request-id",
                "private-scope-user",
                "private-scope-extra",
                "private-scope-tag-value",
                str(Settings.from_env().root),
            ):
                assert private_value not in event_json
            assert sdk_client.integrations == {}
            assert not sdk_client.options["data_collection"]["user_info"]
            assert sdk_client.options["traces_sample_rate"] == 0
            assert sdk_client.options["profiles_sample_rate"] == 0
            assert not sdk_client.options["enable_metrics"]
            assert not sdk_client.options["enable_logs"]
            assert sentry_sdk.Scope.get_global_scope().client is original_global_client
            assert sentry_sdk.get_client() is unrelated_client
        unrelated_client.close()
    assert transport.closed
    assert transport.flush_timeouts == [1.0]
    assert application.state.runtime.reporter is None


def test_route_parameters_are_not_sent_and_expected_errors_are_not_reported(sdk_clients):
    application = configured_app()

    @application.get("/api/crash/{account}")
    def crash(account: str):
        raise RuntimeError(account)

    with TestClient(application) as client:
        assert client.get("/not-found/private-user").status_code == 404
        assert client.post("/api/forecast/future", json={"start": "not-a-date"}).status_code == 422
        # Missing resources are a controlled readiness state, not an exception event.
        application.state.runtime.service = None
        assert client.get("/api/health").status_code == 503
        assert sdk_clients[0].transport.events == []
        response = client.get("/api/crash/private-user@example.com?key=private-api-key")
        event = sdk_clients[0].transport.events[0]
        assert event["transaction"] == "/api/crash/{account}"
        assert event["tags"]["request_id"] == response.headers["X-Request-ID"]
        assert "private-user" not in json.dumps(event, default=str)
        assert "private-api-key" not in json.dumps(event, default=str)


def test_two_applications_keep_transports_and_shutdown_independent(sdk_clients):
    first, second = configured_app(), configured_app()
    with TestClient(second) as second_client:
        with TestClient(first) as first_client:
            assert len(sdk_clients) == 2
            assert first.state.runtime.reporter is not second.state.runtime.reporter
            first_client.get("/api/forecast?date=2024-12-31&hour=12")
            assert sdk_clients[0].transport.events == []
            assert len(sdk_clients[1].transport.events) == 1
            first_transport, second_transport = sdk_clients[1].transport, sdk_clients[0].transport
        assert first_transport.closed
        assert not second_transport.closed
        second_client.get("/api/forecast?date=2024-12-31&hour=12")
        assert len(sdk_clients[0].transport.events) == 1
    assert second_transport.closed


@pytest.mark.parametrize("failure", ["missing_sdk", "invalid_dsn"])
def test_optional_reporter_initialization_failure_keeps_api_available(monkeypatch, caplog, failure):
    settings = replace(Settings.from_env(), sentry_dsn="private-invalid-dsn")
    if failure == "missing_sdk":
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "sentry_sdk":
                raise ModuleNotFoundError("secret-module-path")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", guarded_import)
    monkeypatch.setattr("backend.main.logger.propagate", True)
    with TestClient(create_app(settings, service_factory=service_factory)) as client:
        assert client.get("/api/live").json() == {"status": "alive"}
        assert client.get("/api/forecast?date=2024-12-31&hour=12").status_code == 500
    warning = next(
        record for record in caplog.records if record.msg == "error_reporting_unavailable"
    )
    assert warning.exc_info is None
    assert "private-invalid-dsn" not in warning.getMessage()
    assert "secret-module-path" not in warning.getMessage()


def test_transport_failure_never_replaces_original_safe_response_or_blocks_shutdown(monkeypatch):
    class BrokenReporter:
        def __init__(self):
            self.closed = False

        def capture_exception(self, *args, **kwargs):
            raise RuntimeError("private-transport-credentials")

        def close(self):
            self.closed = True
            raise RuntimeError("private-shutdown-error")

    reporter = BrokenReporter()
    monkeypatch.setattr("backend.main.create_error_reporter", lambda settings: reporter)
    application = configured_app()
    with TestClient(application) as client:
        response = client.get("/api/forecast?date=2024-12-31&hour=12")
        assert response.status_code == 500
        assert response.json() == {"detail": "Internal server error"}
        assert client.get("/api/live").status_code == 200
    assert reporter.closed
    assert application.state.runtime.reporter is None


def test_settings_hide_dsn_and_normalize_empty_environment(monkeypatch):
    monkeypatch.setenv("SENTRY_DSN", "  https://private-public-key@example.invalid/1 ")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", " ")
    settings = Settings.from_env()
    assert settings.sentry_dsn == "https://private-public-key@example.invalid/1"
    assert settings.sentry_environment == "production"
    assert "private-public-key" not in repr(settings)
    assert create_error_reporter(replace(settings, sentry_dsn=None)) is None


def test_forecast_resource_shutdown_failure_still_closes_reporter_and_clears_state(sdk_clients):
    def broken_close():
        raise RuntimeError("forecast-resource-close-failed")

    def broken_service_factory(settings):
        return SimpleNamespace(closed=False, close=broken_close)

    application = create_app(
        replace(Settings.from_env(), sentry_dsn="https://public@example.invalid/1"),
        service_factory=broken_service_factory,
    )
    with pytest.raises(RuntimeError, match="forecast-resource-close-failed"):
        with TestClient(application) as client:
            transport = sdk_clients[0].transport
            assert client.get("/api/live").status_code == 200
    assert transport.closed
    assert application.state.runtime.service is None
    assert application.state.runtime.reporter is None
    assert application.state.runtime.error_code == "not_initialized"
