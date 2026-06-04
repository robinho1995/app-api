# Security Agent Report

Generated: 2026-06-04T18:52:00.096357

Service: app-api
Environment: staging
Total findings: 14

## [P1] SonarQube:python:S8392
- Blast radius: HIGH — Binding to 0.0.0.0 exposes the API to all network interfaces, including public internet if not strictly firewalled, enabling direct RCE or data exfiltration attacks.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:214
- Description: Application bound to all network interfaces (0.0.0.0) instead of localhost.
- Remediation: Bind the FastAPI app specifically to 127.0.0.1 for internal-only access in staging, or configure UFW/firewall rules if public access is intended but restricted.

## [P3] SonarQube:python:S3776
- Blast radius: LOW — High cognitive complexity in main.py increases maintenance risk and potential for logic bugs, but does not directly expose security vulnerabilities.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:67
- Description: Function cognitive complexity (19) exceeds threshold (15).
- Remediation: Refactor the function by extracting sub-logic into smaller, single-responsibility helper functions.

## [P3] SonarQube:python:S8396
- Blast radius: LOW — Missing default value in schema may cause runtime errors or unexpected behavior during data validation, but is not a direct security exploit vector.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/schemas.py:24
- Description: Optional field lacks an explicit default value.
- Remediation: Add a default value (e.g., None or empty string) to the optional Pydantic field.

## [P3] SonarQube:python:S7487
- Blast radius: LOW — Blocking synchronous subprocess call in async function may cause latency spikes (p99 degradation), but does not inherently leak data or allow RCE.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py:80
- Description: Synchronous subprocess call used in an async function context.
- Remediation: Replace synchronous subprocess calls with asyncio.create_subprocess_exec or similar async methods.

## [P3] SonarQube:python:S5886
- Blast radius: LOW — Incorrect type hinting for async generator may lead to runtime errors or confusion, but has low security impact.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py:27
- Description: Yield statement in function 'get_db' lacks proper AsyncGenerator annotation.
- Remediation: Annotate the generator function with typing.AsyncGenerator or remove yield if not intended to be a generator.

## [P3] SonarQube:python:S8415
- Blast radius: LOW — Missing documentation for HTTP 404 responses reduces API clarity but does not expose vulnerabilities.
- Severity: HIGH | Source: sonarqube
- File/Package: app/routers/items.py:28, 41
- Description: HTTPException with status code 404 not documented in 'responses' parameter.
- Remediation: Add the 404 response to the FastAPI endpoint's responses list.

## [P3] SonarQube:python:S8410
- Blast radius: LOW — Non-standard type hints for dependency injection reduce code readability but do not impact security.
- Severity: MEDIUM | Source: sonarqube
- File/Package: app/routers/health.py:15, app/routers/items.py:13-16, 25, 33, 38
- Description: Use 'Annotated' type hints for FastAPI dependency injection.
- Remediation: Update function signatures to use typing.Annotated for dependencies.

