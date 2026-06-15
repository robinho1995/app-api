from __future__ import annotations

import inspect
import pathlib

import pytest


TELEMETRY_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "telemetry.py"
MAIN_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"


def _read_telemetry_source() -> str:
    return TELEMETRY_PATH.read_text()


def _read_main_source() -> str:
    return MAIN_PATH.read_text()


class TestCorrectImports:
    def test_fastapi_instrumentor_from_instrumentation_namespace(self):
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        assert FastAPIInstrumentor is not None

    def test_ext_asgi_import_raises_error(self):
        with pytest.raises(ImportError):
            import opentelemetry.ext.asgi  # noqa: F401

    def test_telemetry_uses_instrumentation_not_ext(self):
        source = _read_telemetry_source()
        assert "opentelemetry.instrumentation.fastapi" in source
        assert "opentelemetry.instrumentation.sqlalchemy" in source
        assert "opentelemetry.instrumentation.redis" in source
        assert "opentelemetry.ext." not in source

    def test_otlp_grpc_exporter_from_correct_module(self):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        assert OTLPSpanExporter is not None
        assert OTLPMetricExporter is not None

    def test_telemetry_imports_otlp_grpc_not_http(self):
        source = _read_telemetry_source()
        assert "opentelemetry.exporter.otlp.proto.grpc" in source
        assert "opentelemetry.exporter.otlp.proto.http" not in source


class TestSemanticConventions:
    def test_histogram_name_correct(self):
        source = _read_telemetry_source()
        assert '"http.server.request.duration"' in source
        assert '"http.server.request.latency"' not in source

    def test_counter_name_correct(self):
        source = _read_telemetry_source()
        assert '"http.server.request.count"' in source

    def test_label_http_request_method(self):
        source = _read_telemetry_source()
        assert '"http.request.method"' in source
        assert '"http.method"' not in source

    def test_label_url_path(self):
        source = _read_telemetry_source()
        assert '"url.path"' in source
        assert '"http.url"' not in source

    def test_label_http_response_status_code(self):
        source = _read_telemetry_source()
        assert '"http.response.status_code"' in source
        assert '"http.status_code"' not in source

    def test_deprecated_labels_not_used(self):
        source = _read_telemetry_source()
        deprecated = ['"http.method"', '"http.url"', '"http.status_code"']
        for label in deprecated:
            assert label not in source, f"Deprecated label {label} found in telemetry.py"


class TestHistogramBuckets:
    def test_histogram_has_explicit_buckets(self):
        source = _read_telemetry_source()
        assert "explicit_bucket_boundaries" in source
        expected_buckets = [
            0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0,
        ]
        for bucket in expected_buckets:
            assert str(bucket) in source, f"Bucket {bucket} not found"

    def test_histogram_unit_is_seconds(self):
        source = _read_telemetry_source()
        assert '"s"' in source


class TestBatchSpanProcessor:
    def test_batch_span_processor_configured(self):
        source = _read_telemetry_source()
        assert "BatchSpanProcessor" in source
        assert "max_queue_size=2048" in source
        assert "schedule_delay_millis=5000" in source
        assert "export_timeout_millis=30000" in source


class TestPeriodicExportingMetricReader:
    def test_periodic_reader_configured(self):
        source = _read_telemetry_source()
        assert "PeriodicExportingMetricReader" in source
        assert "export_interval_millis=15000" in source
        assert "export_timeout_millis=10000" in source


class TestResourceAttributes:
    def test_service_name_attribute(self):
        source = _read_telemetry_source()
        assert '"service.name"' in source
        assert "app-api" in source

    def test_service_version_attribute(self):
        source = _read_telemetry_source()
        assert '"service.version"' in source

    def test_deployment_environment_attribute(self):
        source = _read_telemetry_source()
        assert '"deployment.environment"' in source


class TestGenAIAttributes:
    def test_gen_ai_system_defined(self):
        source = _read_telemetry_source()
        assert '"gen_ai.system"' in source

    def test_gen_ai_request_model_defined(self):
        source = _read_telemetry_source()
        assert '"gen_ai.request.model"' in source

    def test_gen_ai_usage_input_tokens_defined(self):
        source = _read_telemetry_source()
        assert '"gen_ai.usage.input_tokens"' in source

    def test_gen_ai_usage_output_tokens_defined(self):
        source = _read_telemetry_source()
        assert '"gen_ai.usage.output_tokens"' in source

    def test_gen_ai_tool_name_defined(self):
        source = _read_telemetry_source()
        assert '"gen_ai.tool.name"' in source


class TestSetupTelemetryFunction:
    def test_setup_telemetry_exists(self):
        from app.telemetry import setup_telemetry

        assert callable(setup_telemetry)

    def test_setup_telemetry_signature(self):
        from app.telemetry import setup_telemetry

        sig = inspect.signature(setup_telemetry)
        params = list(sig.parameters.keys())
        assert "app" in params
        assert "app_name" in params
        assert "endpoint" in params

    def test_setup_telemetry_default_app_name(self):
        from app.telemetry import setup_telemetry

        sig = inspect.signature(setup_telemetry)
        assert sig.parameters["app_name"].default == "app-api"

    def test_setup_telemetry_default_endpoint(self):
        from app.telemetry import setup_telemetry

        sig = inspect.signature(setup_telemetry)
        default_endpoint = sig.parameters["endpoint"].default
        assert "otel-collector.observability.svc.cluster.local" in default_endpoint
        assert "4317" in default_endpoint

    def test_main_calls_setup_telemetry(self):
        source = _read_main_source()
        assert "setup_telemetry" in source
        assert "app-api" in source


class TestAutoInstrumentation:
    def test_fastapi_instrumentor_used(self):
        source = _read_telemetry_source()
        assert "FastAPIInstrumentor" in source
        assert "instrument_app" in source

    def test_sqlalchemy_instrumentor_used(self):
        source = _read_telemetry_source()
        assert "SQLAlchemyInstrumentor" in source

    def test_redis_instrumentor_used(self):
        source = _read_telemetry_source()
        assert "RedisInstrumentor" in source


class TestGracefulShutdown:
    def test_atexit_registered(self):
        source = _read_telemetry_source()
        assert "atexit.register" in source

    def test_force_flush_in_shutdown(self):
        source = _read_telemetry_source()
        assert "force_flush" in source


class TestDefensiveCode:
    def test_try_except_in_setup(self):
        source = _read_telemetry_source()
        assert source.count("try:") >= 5

    def test_error_logging_in_setup(self):
        source = _read_telemetry_source()
        assert "logger.error" in source
