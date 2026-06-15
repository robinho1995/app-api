from __future__ import annotations

import atexit
import logging
import time
from typing import Optional

from fastapi import FastAPI, Request, Response

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource

from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

logger = logging.getLogger(__name__)

_tracer_provider: Optional[TracerProvider] = None
_meter_provider: Optional[MeterProvider] = None
_meter: Optional[metrics.Meter] = None

_request_duration_hist: Optional[metrics.Histogram] = None
_request_count_counter: Optional[metrics.Counter] = None

ATTR_HTTP_REQUEST_METHOD = "http.request.method"
ATTR_URL_PATH = "url.path"
ATTR_HTTP_RESPONSE_STATUS_CODE = "http.response.status_code"
ATTR_DB_SYSTEM = "db.system"
ATTR_DB_STATEMENT = "db.statement"

ATTR_GEN_AI_SYSTEM = "gen_ai.system"
ATTR_GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
ATTR_GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
ATTR_GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
ATTR_GEN_AI_TOOL_NAME = "gen_ai.tool.name"


def setup_telemetry(
    app_name: str = "app-api",
    endpoint: str = "http://otel-collector:4317",
    app: Optional[FastAPI] = None,
) -> None:
    global _tracer_provider, _meter_provider, _meter
    global _request_duration_hist, _request_count_counter

    resource = Resource.create(
        {
            "service.name": app_name,
            "service.version": "1.0.0",
            "deployment.environment": "dev",
        }
    )

    try:
        otlp_span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        _tracer_provider = TracerProvider(resource=resource)
        _tracer_provider.add_span_processor(
            BatchSpanProcessor(
                otlp_span_exporter,
                max_queue_size=2048,
                schedule_delay_millis=5000,
                export_timeout_millis=30000,
            )
        )
        trace.set_tracer_provider(_tracer_provider)
        logger.info("TracerProvider configurado — endpoint=%s", endpoint)
    except Exception as exc:
        logger.error("Falha ao configurar TracerProvider: %s", exc)

    try:
        otlp_metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=True)
        metric_reader = PeriodicExportingMetricReader(
            otlp_metric_exporter,
            export_interval_millis=15000,
            export_timeout_millis=10000,
        )
        _meter_provider = MeterProvider(resource=resource, readers=[metric_reader])
        metrics.set_meter_provider(_meter_provider)
        logger.info("MeterProvider configurado — endpoint=%s", endpoint)
    except Exception as exc:
        logger.error("Falha ao configurar MeterProvider: %s", exc)

    _meter = metrics.get_meter(app_name, "1.0.0")

    _request_duration_hist = _meter.create_histogram(
        name="http.server.request.duration",
        description="Duration of HTTP server requests",
        unit="s",
        explicit_bucket_boundaries_advisory=[
            0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
        ],
    )

    _request_count_counter = _meter.create_counter(
        name="http.server.request.count",
        description="Total count of HTTP server requests",
    )

    try:
        SQLAlchemyInstrumentor().instrument()
        logger.info("SQLAlchemyInstrumentor habilitado")
    except Exception as exc:
        logger.error("Falha ao instrumentar SQLAlchemy: %s", exc)

    try:
        RedisInstrumentor().instrument()
        logger.info("RedisInstrumentor habilitado")
    except Exception as exc:
        logger.error("Falha ao instrumentar Redis: %s", exc)

    if app is not None:
        try:
            FastAPIInstrumentor.instrument_app(app)
            logger.info("FastAPIInstrumentor habilitado")
        except Exception as exc:
            logger.error("Falha ao instrumentar FastAPI: %s", exc)

    atexit.register(_shutdown)


def _shutdown() -> None:
    if _tracer_provider is not None:
        try:
            _tracer_provider.shutdown()
            logger.info("TracerProvider shutdown concluido")
        except Exception as exc:
            logger.error("Erro no shutdown do TracerProvider: %s", exc)

    if _meter_provider is not None:
        try:
            _meter_provider.shutdown()
            logger.info("MeterProvider shutdown concluido")
        except Exception as exc:
            logger.error("Erro no shutdown do MeterProvider: %s", exc)


async def otel_middleware(request: Request, call_next) -> Response:
    start = time.perf_counter()

    response: Response = await call_next(request)

    duration_s = time.perf_counter() - start

    method = request.method
    path = request.url.path
    status_code = str(response.status_code)

    attributes = {
        ATTR_HTTP_REQUEST_METHOD: method,
        ATTR_URL_PATH: path,
        ATTR_HTTP_RESPONSE_STATUS_CODE: status_code,
    }

    if _request_duration_hist is not None:
        try:
            _request_duration_hist.record(duration_s, attributes=attributes)
        except Exception as exc:
            logger.error("Erro ao registrar histogram: %s", exc)

    if _request_count_counter is not None:
        try:
            _request_count_counter.add(1, attributes=attributes)
        except Exception as exc:
            logger.error("Erro ao incrementar counter: %s", exc)

    return response