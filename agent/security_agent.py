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

SECURITY_AGENT_SYSTEM = """Voce e um engenheiro de seguranca sênior revisando findings para um pipeline de CI/CD.

Contexto do app:
- Servico: {service}
- Ambiente: {environment}
- Zona de rede: {network_zone}
- Runtime: {runtime}

Priorize por blast radius:
- P1: Servico publico ou exposto via VPN com RCE, bypass de autenticacao, ou vazamento de segredos.
- P2: Servico interno com escalada de privilegio, SSRF, ou cadeia de dependencias unhealthy.
- P3: Vazamento de informacoes de baixo impacto, problemas de estilo, ou misconfiguracoes nao exploritaveis.

Para cada finding, informe:
1. Severidade (P1/P2/P3)
2. Componente afetado
3. Recomendacao (fix especifico no codigo ou bump de dependencia)
4. Justificativa do blast radius

Responda SOMENTE em portugues brasileiro.

Output SOMENTE JSON valido com a estrutura:
{{
  "summary": "resumo em portugues",
  "findings": [
    {{
      "id": "...",
      "severity": "P1|P2|P3",
      "component": "...",
      "title": "titulo em portugues",
      "remediation": "recomendacao em portugues",
      "blast_radius": "justificativa em portugues"
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
        lines.append("(nenhum)")

    lines.append("")
    lines.append("=== Trivy Vulnerabilities ===")
    if trivy_findings:
        for f in trivy_findings:
            fix = f" (fix: {f['fixed']})" if f["fixed"] else " (sem fix disponível)"
            lines.append(
                f"- [{f['severity']}] {f['vulnerability_id']} em {f['pkg']} "
                f"{f['installed']}{fix} — {f['title']}"
            )
    else:
        lines.append("(nenhuma)")

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

    summary = analysis.get("summary", "Veja os findings abaixo.")
    findings = analysis.get("findings", [])

    p1 = [f for f in findings if f.get("severity") == "P1"]
    p2 = [f for f in findings if f.get("severity") == "P2"]
    p3 = [f for f in findings if f.get("severity") == "P3"]

    comment = f"## Relatorio do Agente de Seguranca\n\n{summary}\n\n"
    comment += f"| Prioridade | Quantidade |\n|------------|------------|\n| P1 | {len(p1)} |\n| P2 | {len(p2)} |\n| P3 | {len(p3)} |\n\n"

    if p1:
        comment += "### 🔴 P1 — Critico\n"
        for f in p1:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    if p2:
        comment += "### 🟡 P2 — Alto\n"
        for f in p2:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    if p3:
        comment += "### 🟢 P3 — Baixo\n"
        for f in p3:
            comment += f"- **{f.get('id', '?')}**: {f.get('title', '')} — _{f.get('remediation', '')}_\n"
            comment += f"  Blast radius: {f.get('blast_radius', 'N/A')}\n"
        comment += "\n"

    pr.create_issue_comment(comment)
    print(f"  Comentario postado no PR #{pr_number}")


def main():
    print("[1/4] Buscando issues do SonarQube...")
    sonar_issues = fetch_sonarqube_issues()
    print(f"  Encontradas {len(sonar_issues)} issue(s)")

    print("[2/4] Buscando findings do Trivy...")
    trivy_findings = fetch_trivy_findings()
    print(f"  Encontradas {len(trivy_findings)} vulnerabilidade(s)")

    print("[3/4] Enviando findings para analise do LLM...")
    user_prompt = format_findings_for_prompt(sonar_issues, trivy_findings)
    analysis = call_llm(SECURITY_AGENT_SYSTEM, user_prompt)
    print(f"  Analise concluida — {len(analysis.get('findings', []))} finding(s) priorizado(s)")

    print("[4/4] Postando analise como comentario no PR...")
    try:
        comment_on_pr(analysis)
    except Exception as exc:
        print(f"  [ERROR] Falha ao comentar no PR: {exc}")
        raise SystemExit(1)

    print("Concluido.")


if __name__ == "__main__":
    main()