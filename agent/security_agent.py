import json
import os
import re

import requests
from github import Github
from openai import OpenAI

APP_CONTEXT = {
    "service": "app-api",
    "environment": "staging",
    "network_zone": "internal-vpn",
    "runtime": "Python 3.11 FastAPI",
}

SECURITY_AGENT_SYSTEM = """You are a senior security engineer reviewing findings for a CI/CD pipeline.

App context:
- Service: {service}
- Environment: {environment}
- Network zone: {network_zone}
- Runtime: {runtime}

Prioritise by blast radius:
- P1: Public-facing or VPN-exposed service with RCE, auth bypass, or secret leak.
- P2: Internal service with privilege escalation, SSRF, or unhealthy dependency chain.
- P3: Low-impact info leaks, style issues, or non-exploitable misconfigurations.

For each finding state:
1. Severity (P1/P2/P3)
2. Affected component
3. Remediation (specific code fix or dependency bump)
4. Blast-radius justification

Output valid JSON only with structure:
{{
  "summary": "...",
  "findings": [
    {{
      "id": "...",
      "severity": "P1|P2|P3",
      "component": "...",
      "title": "...",
      "remediation": "...",
      "blast_radius": "..."
    }}
  ]
}}""".format(**APP_CONTEXT)


def fetch_sonarqube_issues():
    host = os.environ.get("SONAR_HOST_URL", "http://localhost:9000")
    token = os.environ.get("SONAR_TOKEN", "")
    project = os.environ.get("SONAR_PROJECT", "app-api")

    url = f"{host}/api/issues/search"
    params = {"componentKeys": project}
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        return data.get("issues", [])
    except Exception as exc:
        print(f"  [WARN] SonarQube fetch failed: {exc}")
        return []


def fetch_trivy_findings(report_path="trivy-results.json"):
    try:
        with open(report_path, "r") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        print(f"  [WARN] Trivy report not found at {report_path}")
        return []
    except json.JSONDecodeError as exc:
        print(f"  [WARN] Trivy report invalid JSON: {exc}")
        return []

    findings = []
    for result in data.get("Results", []):
        target = result.get("Target", "unknown")
        result_type = result.get("Type", "unknown")
        for vuln in result.get("Vulnerabilities", []):
            findings.append(
                {
                    "target": target,
                    "type": result_type,
                    "vulnerability_id": vuln.get("VulnerabilityID", ""),
                    "pkg": vuln.get("PkgName", ""),
                    "installed": vuln.get("InstalledVersion", ""),
                    "fixed": vuln.get("FixedVersion", ""),
                    "severity": vuln.get("Severity", "UNKNOWN"),
                    "title": vuln.get("Title", ""),
                    "primary_url": vuln.get("PrimaryURL", ""),
                }
            )
    return findings


def format_findings_for_prompt(sonar_issues, trivy_findings):
    lines = [f"App: {APP_CONTEXT['service']} ({APP_CONTEXT['runtime']})",
             f"Env: {APP_CONTEXT['environment']} | Zone: {APP_CONTEXT['network_zone']}", ""]

    lines.append("=== SonarQube Issues ===")
    if sonar_issues:
        for issue in sonar_issues:
            lines.append(
                f"- [{issue.get('severity', '?')}] {issue.get('message', '')} "
                f"({issue.get('component', '')}:{issue.get('line', '?')}) "
                f"rule={issue.get('rule', '')}"
            )
    else:
        lines.append("(none)")

    lines.append("")
    lines.append("=== Trivy Vulnerabilities ===")
    if trivy_findings:
        for f in trivy_findings:
            fix = f" (fix: {f['fixed']})" if f["fixed"] else " (no fix available)"
            lines.append(
                f"- [{f['severity']}] {f['vulnerability_id']} in {f['pkg']} "
                f"{f['installed']}{fix} — {f['title']}"
            )
    else:
        lines.append("(none)")

    return "\n".join(lines)


def call_llm(system_prompt, user_prompt):
    base_url = os.environ.get("LLM_BASE_URL", "http://localhost:1234/v1")
    model = os.environ.get("LLM_MODEL", "qwen/qwen3.5-35b-a3b")
    api_key = os.environ.get("LLM_API_KEY", "lm-studio")

    client = OpenAI(base_url=base_url, api_key=api_key)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            reasoning_effort="none",
        )
    except Exception as exc:
        print(f"  [ERROR] LLM call failed: {exc}")
        raise

    content = response.choices[0].message.content or ""

    if hasattr(response.choices[0].message, "reasoning_content") and response.choices[0].message.reasoning_content:
        content = response.choices[0].message.content or ""

    content = re.sub(r"^```json\s*", "", content, flags=re.MULTILINE)
    content = re.sub(r"\s*```\s*$", "", content, flags=re.MULTILINE)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print("  [WARN] LLM output was not valid JSON, returning raw text")
        return {"raw": content}


def comment_on_pr(analysis):
    token = os.environ.get("AGENT_PAT") or os.environ.get("GITHUB_TOKEN")
    repo_name = os.environ.get("GITHUB_REPOSITORY")
    pr_number = os.environ.get("PR_NUMBER")

    if not token:
        raise RuntimeError("AGENT_PAT (or GITHUB_TOKEN) is not set")
    if not repo_name:
        raise RuntimeError("GITHUB_REPOSITORY is not set")
    if not pr_number:
        raise RuntimeError("PR_NUMBER is not set (must run in a pull_request event)")

    g = Github(token)
    repo = g.get_repo(repo_name)
    pr = repo.get_pull(int(pr_number))

    summary = analysis.get("summary", "See findings below.")
    findings = analysis.get("findings", [])

    p1 = [f for f in findings if f.get("severity") == "P1"]
    p2 = [f for f in findings if f.get("severity") == "P2"]
    p3 = [f for f in findings if f.get("severity") == "P3"]

    comment = f"## 🔒 Security Agent Report\n\n{summary}\n\n"
    comment += f"| Priority | Count |\n|----------|-------|\n| P1 | {len(p1)} |\n| P2 | {len(p2)} |\n| P3 | {len(p3)} |\n\n"

    if p1:
        comment += "### 🔴 P1 — Critical\n"
        for f in p1:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    if p2:
        comment += "### 🟡 P2 — High\n"
        for f in p2:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    if p3:
        comment += "### 🟢 P3 — Low\n"
        for f in p3:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    pr.create_issue_comment(comment)
    print(f"  Comment posted on PR #{pr_number}")


def main():
    print("[1/4] Fetching SonarQube issues...")
    sonar_issues = fetch_sonarqube_issues()
    print(f"  Found {len(sonar_issues)} issue(s)")

    print("[2/4] Fetching Trivy findings...")
    trivy_findings = fetch_trivy_findings()
    print(f"  Found {len(trivy_findings)} vulnerability(ies)")

    print("[3/4] Sending findings to LLM for analysis...")
    user_prompt = format_findings_for_prompt(sonar_issues, trivy_findings)
    analysis = call_llm(SECURITY_AGENT_SYSTEM, user_prompt)
    print(f"  Analysis complete — {len(analysis.get('findings', []))} prioritized finding(s)")

    print("[4/4] Posting analysis as comment on PR...")
    try:
        comment_on_pr(analysis)
    except Exception as exc:
        print(f"  [ERROR] PR comment failed: {exc}")
        raise SystemExit(1)

    print("Done.")


if __name__ == "__main__":
    main()