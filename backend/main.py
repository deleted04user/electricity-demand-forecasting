"""FastAPI adapter. Resources belong to each application's managed lifespan."""

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Annotated, Any, cast

from fastapi import Depends, FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .api_models import (
    DemandAnalysisResponse,
    ForecastResponse,
    FutureRequest,
    FutureResponse,
    HealthResponse,
    MetaResponse,
    ModelPerformanceResponse,
    OverviewResponse,
    UnavailableResponse,
)
from .error_reporting import ErrorReporter, create_error_reporter
from .logging_config import log_request, logger
from .service import ForecastError, ForecastService
from .settings import Settings


@dataclass
class RuntimeState:
    service: ForecastService | None = None
    error_code: str = "not_initialized"
    reporter: ErrorReporter | None = None


def runtime(request: Request) -> ForecastService:
    state = cast(RuntimeState, request.app.state.runtime)
    if state.service is None or state.service.closed:
        raise ForecastError(503, state.error_code)
    return state.service


Service = Annotated[ForecastService, Depends(runtime)]


def create_app(
    settings: Settings | None = None,
    service_factory: Callable[[Settings], ForecastService] = ForecastService.load,
) -> FastAPI:
    configuration = settings if settings is not None else Settings.from_env()
    state = RuntimeState()

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            state.reporter = create_error_reporter(configuration)
        except Exception as exc:
            # Optional telemetry must never prevent forecasting or expose the DSN.
            logger.warning("error_reporting_unavailable", extra={"error_type": type(exc).__name__})
        try:
            state.service = service_factory(configuration)
            state.error_code = ""
        except Exception as exc:
            state.error_code = "resource_initialization_failed"
            logger.exception(
                "resource_initialization_failed", extra={"error_type": type(exc).__name__}
            )
        try:
            yield
        finally:
            try:
                if state.service is not None:
                    state.service.close()
            finally:
                state.service = None
                state.error_code = "not_initialized"
                if state.reporter is not None:
                    try:
                        state.reporter.close()
                    except Exception as exc:
                        logger.warning(
                            "error_reporting_shutdown_failed",
                            extra={"error_type": type(exc).__name__},
                        )
                    finally:
                        state.reporter = None

    async def request_logging(request: Request, call_next: RequestResponseEndpoint) -> Response:
        return await log_request(request, call_next, state.reporter)

    application = FastAPI(
        title="Electricity Demand Forecasting API", version="0.3.0", lifespan=lifespan
    )
    application.state.runtime = state
    application.middleware("http")(request_logging)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(configuration.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.exception_handler(ForecastError)
    async def forecast_error(request: Request, exc: ForecastError) -> JSONResponse:
        if exc.status_code == 503:
            return JSONResponse(
                status_code=503,
                content=UnavailableResponse(
                    detail="Forecast resources are unavailable", error_code=exc.detail
                ).model_dump(),
            )
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})

    unavailable: dict[int | str, dict[str, Any]] = {
        503: {
            "model": UnavailableResponse,
            "description": "Required model/data failed initialization or the application lifespan has not started.",
        }
    }

    @application.get("/api/live")
    def live() -> dict[str, str]:
        """Liveness only; use /api/health for model/data readiness."""
        return {"status": "alive"}

    @application.get("/api/health", response_model=HealthResponse, responses=unavailable)
    def health(service: Service) -> dict[str, Any]:
        return service.health()

    @application.get("/api/overview", response_model=OverviewResponse, responses=unavailable)
    def overview(service: Service) -> dict[str, Any]:
        return service.overview()

    @application.get(
        "/api/demand-analysis", response_model=DemandAnalysisResponse, responses=unavailable
    )
    def demand_analysis(service: Service) -> dict[str, Any]:
        return service.demand_analysis()

    @application.get(
        "/api/model-performance", response_model=ModelPerformanceResponse, responses=unavailable
    )
    def model_performance(service: Service) -> dict[str, Any]:
        return service.model_performance()

    @application.get("/api/forecast", response_model=ForecastResponse, responses=unavailable)
    def forecast(
        service: Service, date: str, hour: int = Query(..., ge=0, le=23)
    ) -> dict[str, Any]:
        return service.forecast(date, hour)

    @application.get("/api/meta", response_model=MetaResponse, responses=unavailable)
    def meta(service: Service) -> dict[str, Any]:
        return service.meta()

    @application.post("/api/forecast/future", response_model=FutureResponse, responses=unavailable)
    def future_forecast(service: Service, payload: FutureRequest) -> dict[str, Any]:
        return service.future_forecast(payload)

    return application


app = create_app()
