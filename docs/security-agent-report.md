# Security Agent Report

Generated: 2026-06-04T18:46:26.724806

Service: app-api
Environment: staging
Total findings: 14

## [P1] python:S8392
- Blast radius: HIGH — Binding to all interfaces (0.0.0.0) in a staging/internal environment increases exposure to lateral movement if VPN is breached.
- Severity: CRITICIAL | Source: sonarqube
- File/Package: app/main.py
- Description: Avoid binding the application to all network interfaces.
- Remediation: Restrict host binding to localhost or specific internal interface.

## [P2] python:S7487
- Blast radius: MEDIUM — Synchronous subprocess calls block the event loop, causing thread exhaustion and potential DoS for internal services.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py
- Description: Use an async subprocess call in this async function instead of a synchronous one.
- Remediation: Replace subprocess.run with asyncio.create_subprocess_exec.

## [P2] python:S3776
- Blast radius: MEDIUM — High cognitive complexity in main entry point increases risk of logic errors and unhandled edge cases in request routing.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Refactor this function to reduce its Cognitive Complexity from 19 to the 15 allowed.
- Remediation: Decompose the function into smaller, testable sub-functions.

## [P3] python:S5886
- Blast radius: LOW — Type annotation mismatch in DB session generator is a local typing issue.
- Severity: HIGH | Source: sonarqube
- File/Package: app/database.py
- Description: Remove this yield statement or annotate function 'get_db' with 'typing.AsyncGenerator'.
- Remediation: Add AsyncGenerator type hint to the generator function.

