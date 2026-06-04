# Security Agent Report

Generated: 2026-06-04T18:28:57.992176

Service: app-api
Environment: staging
Total findings: 14

## [P1] SonarQube:python:S8392
- Blast radius: HIGH — Binding to 0.0.0.0 exposes the API to all network interfaces, including external networks if not strictly firewalled, enabling direct RCE or data exfiltration attacks.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Application is bound to all network interfaces (0.0.0.0) instead of localhost, increasing attack surface.
- Remediation: Bind the FastAPI application specifically to 127.0.0.1 for internal-only access or configure a reverse proxy with strict firewall rules if external access is required.

## [P3] SonarQube:python:S3776
- Blast radius: LOW — High cognitive complexity in main.py increases maintenance risk and potential for logic bugs, but does not directly enable exploitation.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Function complexity (19) exceeds the threshold (15), making code hard to understand and test.
- Remediation: Refactor the function by extracting sub-logic into smaller, single-responsibility helper functions.

## [P3] SonarQube:python:S8396
- Blast radius: LOW — Missing default value in schema may cause unexpected behavior or validation errors, but limited to internal data processing.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/schemas.py
- Description: Optional field in Pydantic schema lacks an explicit default value, potentially causing validation issues.
- Remediation: Add an explicit default value (e.g., None or empty list) to the optional field definition.

## [P3] SonarQube:python:S7487
- Blast radius: LOW — Blocking synchronous subprocess call in async context causes performance degradation but not security exposure.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py
- Description: Synchronous subprocess call used inside an async function blocks the event loop.
- Remediation: Replace synchronous subprocess calls with asyncio.create_subprocess_exec or similar async methods.

## [P3] SonarQube:python:S5886
- Blast radius: LOW — Incorrect type hinting for async generator may cause runtime errors in dependency injection but limited blast radius.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py
- Description: Yield statement used without proper AsyncGenerator type annotation in async context.
- Remediation: Annotate the function return type as typing.AsyncGenerator or remove yield if not intended to be a generator.

## [P3] SonarQube:python:S8415
- Blast radius: LOW — Missing documentation for HTTP 404 responses reduces API clarity but does not introduce security risks.
- Severity: HIGH | Source: sonarqube
- File/Package: app/routers/items.py
- Description: HTTPException with status code 404 is not documented in the 'responses' parameter.
- Remediation: Add the 404 response to the FastAPI endpoint's responses parameter documentation.

## [P3] SonarQube:python:S8410
- Blast radius: LOW — Non-standard type hints for dependency injection reduce code readability but do not affect security.
- Severity: MEDIUM | Source: sonarqube
- File/Package: app/routers/health.py, app/routers/items.py
- Description: FastAPI dependency injection should use 'Annotated' type hints for better clarity and tooling support.
- Remediation: Update function signatures to use typing.Annotated for FastAPI dependencies.

