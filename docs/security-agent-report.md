# Security Agent Report

Generated: 2026-06-04T18:50:43.654555

Service: app-api
Environment: staging
Total findings: 14

## [P1] SonarQube:python:S8392
- Blast radius: HIGH — Binding to 0.0.0.0 exposes the API to all network interfaces, including public internet if not strictly firewalled, enabling direct RCE or data exfiltration attacks.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:214
- Description: Application is bound to all network interfaces (0.0.0.0) instead of localhost.
- Remediation: Bind the FastAPI app specifically to 127.0.0.1 for internal-only access in staging, or ensure strict firewall rules if external access is required.

## [P3] SonarQube:python:S3776
- Blast radius: LOW — High cognitive complexity increases maintenance risk and potential for logic bugs, but does not directly enable exploitation.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:67
- Description: Function complexity (19) exceeds the threshold (15), making it hard to test and maintain.
- Remediation: Refactor the function by extracting sub-logic into smaller, single-responsibility helper functions.

## [P3] SonarQube:python:S8410
- Blast radius: LOW — Missing type hints reduce code clarity and IDE support but do not introduce security vulnerabilities.
- Severity: MEDIUM | Source: sonarqube
- File/Package: app/routers/items.py:13, 14, 16, 25, 33, 38
- Description: FastAPI dependency injection should use 'Annotated' type hints for better compatibility and clarity.
- Remediation: Update function signatures to use typing.Annotated for FastAPI dependencies.

## [P3] SonarQube:python:S7487
- Blast radius: LOW — Blocking I/O in an async function degrades performance (latency) but does not expose data or allow remote code execution.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py:80
- Description: Synchronous subprocess call used inside an async function, blocking the event loop.
- Remediation: Replace synchronous subprocess calls with asyncio.create_subprocess_exec or run_in_executor.

## [P3] SonarQube:python:S8415
- Blast radius: LOW — Missing documentation for error responses affects API discoverability but does not impact security or stability.
- Severity: HIGH | Source: sonarqube
- File/Package: app/routers/items.py:28, 41
- Description: HTTPException with status code 404 is not documented in the 'responses' parameter.
- Remediation: Add the 404 response to the OpenAPI documentation using the responses parameter.

## [P3] SonarQube:python:S5886
- Blast radius: LOW — Incorrect generator typing may cause runtime errors in async contexts but is a code quality issue.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py:27
- Description: Yield statement in 'get_db' needs proper AsyncGenerator typing annotation.
- Remediation: Annotate the function return type as AsyncGenerator[Session, None].

## [P3] SonarQube:python:S8396
- Blast radius: LOW — Missing default value for optional fields can lead to unexpected validation errors or None handling issues.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/schemas.py:24
- Description: Optional field in schema lacks an explicit default value.
- Remediation: Add a default value (e.g., None or empty string) to the optional field definition.

## [P3] SonarQube:python:S8410
- Blast radius: LOW — Missing type hints reduce code clarity and IDE support but do not introduce security vulnerabilities.
- Severity: MEDIUM | Source: sonarqube
- File/Package: app/routers/health.py:15
- Description: FastAPI dependency injection should use 'Annotated' type hints for better compatibility and clarity.
- Remediation: Update function signatures to use typing.Annotated for FastAPI dependencies.

