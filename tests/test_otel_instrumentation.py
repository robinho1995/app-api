from __future__ import annotations

import inspect

import pytest


def test_fastapi_instrumentor_import_path():
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    assert FastAPIInstrumentor is not None


def test_deprecated_ext_asgi_raises_import_error():
    with pytest.raises(ImportError):
        from opentelemetry.ext.asgi import OpenTelemetryMiddleware  # noqa: F401


def test_telemetry_uses_instrumentation_namespace():
    import app.telemetry as telemetry_module

    source = inspect.getsource(telemetry_module)
    assert "opentelemetry.instrumentation.fastapi" in source
    assert "opentelemetry.instrumentation.sqlalchemy" in source
    assert "opentelemetry.instrumentation.redis" in source
    assert "opentelemetry.ext" not in source


def test_histogram_name_and_buckets():
    from app.telemetry import REQUEST_DURATION_HISTOGRAM, DURATION_BUCKETS

    assert REQUEST_DURATION_HISTOGRAM == "http.server.request.duration"
    assert DURATION_BUCKETS == [
        0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0
    ]


def test_counter_name():
    from app.telemetry import REQUEST_COUNT_COUNTER

    assert REQUEST_COUNT_COUNTER == "http.server.request.count"


def test_counter_labels_use_semantic_conventions():
    from app.telemetry import SEMANTIC_CONVENTION_ATTRS

    assert "http.request.method" in SEMANTIC_CONVENTION_ATTRS
    assert "url.path" in SEMANTIC_CONVENTION_ATTRS
    assert "http.response.status_code" in SEMANTIC_CONVENTION_ATTRS


def test_otlp_grpc_exporter_import():
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    assert OTLPSpanExporter is not None
    assert OTLPMetricExporter is not None


def test_batch_span_processor_configured():
    import app.telemetry as telemetry_module

    source = inspect.getsource(telemetry_module)
    assert "BatchSpanProcessor" in source
    assert "max_queue_size=2048" in source
    assert "schedule_delay_millis=5000" in source
    assert "export_timeout_millis=30000" in source


def test_resource_attributes():
    import app.telemetry as telemetry_module

    source = inspect.getsource(telemetry_module)
    assert r'"service.name": app_name' in source or '"service.name"' in source
    assert r'"service.version": service_version' in source or '"service.version"' in source
    assert '"deployment.environment"' in source


def test_semantic_conventions_not_deprecated():
    import app.telemetry as telemetry_module

    source = inspect.getsource(telemetry_module)
    assert "http.request.method" in source
    assert "url.path" in source
    assert "http.response.status_code" in source


def test_deprecated_attributes_not_used():
    import app.telemetry as telemetry_module

    source = inspect.getsource(telemetry_module)
    assert '"http.method"' not in source
    assert '"http.url"' not in source
    assert '"http.status_code"' not in source


def test_gen_ai_attributes_defined():
    from app.telemetry import GEN_AI_ATTRIBUTES

    assert "gen_ai.system" in GEN_AI_ATTRIBUTES
    assert "gen_ai.request.model" in GEN_AI_ATTRIBUTES
    assert "gen_ai.usage.input_tokens" in GEN_AI_ATTRIBUTES
    assert "gen_ai.usage.output_tokens" in GEN_AI_ATTRIBUTES
    assert "gen_ai.tool.name" in GEN_AI_ATTRIBUTES


def test_deprecated_attrs_not_in_semantic_conventions():
    from app.telemetry import DEPRECATED_ATTRS

    assert "http.method" in DEPRECATED_ATTRS
    assert "http.url" in DEPRECATED_ATTRS
    assert "http.status_code" in DEPRECATED_ATTRS