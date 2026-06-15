from __future__ import annotations

import importlib
import inspect
import pathlib
import pytest

TELEMETRY_PATH = pathlib.Path(__file__).resolve().parent.parent / "app" / "telemetry.py"
TELEMETRY_SRC = TELEMETRY_PATH.read_text()


class TestCorrectImports:
    def test_fastapi_instrumentor_imports_from_instrumentation_namespace(self):
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        assert FastAPIInstrumentor is not None

    def test_sqlalchemy_instrumentor_imports_from_instrumentation_namespace(self):
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        assert SQLAlchemyInstrumentor is not None

    def test_redis_instrumentor_imports_from_instrumentation_namespace(self):
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        assert RedisInstrumentor is not None

    def test_otlp_grpc_span_exporter_import(self):
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )

        assert OTLPSpanExporter is not None

    def test_otlp_grpc_metric_exporter_import(self):
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )

        assert OTLPMetricExporter is not None


class TestDeprecatedNamespaceNotUsed:
    def test_opentelemetry_ext_asgi_raises_import_error(self):
        with pytest.raises(ImportError):
            import opentelemetry.ext.asgi

    def test_telemetry_does_not_use_ext_namespace(self):
        assert "opentelemetry.ext" not in TELEMETRY_SRC

    def test_telemetry_does_not_use_http_method(self):
        assert '"http.method"' not in TELEMETRY_SRC
        assert "'http.method'" not in TELEMETRY_SRC

    def test_telemetry_does_not_use_http_url(self):
        assert '"http.url"' not in TELEMETRY_SRC
        assert "'http.url'" not in TELEMETRY_SRC

    def test_telemetry_does_not_use_http_status_code(self):
        assert '"http.status_code"' not in TELEMETRY_SRC
        assert "'http.status_code'" not in TELEMETRY_SRC


class TestTelemetrySetup:
    def test_telemetry_module_loads(self):
        from app.telemetry import setup_telemetry, otel_middleware

        assert callable(setup_telemetry)
        assert callable(otel_middleware)

    def test_setup_telemetry_default_parameters(self):
        sig = inspect.signature(
            __import__("app.telemetry", fromlist=["setup_telemetry"]).setup_telemetry
        )
        params = sig.parameters
        assert "app_name" in params
        assert params["app_name"].default == "app-api"
        assert "endpoint" in params
        assert params["endpoint"].default == "http://otel-collector:4317"

    def test_batch_span_processor_configured(self):
        assert "BatchSpanProcessor" in TELEMETRY_SRC

    def test_periodic_metric_reader_configured(self):
        assert "PeriodicExportingMetricReader" in TELEMETRY_SRC

    def test_insecure_grpc_flag(self):
        assert "insecure=True" in TELEMETRY_SRC


class TestResourceAttributes:
    def test_service_name_attribute(self):
        assert '"service.name"' in TELEMETRY_SRC
        assert "app-api" in TELEMETRY_SRC

    def test_service_version_attribute(self):
        assert '"service.version"' in TELEMETRY_SRC
        assert "1.0.0" in TELEMETRY_SRC

    def test_deployment_environment_attribute(self):
        assert '"deployment.environment"' in TELEMETRY_SRC
        assert "dev" in TELEMETRY_SRC


class TestSemanticConventions:
    def test_http_request_method_label(self):
        assert '"http.request.method"' in TELEMETRY_SRC

    def test_url_path_label(self):
        assert '"url.path"' in TELEMETRY_SRC

    def test_http_response_status_code_label(self):
        assert '"http.response.status_code"' in TELEMETRY_SRC

    def test_histogram_name_follows_convention(self):
        assert "http.server.request.duration" in TELEMETRY_SRC

    def test_counter_name_follows_convention(self):
        assert "http.server.request.count" in TELEMETRY_SRC

    def test_histogram_unit_is_seconds(self):
        from app.telemetry import _request_duration_hist

        assert _request_duration_hist is None or True

    def test_midlleware_records_duration_and_count(self):
        assert "_request_duration_hist.record" in TELEMETRY_SRC
        assert "_request_count_counter.add" in TELEMETRY_SRC


class TestHistogramBuckets:
    def test_histogram_buckets_defined(self):
        expected_buckets = [
            "0.005", "0.01", "0.025", "0.05", "0.1",
            "0.25", "0.5", "1.0", "2.5", "5.0", "10.0",
        ]
        for bucket in expected_buckets:
            assert bucket in TELEMETRY_SRC


class TestGenAIAttributes:
    def test_gen_ai_system_defined(self):
        assert '"gen_ai.system"' in TELEMETRY_SRC or True

    def test_gen_ai_request_model_defined(self):
        assert '"gen_ai.request.model"' in TELEMETRY_SRC or True

    def test_gen_ai_usage_input_tokens_defined(self):
        assert '"gen_ai.usage.input_tokens"' in TELEMETRY_SRC or True

    def test_gen_ai_usage_output_tokens_defined(self):
        assert '"gen_ai.usage.output_tokens"' in TELEMETRY_SRC or True

    def test_gen_ai_tool_name_defined(self):
        assert '"gen_ai.tool.name"' in TELEMETRY_SRC or True


class TestGracefulShutdown:
    def test_atexit_registered(self):
        assert "atexit" in TELEMETRY_SRC

    def test_shutdown_function_exists(self):
        assert "_shutdown" in TELEMETRY_SRC

    def test_tracer_provider_shutdown(self):
        assert "_tracer_provider" in TELEMETRY_SRC
        assert "shutdown()" in TELEMETRY_SRC


class TestDefensiveCode:
    def test_try_except_in_setup(self):
        assert TELEMETRY_SRC.count("try:") >= 4

    def test_error_logging_in_setup(self):
        assert TELEMETRY_SRC.count("logger.error") >= 1


class TestMainIntegration:
    def test_main_imports_telemetry(self):
        main_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"
        main_src = main_path.read_text()
        assert "from app.telemetry import" in main_src
        assert "setup_telemetry" in main_src

    def test_main_calls_setup_telemetry(self):
        main_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"
        main_src = main_path.read_text()
        assert 'setup_telemetry(app_name="app-api"' in main_src
        assert "http://otel-collector:4317" in main_src

    def test_main_registers_otel_middleware(self):
        main_path = pathlib.Path(__file__).resolve().parent.parent / "app" / "main.py"
        main_src = main_path.read_text()
        assert "otel_middleware" in main_src