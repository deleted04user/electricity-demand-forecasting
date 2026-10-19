"""Opt-in, per-application error aggregation with a deliberately small event schema.

The SDK is imported and its transport created only when the application starts
with a DSN. We never bind a process-wide Sentry client or enable integrations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from .settings import Settings

if TYPE_CHECKING:
    from sentry_sdk import Client


class ErrorReporter(Protocol):
    def capture_exception(
        self, error: Exception, *, request_id: str, method: str, route: str
    ) -> None: ...

    def close(self) -> None: ...


class SentryReporter:
    def __init__(self, client: Client) -> None:
        self.client = client

    def capture_exception(
        self, error: Exception, *, request_id: str, method: str, route: str
    ) -> None:
        # Construct an allowlist rather than relying on SDK scrubbing of arbitrary
        # exceptions: exception messages, locals and filesystem paths can be secrets.
        frames: list[dict[str, Any]] = []
        traceback = error.__traceback__
        while traceback is not None:
            module = traceback.tb_frame.f_globals.get("__name__", "")
            if isinstance(module, str) and module.startswith("backend."):
                frames.append(
                    {
                        "filename": module.replace(".", "/") + ".py",
                        "module": module,
                        "function": traceback.tb_frame.f_code.co_name,
                        "lineno": traceback.tb_lineno,
                        "in_app": True,
                    }
                )
            traceback = traceback.tb_next
        # Passing no scope keeps other applications' user data and breadcrumbs out.
        # Passing no exception hint prevents SDK processors from inspecting locals.
        self.client.capture_event(
            {
                "level": "error",
                "exception": {
                    "values": [
                        {
                            "type": type(error).__name__,
                            "value": "Unexpected API error (message withheld)",
                            "stacktrace": {"frames": frames},
                            "mechanism": {"type": "electricity_api", "handled": False},
                        }
                    ]
                },
                "tags": {"request_id": request_id, "method": method, "route": route},
                "transaction": route,
            }
        )

    def close(self) -> None:
        self.client.close(timeout=1.0)


def create_error_reporter(settings: Settings) -> ErrorReporter | None:
    if not settings.sentry_dsn:
        return None

    from sentry_sdk import Client

    return SentryReporter(
        Client(
            dsn=settings.sentry_dsn,
            environment=settings.sentry_environment,
            release="electricity-demand-forecasting@0.3.1",
            server_name="electricity-api",
            debug=False,
            spotlight=False,
            default_integrations=False,
            auto_enabling_integrations=False,
            data_collection={
                "user_info": False,
                "cookies": {"mode": "off"},
                "http_headers": {"request": {"mode": "off"}},
                "http_bodies": [],
                "url_query_params": {"mode": "off"},
                "stack_frame_variables": False,
                "frame_context_lines": 0,
            },
            max_request_body_size="never",
            include_local_variables=False,
            include_source_context=False,
            attach_stacktrace=False,
            max_breadcrumbs=0,
            traces_sample_rate=0.0,
            propagate_traces=False,
            profiles_sample_rate=0.0,
            profile_session_sample_rate=0.0,
            auto_session_tracking=False,
            send_client_reports=False,
            enable_logs=False,
            enable_metrics=False,
            enable_backpressure_handling=False,
            shutdown_timeout=1.0,
            transport_queue_size=100,
        )
    )
