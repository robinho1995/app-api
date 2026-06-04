#!/usr/bin/env python3
"""
Security Agent — Agente Orquestrador de Seguranca

Consolida findings do SonarQube e Trivy, prioriza por blast radius
usando LLM (via OpenAI SDK compativel com LM Studio/Ollama),
e abre PR automatico com plano de remediacao.

Uso:
    python security_agent.py

Variaveis de ambiente necessarias:
    SONAR_TOKEN      — token de API do SonarQube
    SONAR_HOST       — URL do SonarQube (default: http://localhost:9000)
    GITHUB_TOKEN     — token com permissoes de repo (para abrir PR)
    GITHUB_REPOSITORY— formato owner/repo (ex: user/app-api)
    LLM_BASE_URL     — URL base do LLM (default: http://localhost:1234/v1)
    LLM_MODEL        — nome do modelo (default: qwen)

Baseado no app-api (FastAPI + PostgreSQL + Redis) do Modulo 1.
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

import requests
from github import Github, GithubException
from openai import OpenAI

APP_CONTEXT = {
    "name": "app-api",
    "environment": os.getenv("APP_ENV", "staging"),
    "exposure": os.getenv("APP_EXPOSURE", "internal-vpn"),
    "description": "API REST em Python 3.11 com FastAPI, endpoints /health, /api/v1/items, /metrics",
    "stack": "Python 3.11, FastAPI, PostgreSQL 15, Redis 7",
    "slos": "disponibilidade 99.9%, p99 < 500ms",
}

SONAR_HOST = os.getenv("SONAR_HOST", "http://localhost:9000")
SONAR_TOKEN = os.getenv("SONAR_TOKEN", "")
SONAR_PROJECT = os.getenv("SONAR_PROJECT", "app-api")

LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:1234/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "qwen/qwen3.5-35b-a3b")
LLM_API_KEY = os.getenv("LLM_API_KEY", "lm-studio")

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_REPOSITORY = os.getenv("GITHUB_REPOSITORY", "user/app-api")

SECURITY_AGENT_SYSTEM = """Voce e um Security Agent. Priorize findings por BLAST RADIUS REAL.

CONTEXTO: {name} | {environment} | {exposure} | {stack} | SLOs: {slos}

PRIORIZACAO:
- P1 (HIGH): RCE/data exfil em servico publico
- P2 (MEDIUM): Vuln em dependencia de servico interno
- P3 (LOW): Code smell em funcao interna

PARA P1: acao + comando/diff + tipo (codigo ou config) + ref URL

RETORNE APENAS JSON:
{{
  "service": "{name}",
  "summary": {{"total_findings": X, "P1_count": X, "P2_count": X, "P3_count": X}},
  "prioritized_findings": [
    {{
      "id": "CVE ou SonarQube:rule",
      "priority": "P1|P2|P3",
      "blast_radius": "HIGH|MEDIUM|LOW",
      "blast_radius_justification": "texto curto",
      "type": "VULNERABILITY|CODE_SMELL|BUG",
      "source": "trivy|sonarqube",
      "severity": "CRITICAL|HIGH|MEDIUM|LOW",
      "file_or_package": "caminho",
      "description": "resumo",
      "remediation": {{"action": "texto", "is_code_fix": true, "suggested_diff": "comando", "reference_url": "url"}}
    }}
  ],
  "pr_description": "descricao para PR"
}}"""


def fetch_sonarqube_issues() -> list[dict]:
    """Busca issues abertas do SonarQube para o projeto app-api."""
    url = f"{SONAR_HOST}/api/issues/search"
    params = {
        "componentKeys": SONAR_PROJECT,
        "resolved": "false",
        "ps": 100,
    }
    headers = {"Authorization": f"Bearer {SONAR_TOKEN}"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except requests.RequestException as e:
        print(f"[WARN] Falha ao buscar SonarQube issues: {e}")
        return []

    findings = []
    for issue in data.get("issues", []):
        severity_map = {"BLOCKER": "CRITICAL", "CRITICAL": "CRITICAL", "MAJOR": "HIGH", "MINOR": "MEDIUM", "INFO": "LOW"}
        findings.append({
            "type": issue.get("type", "CODE_SMELL"),
            "severity": severity_map.get(issue.get("severity", "MAJOR"), "MEDIUM"),
            "file": issue.get("component", "").replace(f"{SONAR_PROJECT}:", ""),
            "line": issue.get("line", 0),
            "rule": issue.get("rule", ""),
            "message": issue.get("message", ""),
            "effort": issue.get("effort", "unknown"),
        })

    return findings


def fetch_trivy_findings(report_path: str = "trivy-results.json") -> list[dict]:
    """Parseia o JSON de resultados do Trivy filesystem scan."""
    path = Path(report_path)
    if not path.exists():
        print(f"[WARN] Arquivo Trivy nao encontrado: {report_path}")
        return []

    try:
        with open(path) as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"[WARN] Erro ao ler Trivy results: {e}")
        return []

    findings = []
    for result in data.get("Results", []):
        target = result.get("Target", "unknown")
        target_type = result.get("Type", "unknown")

        for vuln in result.get("Vulnerabilities", []):
            findings.append({
                "vulnerability_id": vuln.get("VulnerabilityID", ""),
                "pkg_name": vuln.get("PkgName", ""),
                "installed_version": vuln.get("InstalledVersion", ""),
                "fixed_version": vuln.get("FixedVersion", ""),
                "severity": vuln.get("Severity", "UNKNOWN"),
                "title": vuln.get("Title", ""),
                "primary_url": vuln.get("PrimaryURL", ""),
                "attack_vector": vuln.get("CVSS", {}).get("nvd", {}).get("V3Vector", "unknown"),
                "target": target,
                "target_type": target_type,
            })

    return findings


def format_findings_for_prompt(sonar_findings: list[dict], trivy_findings: list[dict]) -> str:
    """Formata os findings para o prompt estruturado do LLM."""
    sections = []

    if sonar_findings:
        lines = ["FINDINGS DO SONARQUBE:"]
        for i, f in enumerate(sonar_findings, 1):
            lines.append(
                f"{i}. Type: {f['type']} | Severity: {f['severity']} | "
                f"File: {f['file']} | Line: {f['line']} | "
                f"Rule: {f['rule']} | Message: \"{f['message']}\" | "
                f"Effort: {f['effort']}"
            )
        sections.append("\n".join(lines))

    if trivy_findings:
        lines = ["FINDINGS DO TRIVY:"]
        for i, f in enumerate(trivy_findings, 1):
            lines.append(
                f"{i}. VulnerabilityID: {f['vulnerability_id']} | "
                f"PkgName: {f['pkg_name']} | "
                f"InstalledVersion: {f['installed_version']} | "
                f"FixedVersion: {f['fixed_version']} | "
                f"Severity: {f['severity']} | "
                f"Title: {f['title']} | "
                f"PrimaryURL: {f['primary_url']} | "
                f"AttackVector: {f['attack_vector']}"
            )
        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def call_llm(system_prompt: str, user_prompt: str) -> dict:
    """Chama o LLM via OpenAI SDK (compativel com LM Studio/Ollama)."""
    client = OpenAI(base_url=LLM_BASE_URL, api_key=LLM_API_KEY)

    try:
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.1,
            max_tokens=4096,
            extra_body={"reasoning_effort": "none"},
        )
        message = response.choices[0].message
        content = message.content or ""
        if hasattr(message, "reasoning_content") and message.reasoning_content:
            if not content.strip():
                content = message.reasoning_content
        content = content.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        if content.startswith("Thinking Process:") or content.startswith("Thinking:"):
            lines = content.split("\n")
            json_start = None
            for i, line in enumerate(lines):
                if line.strip().startswith("{"):
                    json_start = i
                    break
            if json_start is not None:
                content = "\n".join(lines[json_start:])
    except Exception as e:
        print(f"[ERROR] Falha ao chamar LLM: {e}")
        sys.exit(1)

    try:
        return json.loads(content)
    except json.JSONDecodeError:
        print(f"[ERROR] Resposta do LLM nao e JSON valido. Response:\n{content[:500]}")
        sys.exit(1)


def create_pr(analysis: dict) -> str:
    """Abre um Pull Request no GitHub com o plano de remediacao."""
    if not GITHUB_TOKEN or not GITHUB_REPOSITORY:
        print("[WARN] GITHUB_TOKEN ou GITHUB_REPOSITORY nao configurados. Pulando criacao de PR.")
        print("[INFO] Analise completa. PR nao criado automaticamente.")
        return ""

    g = Github(GITHUB_TOKEN)
    try:
        repo = g.get_repo(GITHUB_REPOSITORY)
    except GithubException as e:
        print(f"[ERROR] Nao foi possivel acessar o repositorio {GITHUB_REPOSITORY}: {e}")
        return ""

    pr_title = f"[Security Agent] {analysis['summary']['P1_count']} P1, {analysis['summary']['P2_count']} P2, {analysis['summary']['P3_count']} P3 findings — {analysis['service']}"
    pr_body = analysis.get("pr_description", "Plano de remediacao gerado automaticamente.")

    branch_name = f"security-agent/fix-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    try:
        base = repo.get_branch(repo.default_branch)
        repo.create_git_ref(ref=f"refs/heads/{branch_name}", sha=base.commit.sha)

        readme_path = "docs/security-agent-report.md"
        report_content = f"# Security Agent Report\n\nGenerated: {datetime.now().isoformat()}\n\n"
        report_content += f"Service: {analysis['service']}\n"
        report_content += f"Environment: {analysis.get('environment', os.getenv('APP_ENV', 'staging'))}\n"
        report_content += f"Total findings: {analysis['summary']['total_findings']}\n\n"
        for f in analysis.get("prioritized_findings", []):
            report_content += f"## [{f['priority']}] {f['id']}\n"
            report_content += f"- Blast radius: {f['blast_radius']} — {f['blast_radius_justification']}\n"
            report_content += f"- Severity: {f['severity']} | Source: {f['source']}\n"
            report_content += f"- File/Package: {f['file_or_package']}\n"
            report_content += f"- Description: {f['description']}\n"
            if f.get("remediation"):
                report_content += f"- Remediation: {f['remediation']['action']}\n\n"

        repo.create_file(
            path=readme_path,
            message=f"security-agent: add report for {analysis['service']}",
            content=report_content,
            branch=branch_name,
        )

        pr = repo.create_pull(
            title=pr_title,
            body=pr_body,
            head=branch_name,
            base=repo.default_branch,
        )
        print(f"[OK] PR criado: {pr.html_url}")
        return pr.html_url
    except GithubException as e:
        print(f"[ERROR] Falha ao criar PR: {e}")
        return ""


def main():
    print("=" * 60)
    print("Security Agent — Agente Orquestrador de Seguranca")
    print(f"Servico: {APP_CONTEXT['name']} | Env: {APP_CONTEXT['environment']}")
    print("=" * 60)

    print("\n[1/4] Buscando findings do SonarQube...")
    sonar_findings = fetch_sonarqube_issues()
    print(f"  -> {len(sonar_findings)} findings do SonarQube")

    print("\n[2/4] Parseando findings do Trivy...")
    trivy_findings = fetch_trivy_findings()
    print(f"  -> {len(trivy_findings)} findings do Trivy")

    if not sonar_findings and not trivy_findings:
        print("\n[INFO] Nenhum finding encontrado. Encerrando.")
        sys.exit(0)

    print(f"\n[3/4] Enviando ao LLM para priorizar por blast radius...")
    system_prompt = SECURITY_AGENT_SYSTEM.format(**APP_CONTEXT)
    user_prompt = format_findings_for_prompt(sonar_findings, trivy_findings)

    analysis = call_llm(system_prompt, user_prompt)

    print(f"\n  -> Resumo:")
    print(f"     Total: {analysis['summary']['total_findings']}")
    print(f"     P1: {analysis['summary']['P1_count']}")
    print(f"     P2: {analysis['summary']['P2_count']}")
    print(f"     P3: {analysis['summary']['P3_count']}")

    print(f"\n[4/4] Abrindo PR de remediacao...")
    pr_url = create_pr(analysis)

    if pr_url:
        print(f"\n[OK] Security Agent concluido com sucesso.")
        print(f"     PR: {pr_url}")
    else:
        print(f"\n[OK] Analise concluida. PR nao criado — confira o output acima.")

    print("=" * 60)


if __name__ == "__main__":
    main()