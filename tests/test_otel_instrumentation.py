from pathlib import Path


TELEMETRY_PATH = Path(__file__).resolve().parent.parent / "app" / "telemetry.py"


def _source() -> str:
    return TELEMETRY_PATH.read_text()


def test_fastapi_instrumentor_import():
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    assert FastAPIInstrumentor is not None


def test_ext_asgi_raises_import_error():
    try:
        import opentelemetry.ext.asgi  # noqa: F401
        assert False, "opentelemetry.ext.asgi should not be importable"
    except (ImportError, ModuleNotFoundError):
        pass


def test_telemetry_uses_instrumentation_namespace():
    src = _source()
    assert "opentelemetry.instrumentation.fastapi" in src
    assert "opentelemetry.instrumentation.sqlalchemy" in src
    assert "opentelemetry.instrumentation.redis" in src
    assert "opentelemetry.ext" not in src


def test_histogram_exists_with_correct_name_and_buckets():
    src = _source()
    assert 'name="http.server.request.duration"' in src
    assert "unit=" in src
    expected_buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
    for bucket in expected_buckets:
        assert str(bucket) in src


def test_counter_exists_with_correct_name():
    src = _source()
    assert 'name="http.server.request.count"' in src


def test_counter_labels_semantic_conventions():
    from app.telemetry import (
        ATTR_HTTP_REQUEST_METHOD,
        ATTR_URL_PATH,
        ATTR_HTTP_RESPONSE_STATUS_CODE,
    )

    assert ATTR_HTTP_REQUEST_METHOD == "http.request.method"
    assert ATTR_URL_PATH == "url.path"
    assert ATTR_HTTP_RESPONSE_STATUS_CODE == "http.response.status_code"


def test_otlp_grpc_exporter_import():
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter

    assert OTLPSpanExporter is not None
    assert OTLPMetricExporter is not None


def test_batch_span_processor_configured():
    src = _source()
    assert "BatchSpanProcessor" in src
    assert "max_queue_size=2048" in src
    assert "schedule_delay_millis=5000" in src
    assert "export_timeout_millis=30000" in src


def test_resource_attributes():
    src = _source()
    assert '"service.name"' in src
    assert '"service.version"' in src
    assert '"deployment.environment"' in src
    assert '"1.0.0"' in src
    assert '"dev"' in src


def test_semantic_conventions_not_deprecated():
    src = _source()
    assert "http.request.method" in src
    assert "url.path" in src
    assert "http.response.status_code" in src
    assert '"http.method"' not in src
    assert '"http.url"' not in src
    assert '"http.status_code"' not in src


def test_gen_ai_attributes_defined():
    from app.telemetry import (
        ATTR_GEN_AI_SYSTEM,
        ATTR_GEN_AI_REQUEST_MODEL,
        ATTR_GEN_AI_USAGE_INPUT_TOKENS,
        ATTR_GEN_AI_USAGE_OUTPUT_TOKENS,
        ATTR_GEN_AI_TOOL_NAME,
    )

    assert ATTR_GEN_AI_SYSTEM == "gen_ai.system"
    assert ATTR_GEN_AI_REQUEST_MODEL == "gen_ai.request.model"
    assert ATTR_GEN_AI_USAGE_INPUT_TOKENS == "gen_ai.usage.input_tokens"
    assert ATTR_GEN_AI_USAGE_OUTPUT_TOKENS == "gen_ai.usage.output_tokens"
    assert ATTR_GEN_AI_TOOL_NAME == "gen_ai.tool.name"


def test_deprecated_attributes_not_used():
    src = _source()
    assert '"http.method"' not in src
    assert '"http.url"' not in src
    assert '"http.status_code"' not in src


def test_setup_telemetry_callable():
    from app.telemetry import setup_telemetry

    assert callable(setup_telemetry)


def test_otel_middleware_callable():
    from app.telemetry import otel_middleware

    assert callable(otel_middleware)


def test_atexit_shutdown_registered():
    src = _source()
    assert "atexit.register(_shutdown)" in src


def test_periodic_metric_reader_configured():
    src = _source()
    assert "PeriodicExportingMetricReader" in src
    assert "export_interval_millis=15000" in src
    assert "export_timeout_millis=10000" in src