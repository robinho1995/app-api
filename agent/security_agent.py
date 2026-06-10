from __future__ import annotations

import json
import os
import re
import sys
import logging
from typing import Any, Dict, List, Optional

import requests
from github import Github
from openai import OpenAI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SONAR_HOST_URL = os.getenv("SONAR_HOST_URL", "http://localhost:9000")
SONAR_TOKEN = os.getenv("SONAR_TOKEN", "")
SONAR_PROJECT = os.getenv("SONAR_PROJECT", "app-api")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.5-35b-a3b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")

AGENT_PAT = os.getenv("AGENT_PAT", os.getenv("GITHUB_TOKEN", ""))
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "")
PR_NUMBER = int(os.getenv("PR_NUMBER", "0"))

TRIVY_RESULTS_PATH = os.getenv("TRIVY_RESULTS_PATH", "trivy-results.json")

APP_CONTEXT = {
    "service": "app-api",
    "environment": "staging",
    "network_zone": "internal-vpn",
    "runtime": "Python 3.11 FastAPI",
}

SYSTEM_PROMPT = """You are a senior security engineer performing triage on vulnerability findings.
Prioritize each finding by blast radius using the following scale:

- P1 (Critical): Remote code execution, authentication bypass, data exfiltration with no prerequisites.
- P2 (High): Exploitable vulnerabilities that require some access or have limited scope.
- P3 (Medium/Low): Theoretical issues, informational findings, or low-impact vulnerabilities.

App context:
- Service: {service}
- Environment: {environment}
- Network zone: {network_zone}
- Runtime: {runtime}

Analyze the findings provided and return ONLY a JSON object (no markdown, no code fences) with this exact structure:

{{
  "summary": "Brief summary of overall security posture",
  "findings": [
    {{
      "id": "unique identifier from the source",
      "severity": "P1|P2|P3",
      "component": "affected component",
      "title": "finding title",
      "remediation": "specific remediation steps",
      "blast_radius": "explanation of why this priority was assigned"
    }}
  ]
}}""".format(**APP_CONTEXT)


def fetch_sonar_issues() -> List[Dict[str, Any]]:
    if not SONAR_TOKEN:
        logger.warning("SONAR_TOKEN not set, skipping SonarQube fetch")
        return []

    url = f"{SONAR_HOST_URL}/api/issues/search"
    params = {
        "componentKeys": SONAR_PROJECT,
        "ps": 100,
        "statuses": "OPEN,REOPENED,CONFIRMED",
    }
    headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}

    logger.info("Fetching SonarQube issues from %s", url)
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        issues = data.get("issues", [])
        logger.info("Fetched %d SonarQube issues", len(issues))
        return issues
    except Exception as exc:
        logger.error("Failed to fetch SonarQube issues: %s", exc)
        return []


def read_trivy_results() -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []

    if not os.path.isfile(TRIVY_RESULTS_PATH):
        logger.warning("Trivy results file not found at %s", TRIVY_RESULTS_PATH)
        return findings

    logger.info("Reading Trivy results from %s", TRIVY_RESULTS_PATH)
    try:
        with open(TRIVY_RESULTS_PATH) as f:
            data = json.load(f)
    except Exception as exc:
        logger.error("Failed to read Trivy results: %s", exc)
        return findings

    results = data.get("Results", []) if isinstance(data, dict) else data
    for result in results:
        target = result.get("Target", "unknown")
        vuln_type = result.get("Type", "unknown")
        for vuln in result.get("Vulnerabilities", []):
            findings.append(
                {
                    "source": "trivy",
                    "id": vuln.get("VulnerabilityID", vuln.get("PkgName", "unknown")),
                    "severity": vuln.get("Severity", "UNKNOWN"),
                    "component": f"{target} / {vuln.get('PkgName', 'unknown')}",
                    "title": vuln.get("Title", vuln.get("VulnerabilityID", "unknown")),
                    "description": vuln.get("Description", "")[:300],
                    "type": vuln_type,
                }
            )

    logger.info("Parsed %d Trivy findings", len(findings))
    return findings


def format_findings_for_llm(
    sonar_issues: List[Dict[str, Any]], trivy_findings: List[Dict[str, Any]]
) -> str:
    lines: List[str] = []

    if sonar_issues:
        lines.append("=== SonarQube Issues ===")
        for issue in sonar_issues:
            lines.append(
                f"- ID: {issue.get('key', 'N/A')}\n"
                f"  Rule: {issue.get('rule', 'N/A')}\n"
                f"  Severity: {issue.get('severity', 'N/A')}\n"
                f"  Component: {issue.get('component', 'N/A')}\n"
                f"  Message: {issue.get('message', 'N/A')}\n"
                f"  Type: {issue.get('type', 'N/A')}"
            )

    if trivy_findings:
        lines.append("\n=== Trivy Vulnerability Findings ===")
        for finding in trivy_findings:
            lines.append(
                f"- ID: {finding['id']}\n"
                f"  Severity: {finding['severity']}\n"
                f"  Component: {finding['component']}\n"
                f"  Title: {finding['title']}\n"
                f"  Type: {finding.get('type', 'N/A')}\n"
                f"  Description: {finding.get('description', '')}"
            )

    if not lines:
        lines.append("No findings to analyze.")

    return "\n".join(lines)


def analyze_with_llm(findings_text: str) -> Optional[Dict[str, Any]]:
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    logger.info("Calling LLM at %s with model %s", LLM_BASE_URL, LLM_MODEL)

    response = client.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": findings_text},
        ],
        reasoning_effort="none",
        temperature=0.2,
    )

    choice = response.choices[0]
    raw_content = choice.message.content or ""

    reasoning = getattr(choice.message, "reasoning_content", None)
    if reasoning:
        logger.debug("LLM reasoning: %s", reasoning[:500])

    cleaned = re.sub(r"^```(?:json)?\s*", "", raw_content, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()

    try:
        result = json.loads(cleaned)
        logger.info("LLM analysis complete: %d findings prioritized", len(result.get("findings", [])))
        return result
    except json.JSONDecodeError as exc:
        logger.error("Failed to parse LLM response as JSON: %s", exc)
        logger.debug("Raw LLM response: %s", raw_content[:1000])
        return None


def build_pr_comment(analysis: Dict[str, Any]) -> str:
    summary = analysis.get("summary", "No summary available.")
    findings = analysis.get("findings", [])

    p1 = [f for f in findings if f.get("severity") == "P1"]
    p2 = [f for f in findings if f.get("severity") == "P2"]
    p3 = [f for f in findings if f.get("severity") == "P3"]

    lines: List[str] = [
        "## 🔒 Security Agent Report",
        "",
        f"**Summary:** {summary}",
        "",
        "| Priority | Count |",
        "|----------|-------|",
        f"| P1 Critical | {len(p1)} |",
        f"| P2 High | {len(p2)} |",
        f"| P3 Medium/Low | {len(p3)} |",
        "",
    ]

    for label, items in [("P1 – Critical", p1), ("P2 – High", p2), ("P3 – Medium/Low", p3)]:
        lines.append(f"### {label}")
        if not items:
            lines.append("_No findings._")
            lines.append("")
            continue
        for f in items:
            lines.append(f"**{f.get('id', 'N/A')}** — {f.get('title', 'N/A')}")
            lines.append(f"- **Component:** {f.get('component', 'N/A')}")
            lines.append(f"- **Remediation:** {f.get('remediation', 'N/A')}")
            lines.append(f"- **Blast Radius:** {f.get('blast_radius', 'N/A')}")
            lines.append("")

    return "\n".join(lines)


def post_comment(comment_body: str) -> None:
    if not AGENT_PAT:
        logger.error("AGENT_PAT or GITHUB_TOKEN not set, cannot post comment")
        sys.exit(1)
    if not GITHUB_REPOSITORY:
        logger.error("GITHUB_REPOSITORY not set")
        sys.exit(1)
    if not PR_NUMBER:
        logger.error("PR_NUMBER not set or invalid")
        sys.exit(1)

    logger.info("Posting comment to %s PR #%d", GITHUB_REPOSITORY, PR_NUMBER)

    github = Github(AGENT_PAT)
    repo = github.get_repo(GITHUB_REPOSITORY)
    pr = repo.get_pull(PR_NUMBER)
    pr.create_issue_comment(comment_body)

    logger.info("Comment posted successfully")


def main() -> None:
    logger.info("Security Agent starting")

    sonar_issues = fetch_sonar_issues()
    trivy_findings = read_trivy_results()

    findings_text = format_findings_for_llm(sonar_issues, trivy_findings)
    if findings_text.strip() == "No findings to analyze.":
        logger.info("No findings found, posting minimal comment")
        comment = (
            "## 🔒 Security Agent Report\n\n"
            "**Summary:** No security findings detected. SonarQube and Trivy returned no issues.\n\n"
            "| Priority | Count |\n|----------|-------|\n"
            "| P1 Critical | 0 |\n| P2 High | 0 |\n| P3 Medium/Low | 0 |\n"
        )
        post_comment(comment)
        return

    analysis = analyze_with_llm(findings_text)
    if analysis is None:
        logger.error("LLM analysis failed, posting error comment")
        comment = (
            "## 🔒 Security Agent Report\n\n"
            "⚠️ LLM analysis failed. Check agent logs for details.\n"
        )
        post_comment(comment)
        return

    comment = build_pr_comment(analysis)
    post_comment(comment)

    logger.info("Security Agent finished")


if __name__ == "__main__":
    main()