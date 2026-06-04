# Security Agent Report

Generated: 2026-06-04T18:45:26.545243

Service: app-api
Environment: staging
Total findings: 14

## [P1] python:S8392
- Blast radius: HIGH — Binding to 0.0.0.0 in a staging/internal environment can expose the API to unauthorized lateral movement within the VPN.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Avoid binding the application to all network interfaces.
- Remediation: Change host from '0.0.0.0' to '127.0.0.1' or a specific internal interface IP.

## [P2] python:S7487
- Blast radius: MEDIUM — Synchronous subprocess calls block the event loop, causing thread exhaustion and impacting p99 latency/availability.
- Severity: HIGH | Source: sonarqube
- File/Package: app/main.py
- Description: Use an async subprocess call in this async function instead of a synchronous one.
- Remediation: Replace `subprocess.run` with `asyncio.create_subprocess_exec`.

## [P2] python:S3776
- Blast radius: MEDIUM — High cognitive complexity in main entry point increases risk of logic errors and unhandled edge cases during deployment.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/main.py
- Description: Refactor this function to reduce its Cognitive Complexity from 19 to the 15 allowed.
- Remediation: Decompose the function into smaller, testable sub-functions.

## [P3] python:S8396
- Blast radius: LOW — Missing default values in schemas can lead to unexpected validation errors but does not expose data.
- Severity: CRITICAL | Source: sonarqube
- File/Package: app/schemas.py
- Description: Add an explicit default value to this optional field.
- Remediation: Assign None or a specific default value to the field.

