from __future__ import annotations

import atexit
import logging
import time
from typing import Optional

from fastapi import FastAPI, Request
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import ExplicitBucketHistogramAggregation, PeriodicExportingMetricReader
from opentelemetry.sdk.metrics.view import View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

logger = logging.getLogger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None

REQUEST_DURATION_HISTOGRAM = "http.server.request.duration"
REQUEST_COUNT_COUNTER = "http.server.request.count"

DURATION_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]

GEN_AI_ATTRIBUTES = {
    "gen_ai.system",
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.tool.name",
}

SEMANTIC_CONVENTION_ATTRS = {
    "http.request.method",
    "url.path",
    "http.response.status_code",
}

DEPRECATED_ATTRS = {
    "http.method",
    "http.url",
    "http.status_code",
}


def setup_telemetry(
    app: Optional[FastAPI] = None,
    app_name: str = "app-api",
    endpoint: str = "http://localhost:4317",
    service_version: str = "1.0.0",
    deployment_environment: str = "dev",
) -> None:
    global _tracer_provider, _meter_provider

    resource = Resource.create(
        {
            "service.name": app_name,
            "service.version": service_version,
            "deployment.environment": deployment_environment,
        }
    )

    try:
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        span_processor = BatchSpanProcessor(
            span_exporter,
            max_queue_size=2048,
            schedule_delay_millis=5000,
            export_timeout_millis=30000,
        )
        _tracer_provider = TracerProvider(resource=resource)
        _tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(_tracer_provider)
        logger.info("TracerProvider configured with OTLP gRPC exporter at %s", endpoint)
    except Exception as exc:
        logger.error("Failed to configure TracerProvider: %s", exc)

    try:
        duration_view = View(
            instrument_type=metrics.Histogram,
            instrument_name=REQUEST_DURATION_HISTOGRAM,
            aggregation=ExplicitBucketHistogramAggregation(boundaries=DURATION_BUCKETS),
        )
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=15000,
            export_timeout_millis=10000,
        )
        _meter_provider = MeterProvider(
            resource=resource,
            metric_readers=[metric_reader],
            views=[duration_view],
        )
        metrics.set_meter_provider(_meter_provider)
        logger.info("MeterProvider configured with OTLP gRPC exporter at %s", endpoint)
    except Exception as exc:
        logger.error("Failed to configure MeterProvider: %s", exc)

    try:
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemy instrumentation enabled")
    except Exception as exc:
        logger.error("Failed to instrument SQLAlchemy: %s", exc)

    try:
        RedisInstrumentor().instrument()
        logger.info("Redis instrumentation enabled")
    except Exception as exc:
        logger.error("Failed to instrument Redis: %s", exc)

    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI instrumentation enabled")
        except Exception as exc:
            logger.error("Failed to instrument FastAPI app: %s", exc)

    _register_otel_middleware(app)

    atexit.register(_shutdown_telemetry)


def _register_otel_middleware(app: Optional[FastAPI]) -> None:
    if app is None:
        return

    meter = metrics.get_meter("app-api")

    request_duration = meter.create_histogram(
        name=REQUEST_DURATION_HISTOGRAM,
        description="Duration of HTTP server requests in seconds",
        unit="s",
    )

    request_count = meter.create_counter(
        name=REQUEST_COUNT_COUNTER,
        description="Total number of HTTP server requests",
    )

    @app.middleware("http")
    async def otel_metrics_middleware(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_s = time.perf_counter() - start

        attributes = {
            "http.request.method": request.method,
            "url.path": request.url.path,
            "http.response.status_code": response.status_code,
        }

        request_duration.record(duration_s, attributes=attributes)
        request_count.add(1, attributes=attributes)

        return response


def _shutdown_telemetry() -> None:
    try:
        if _tracer_provider is not None:
            _tracer_provider.shutdown()
            logger.info("TracerProvider shutdown complete")
    except Exception as exc:
        logger.error("Error shutting down TracerProvider: %s", exc)

    try:
        if _meter_provider is not None:
            _meter_provider.shutdown()
            logger.info("MeterProvider shutdown complete")
    except Exception as exc:
        logger.error("Error shutting down MeterProvider: %s", exc)
