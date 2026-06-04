# Security Agent Report

Generated: 2026-06-04T18:43:47.146754

Service: app-api
Environment: staging
Total findings: 14

## [P1] python:S8392
- Blast radius: HIGH — Binding to all interfaces (0.0.0.0) in a staging/internal environment increases exposure to lateral movement if VPN is breached.
- Severity: CRITICIAL | Source: sonarqube
- File/Package: app/main.py
- Description: Avoid binding the application to all network interfaces.
- Remediation: Change host from '0.0.0.0' to '127.0.0.1' or specific internal interface IP in uvicorn/gunicorn config.

## [P2] python:S7487
- Blast radius: MEDIUM — Synchronous subprocess calls block the event loop, causing DoS (Denial of Service) for all concurrent requests in FastAPI.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py
- Description: Use an async subprocess call in this async function instead of a synchronous one.
- Remediation: Replace `subprocess.run` with `asyncio.create_subprocess_exec`.

## [P2] python:S3776
- Blast radius: MEDIUM — High cognitive complexity in main entry point increases risk of logic errors and unhandled edge cases during maintenance.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Refactor this function to reduce its Cognitive Complexity from 19 to the 15 allowed.
- Remediation: Extract nested conditional logic into smaller, private helper functions.

## [P3] python:S5886
- Blast radius: LOW — Type annotation mismatch is a local developer experience/static analysis issue.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py
- Description: Remove this yield statement or annotate function 'get_db' with 'typing.AsyncGenerator'.
- Remediation: Add AsyncGenerator type hint to the function signature.

