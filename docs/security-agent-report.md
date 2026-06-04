# Security Agent Report

Generated: 2026-06-04T18:25:00.124270

Service: app-api
Environment: staging
Total findings: 14

## [P1] SonarQube:python:S8392
- Blast radius: HIGH — Binding to 0.0.0.0 exposes the API to all network interfaces, including untrusted networks if not behind a strict WAF/Security Group, enabling direct RCE or data exfiltration attempts.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:214
- Description: Application is bound to all network interfaces (0.0.0.0) instead of localhost or specific internal IPs.
- Remediation: Change host binding from '0.0.0.0' to '127.0.0.1' or the specific internal interface IP defined in environment variables.

## [P3] SonarQube:python:S7487
- Blast radius: LOW — Blocking synchronous subprocess calls in an async function causes event loop blocking, degrading p99 latency but not causing data loss or RCE.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py:80
- Description: Synchronous subprocess call used inside an async function, blocking the event loop.
- Remediation: Replace synchronous subprocess calls with asyncio.create_subprocess_exec or asyncio.create_subprocess_shell.

## [P3] SonarQube:python:S3776
- Blast radius: LOW — High cognitive complexity increases maintenance risk and bug introduction probability but does not directly expose the system.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py:67
- Description: Function has a Cognitive Complexity of 19, exceeding the limit of 15.
- Remediation: Refactor function into smaller helper functions to reduce complexity below 15.

## [P3] SonarQube:python:S5886
- Blast radius: LOW — Incorrect type hinting for async generators may cause runtime errors or confusion but does not lead to security vulnerabilities.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py:27
- Description: Yield statement in 'get_db' function lacks proper AsyncGenerator type annotation.
- Remediation: Annotate the generator function with typing.AsyncGenerator or remove yield if not intended to be a generator.

## [P3] SonarQube:python:S8396
- Blast radius: LOW — Missing default value in schema may cause validation errors or unexpected behavior but is not a direct security exploit.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/schemas.py:24
- Description: Optional field in Pydantic schema lacks an explicit default value.
- Remediation: Add a default value (e.g., None or empty string) to the optional field.

## [P3] SonarQube:python:S8415
- Blast radius: LOW — Missing documentation for HTTP 404 responses reduces API clarity but does not impact security or availability.
- Severity: HIGH | Source: sonarqube
- File/Package: app/routers/items.py:28,41
- Description: HTTPException with status code 404 is not documented in the 'responses' parameter.
- Remediation: Add 'responses={404: {'description': 'Item not found'}}' to the endpoint definition.

## [P3] SonarQube:python:S8410
- Blast radius: LOW — Using deprecated type hints for FastAPI dependency injection reduces code modernization but has no security impact.
- Severity: MEDIUM | Source: sonarqube
- File/Package: app/routers/health.py:15, app/routers/items.py:13-16,25,33,38
- Description: FastAPI dependency injection should use 'Annotated' type hints.
- Remediation: Update imports to use typing.Annotated for FastAPI dependencies.

