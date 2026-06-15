from __future__ import annotations

import atexit
import logging
import time
from typing import Optional
from fastapi import FastAPI, Request
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

logger = logging.getLogger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None
_request_duration_histogram: Optional[metrics.Histogram] = None
_request_count_counter: Optional[metrics.Counter] = None

HISTOGRAM_BUCKETS = [
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
]

GEN_AI_ATTRIBUTES = {
    "gen_ai.system": "openai",
    "gen_ai.request.model": "",
    "gen_ai.usage.input_tokens": 0,
    "gen_ai.usage.output_tokens": 0,
    "gen_ai.tool.name": "",
}


def _flush_telemetry() -> None:
    global _tracer_provider, _meter_provider
    try:
        if _tracer_provider is not None:
            _tracer_provider.force_flush()
            logger.info("TracerProvider flushed successfully")
    except Exception as exc:
        logger.error("Failed to flush TracerProvider: %s", exc)
    try:
        if _meter_provider is not None:
            _meter_provider.force_flush()
            logger.info("MeterProvider flushed successfully")
    except Exception as exc:
        logger.error("Failed to flush MeterProvider: %s", exc)


atexit.register(_flush_telemetry)


def setup_telemetry(
    app: Optional[FastAPI] = None,
    app_name: str = "app-api",
    endpoint: str = "http://otel-collector.observability.svc.cluster.local:4318",
    service_version: str = "1.0.0",
    deployment_environment: str = "dev",
) -> None:
    global _tracer_provider, _meter_provider
    global _request_duration_histogram, _request_count_counter

    resource = Resource.create(
        {
            "service.name": app_name,
            "service.version": service_version,
            "deployment.environment": deployment_environment,
        }
    )

    try:
        trace_exporter = OTLPSpanExporter(endpoint=f"{endpoint}/v1/traces")
        span_processor = BatchSpanProcessor(
            trace_exporter,
            max_queue_size=2048,
            schedule_delay_millis=5000,
            export_timeout_millis=30000,
        )
        _tracer_provider = TracerProvider(resource=resource)
        _tracer_provider.add_span_processor(span_processor)
        trace.set_tracer_provider(_tracer_provider)
        logger.info("TracerProvider configured with OTLP HTTP exporter at %s", endpoint)
    except Exception as exc:
        logger.error("Failed to configure TracerProvider: %s", exc)

    try:
        metric_exporter = OTLPMetricExporter(endpoint=f"{endpoint}/v1/metrics")
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter,
            export_interval_millis=15000,
            export_timeout_millis=10000,
        )
        _meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)
        logger.info("MeterProvider configured with OTLP HTTP exporter at %s", endpoint)
    except Exception as exc:
        logger.error("Failed to configure MeterProvider: %s", exc)

    try:
        meter = metrics.get_meter(app_name, service_version)

        _request_duration_histogram = meter.create_histogram(
            name="http.server.request.duration",
            description="Duration of HTTP server requests in seconds",
            unit="s",
            explicit_bucket_boundaries=HISTOGRAM_BUCKETS,
        )

        _request_count_counter = meter.create_counter(
            name="http.server.request.count",
            description="Total number of HTTP server requests",
        )

        logger.info("Metrics instruments created: http.server.request.duration, http.server.request.count")
    except Exception as exc:
        logger.error("Failed to create metrics instruments: %s", exc)

    try:
        SQLAlchemyInstrumentor().instrument(engine=None)
        logger.info("SQLAlchemy auto-instrumentation enabled")
    except Exception as exc:
        logger.error("Failed to instrument SQLAlchemy: %s", exc)

    try:
        RedisInstrumentor().instrument()
        logger.info("Redis auto-instrumentation enabled")
    except Exception as exc:
        logger.error("Failed to instrument Redis: %s", exc)

    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPI auto-instrumentation enabled")
        except Exception as exc:
            logger.error("Failed to instrument FastAPI: %s", exc)

        @app.middleware("http")
        async def otel_metrics_middleware(request: Request, call_next):
            start_time = time.perf_counter()
            response = await call_next(request)
            duration_s = time.perf_counter() - start_time

            if _request_duration_histogram is not None:
                try:
                    _request_duration_histogram.record(
                        duration_s,
                        {
                            "http.request.method": request.method,
                            "url.path": request.url.path,
                            "http.response.status_code": response.status_code,
                        },
                    )
                except Exception as exc:
                    logger.error("Failed to record histogram: %s", exc)

            if _request_count_counter is not None:
                try:
                    _request_count_counter.add(
                        1,
                        {
                            "http.request.method": request.method,
                            "url.path": request.url.path,
                            "http.response.status_code": response.status_code,
                        },
                    )
                except Exception as exc:
                    logger.error("Failed to increment counter: %s", exc)

            return response

    logger.info("Telemetry setup complete for %s", app_name)