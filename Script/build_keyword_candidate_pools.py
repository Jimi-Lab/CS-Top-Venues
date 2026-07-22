#!/usr/bin/env python3
"""Build auditable 2026 reading candidate pools from paper titles and abstracts.

This is deliberately a *retrieval* rule set, not an automatic research-paper
classifier.  It never modifies ``Source/2026``.  Each selected paper carries
the literal matching phrases and whether they were found in the title or
abstract, so every inclusion can be reviewed.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from datetime import date
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "Source" / "2026"
OUTPUT = ROOT / "Output"


# These are intentionally phrase-oriented.  A bare ``agent``, ``memory``,
# ``model``, or ``analysis`` is never a trigger.  ``security`` / ``secure``
# are valid foundation triggers, per the reading-library policy.
AI_METHODS = [
    "artificial intelligence", "ai-assisted", "ai assisted", "generative ai",
    "large language model", "language model", "foundation model", "code model",
    "code language model", "llm", "ai agent", "llm agent", "agentic",
    "autonomous agent", "coding agent", "browser agent", "computer-using agent",
    "computer using agent", "machine learning", "deep learning", "neural network",
    "graph neural network", "representation learning", "reinforcement learning",
    "multi-agent reinforcement learning", "retrieval-augmented generation",
    "retrieval augmented generation", "rag",
]

SECURITY_CORE = [
    "security", "secure", "cybersecurity", "cyber security", "software security",
    "application security", "system security", "network security", "cloud security",
    "web security", "api security", "mobile security", "iot security",
    "vulnerability", "vulnerabilities", "cve", "cwe", "cvss", "capec",
    "exploitability", "exploitation", "exploit code", "attack surface", "attack graph",
    "attack path", "malware", "ransomware", "phishing", "intrusion",
    "privacy", "confidentiality", "data leakage", "data leak", "exfiltration",
    "backdoor", "trojan", "poisoning", "authentication", "authorization",
    "access control", "permission", "privilege escalation", "zero trust",
]

# ``attack``, ``exploit`` and ``vulnerable`` are common ordinary English verbs
# in ML/vision abstracts.  They are retained as evidence only when a stronger
# security/foundation trigger is present; they never select a paper by themselves.
AMBIGUOUS_SECURITY_TERMS = ["attack", "attacker", "adversarial", "exploit", "vulnerable", "threat", "malicious"]

FOUNDATION_SECURITY_TASKS = [
    "code audit", "vulnerability discovery", "vulnerability detection", "root cause",
    "attack path", "attack graph", "exploitability", "penetration testing", "pentesting",
    "malware analysis", "malware detection", "threat intelligence", "incident response",
    "intrusion detection", "digital forensic", "fuzzing", "fuzzer", "taint analysis",
    "information flow", "symbolic execution", "concolic", "secure compilation",
    "binary analysis", "binary lifting", "decompilation", "disassembly", "reverse engineering",
    "firmware", "software supply chain", "dependency confusion", "malicious package",
    "sbom", "code provenance", "configuration security", "misconfiguration",
]

COMPUTING_SECURITY_CARRIERS = [
    "software", "source code", "code", "program", "repository", "system", "network",
    "cloud", "web", "api", "database", "binary", "firmware", "device", "protocol",
    "application", "cyber", "computer", "data", "model", "agent", "llm", "package",
]

# These domains are not discarded wholesale: explicit cyber/security-method
# evidence still wins.  They only prevent a stray abstract word such as
# "attack" or "security" from admitting ordinary vision/medical papers.
LOW_RELEVANCE_ML_DOMAINS = [
    "point cloud", "image classification", "image recognition", "object detection",
    "remote sensing", "medical imaging", "medical image", "video recognition",
    "visual recognition", "image segmentation", "speech recognition", "protein",
]

# Explicit non-computing meanings of the word security.  They suppress the
# standalone security route only; any positive computing-security phrase wins.
NON_COMPUTING_SECURITY = [
    "food security", "social security", "economic security", "energy security",
    "water security", "physical security", "public security", "national security",
    "human security", "health security", "job security",
]

CYBER_TASKS = [
    "code audit", "vulnerability discovery", "vulnerability detection",
    "vulnerability assessment", "root cause", "root-cause", "attack path",
    "attack graph", "attack surface", "exploitability", "exploit prediction",
    "penetration testing", "pentesting", "red team", "red teaming", "reconnaissance",
    "threat intelligence", "vulnerability intelligence", "vulnerability report",
    "proof of concept", "proof-of-concept", "poc", "malware analysis",
    "malware detection", "malware classification", "malware family", "incident response",
    "intrusion detection", "anomaly detection", "forensics", "digital forensic",
    "runtime detection", "runtime monitoring", "security testing", "differential testing",
    "sanitizer", "fuzzing", "fuzzer", "fuzz", "coverage-guided",
    "taint analysis", "information flow", "data flow", "control flow",
    "static analysis", "dynamic analysis", "program analysis", "program slicing",
    "symbolic execution", "concolic", "model checking", "formal verification",
    "theorem proving", "abstract interpretation", "secure compilation",
    "binary analysis", "binary lifting", "binary function", "decompilation",
    "disassembly", "reverse engineering", "firmware", "embedded device",
    "compiler optimization", "compiler-aware", "optimization-aware", "debug information",
    "software supply chain", "supply chain attack", "dependency confusion",
    "malicious package", "package security", "sbom", "software bill of materials",
    "code provenance", "dependency provenance", "third-party library",
    "infrastructure as code", "iac", "misconfiguration", "configuration security",
]

LIFECYCLE_SE = [
    "program repair", "automated repair", "automated program repair", "security patch",
    "patch generation", "patch validation", "patch correctness", "patch propagation",
    "semantic equivalence", "vulnerability fix", "fixing commit", "introducing commit",
    "vulnerability-introducing", "vulnerability introducing", "bug-inducing",
    "affected version", "affected versions", "vulnerable version", "release tag",
    "version history", "git history", "git repository", "repository-level",
    "software repository", "codebase", "commit", "backport", "cherry-pick",
    "issue-to-code", "issue to code", "report-to-code", "report to code",
    "commit-to-cve", "commit to cve", "cve-to-code", "cve to code", "szz",
    "regression test", "security regression", "bug localization", "fault localization",
    "code review", "code migration", "api migration", "dependency upgrade",
    "ci/cd", "continuous integration", "continuous delivery", "devsecops",
    "release engineering", "software evolution", "change history", "call graph",
    "program graph", "knowledge graph", "repository reasoning", "history-aware",
]

AI_SYSTEM_ASSETS = [
    "large language model", "language model", "llm",
    "generative ai", "ai agent", "llm agent", "agentic", "autonomous agent",
    "coding agent", "browser agent", "computer-using agent", "computer using agent",
    "retrieval-augmented generation", "retrieval augmented generation", "rag",
    "model context protocol", "mcp", "tool calling", "tool use", "tool invocation",
    "function calling", "agent memory", "long-term memory", "long term memory",
    "agent-to-agent", "agent to agent", "a2a",
    "multimodal model", "vision-language model", "vision language model", "vlm",
    "model serving", "inference service", "vector database", "model weight",
    "checkpoint", "ai coding assistant", "code assistant",
]

AI_SAFETY_RISKS = [
    "prompt injection", "indirect prompt injection", "jailbreak", "prompt leaking",
    "tool hijacking", "tool calling attack", "tool use attack", "tool misuse",
    "confused deputy", "permission abuse", "privilege escalation", "unauthorized access",
    "memory poisoning", "context poisoning", "retrieval poisoning", "rag poisoning",
    "knowledge-base poisoning", "knowledge base poisoning", "data poisoning",
    "training data poisoning", "model backdoor", "backdoor attack", "malicious model",
    "model supply chain", "agent supply chain", "model stealing", "model extraction",
    "model inversion", "membership inference", "training data extraction",
    "sensitive information", "privacy leakage", "cross-tenant", "cross tenant",
    "side channel", "data exfiltration", "prompt leakage", "information leakage",
    "ai red teaming", "llm red teaming", "agent red teaming", "security testing",
    "agent identity", "agent authorization", "agent authentication", "least privilege",
    "agent audit", "policy enforcement",
    "delegation attack", "trust propagation", "environment manipulation",
    "feedback deception", "unsafe code generation", "insecure code",
]

# These phrases themselves denote attacks on AI systems and can enter the AI
# Safety pool even where a short abstract omits a separate asset phrase.  More
# generic risks such as "security testing" or "least privilege" still require
# an explicit AI-system asset, avoiding a flood of ordinary cyber papers.
AI_SAFETY_DIRECT_RISKS = [
    "model backdoor", "model supply chain", "agent supply chain",
    "model stealing", "model extraction", "membership inference",
    "training data extraction", "ai red teaming", "llm red teaming", "agent red teaming",
]

AI_SAFETY_CONTEXT = [
    "ai security", "ai safety", "llm security", "llm safety", "model security", "model safety",
    "agent security", "agent safety", "rag security", "mcp security", "secure agent",
    "secure tool use", "secure tool calling", "secure coding agent",
    "verifiable agent", "auditable agent", "agent accountability", "agent audit",
    "agent governance", "agent policy enforcement", "agent world model",
]

SE_SIGNALS = [
    "software engineering", "software repository", "repository-level", "repository level",
    "codebase", "source code", "code review", "coding agent", "code agent",
    "program repair", "patch generation", "patch validation", "bug localization",
    "fault localization", "issue-to-code", "issue to code", "report-to-code",
    "report to code", "test generation", "test case generation", "debugging",
    "code migration", "code refactoring", "software evolution", "version history",
    "git history", "git commit", "pull request", "release", "backport",
    "ci/cd", "continuous integration", "devsecops", "dependency graph", "call graph",
    "program graph", "code provenance", "compiler optimization", "debug information",
]

# Patch/test terminology alone is overloaded (e.g. image patches).  These are
# the repository/code-semantic anchors required for the AI-for-SE group.
SE_STRUCTURAL_SIGNALS = [
    "software engineering", "software repository", "repository-level", "repository level",
    "codebase", "source code", "code review", "coding agent", "code agent",
    "issue-to-code", "issue to code", "report-to-code", "report to code",
    "bug localization", "fault localization", "software evolution", "version history",
    "git history", "git commit", "pull request", "release engineering", "devsecops",
    "ci/cd", "continuous integration", "dependency graph", "call graph", "program graph",
    "binary analysis", "binary lifting", "decompilation", "compiler optimization",
    "debug information", "firmware", "embedded device",
]

SE_ABSTRACT_GATE_SIGNALS = [
    "software engineering", "software repository", "repository-level", "repository level",
    "source code", "code review", "coding agent", "code agent", "issue-to-code",
    "issue to code", "report-to-code", "report to code", "bug localization",
    "fault localization", "software evolution", "git history", "git commit", "pull request",
    "release engineering", "devsecops", "continuous integration", "binary analysis",
    "binary lifting", "decompilation", "compiler optimization", "debug information",
    "firmware", "embedded device",
]


# The user-facing taxonomy.  These terms are evidence for a provisional
# subdirection; the group gate below decides whether a record enters a pool.
DIRECTIONS = {
    "AI for Sec": {
        "LLM/Agent for Vulnerability Discovery、代码审计、根因与攻击路径": [
            "vulnerability discovery", "vulnerability detection", "code audit", "root cause", "attack path", "attack graph"],
        "AI for Vulnerability Lifecycle：提交、补丁、版本、backport": [
            "vulnerability-introducing", "fixing commit", "affected version", "release tag", "backport", "szz"],
        "AI for Automated Program Repair / Security Patch": [
            "program repair", "automated repair", "patch generation", "security patch"],
        "AI for Fuzzing / Program Analysis": [
            "fuzzing", "fuzzer", "taint analysis", "symbolic execution", "static analysis", "program analysis"],
        "Autonomous Cybersecurity Agents": [
            "autonomous agent", "agentic", "ai agent", "llm agent", "cyber range", "penetration testing"],
        "AI for Software Supply Chain Security": [
            "software supply chain", "dependency confusion", "malicious package", "sbom", "code provenance", "dependency provenance"],
        "AI for Exploitability and Attack-Path Reasoning": [
            "exploitability", "exploit prediction", "attack path", "attack graph", "attack surface"],
        "AI for Security Patch Validation": [
            "patch validation", "patch correctness", "semantic equivalence", "security regression"],
        "AI + Formal Methods for Security": [
            "formal verification", "model checking", "theorem proving", "abstract interpretation", "secure compilation"],
        "AI for Binary Lifting / Decompilation / Compiler-Aware Analysis": [
            "binary lifting", "decompilation", "disassembly", "compiler optimization", "optimization-aware"],
        "Security Agent Evaluation and Benchmarks": [
            "security benchmark", "agent benchmark", "cyber benchmark", "cyber range", "agent evaluation"],
        "AI 辅助 Web/API/Cloud/IaC 配置安全与漏洞发现": [
            "web security", "api security", "cloud security", "infrastructure as code", "iac", "misconfiguration"],
        "AI for malware analysis、恶意代码家族分析、行为检测与溯源": [
            "malware analysis", "malware detection", "malware classification", "malware family", "forensics"],
        "AI 辅助渗透测试、自动化 reconnaissance、攻击链生成与红队": [
            "penetration testing", "pentesting", "reconnaissance", "red teaming", "attack chain"],
        "Vulnerability Intelligence：CVE/CWE/CAPEC、漏洞报告、PoC、威胁情报关联": [
            "cve", "cwe", "capec", "vulnerability report", "proof of concept", "threat intelligence"],
        "AI for mobile/IoT/embedded/firmware security": [
            "mobile security", "iot security", "embedded device", "firmware"],
        "AI for vulnerability prioritization、风险评估、修复优先级与 exploit prediction": [
            "vulnerability prioritization", "risk assessment", "exploit prediction", "remediation priority"],
        "AI for security configuration、权限误配、身份与访问控制分析": [
            "configuration security", "misconfiguration", "access control", "authorization", "permission"],
        "AI for code provenance、第三方依赖识别、恶意包与软件供应链投毒": [
            "code provenance", "third-party library", "malicious package", "dependency provenance", "supply chain attack"],
        "AI for runtime detection/response：告警关联、入侵检测、取证与自动响应": [
            "intrusion detection", "incident response", "runtime detection", "forensics", "alert correlation"],
        "AI for security testing：test generation、differential testing、sanitizer-guided testing": [
            "security testing", "test generation", "differential testing", "sanitizer", "coverage-guided"],
    },
    "AI Safety": {
        "Agentic AI Security、MCP、RAG、tool/memory/multi-agent 安全": [
            "model context protocol", "mcp", "retrieval-augmented generation", "rag", "tool calling", "agent memory", "multi-agent"],
        "可验证、可审计的安全智能体": [
            "auditability", "accountability", "policy enforcement", "agent audit", "attestation"],
        "Secure Coding Agents / Coding-Agent Assurance": [
            "coding agent", "code agent", "unsafe code generation", "insecure code", "code assistant"],
        "Multimodal / CUA Security": [
            "computer-using agent", "browser agent", "multimodal model", "vision-language model", "vlm"],
        "AI Data, Privacy, and Knowledge Security": [
            "membership inference", "model inversion", "training data extraction", "privacy leakage", "vector database"],
        "AI system red teaming 与自动化安全测试": [
            "ai red teaming", "llm red teaming", "agent red teaming", "security testing"],
        "Agent 身份、认证、授权、最小权限与审计追踪": [
            "agent identity", "agent authentication", "agent authorization", "least privilege", "agent audit"],
        "Agent-to-Agent / 多 Agent 协议、委托链与信任传播安全": [
            "agent-to-agent", "a2a", "delegation attack", "trust propagation", "multi-agent"],
        "AI 模型与 Agent 供应链安全：模型权重、LoRA、插件、工具、提示词模板、MCP server": [
            "model supply chain", "agent supply chain", "model weight", "lora", "plugin", "mcp server"],
        "模型窃取、成员推断、模型反演、训练数据提取与输出泄露": [
            "model stealing", "model extraction", "membership inference", "model inversion", "training data extraction"],
        "模型后门、数据投毒、知识库投毒与检索操纵": [
            "model backdoor", "data poisoning", "knowledge-base poisoning", "retrieval poisoning", "rag poisoning"],
        "AI serving/inference security：跨租户隔离、缓存泄露、侧信道、模型 API 滥用": [
            "model serving", "inference service", "cross-tenant", "side channel", "model api"],
        "AI 安全治理：可追责性、策略执行、运行时监控、风险度量": [
            "accountability", "policy enforcement", "runtime monitoring", "risk assessment"],
        "Agent world model / environment feedback 欺骗与长期记忆投毒": [
            "world model", "environment manipulation", "feedback deception", "memory poisoning", "long-term memory"],
        "AI coding assistant 安全：不安全代码生成、依赖投毒、代码执行与工具调用越权": [
            "ai coding assistant", "unsafe code generation", "dependency confusion", "tool calling", "privilege escalation"],
    },
    "AI for SE": {
        "Binary/Firmware + AI + 编译优化语义恢复": [
            "binary analysis", "binary lifting", "firmware", "decompilation", "compiler optimization", "semantic recovery"],
        "Security-oriented AI for SE：repository reasoning、Git history、coding agent": [
            "repository reasoning", "git history", "coding agent", "software repository", "history-aware"],
        "安全需求到代码/配置的追踪与验证": [
            "security requirement", "requirements traceability", "configuration security", "formal verification"],
        "Issue/CVE/report-to-code、report-to-patch、commit-to-CVE 推理": [
            "issue-to-code", "report-to-code", "report-to-patch", "commit-to-cve", "cve-to-code"],
        "安全回归测试、补丁测试与修复传播验证": [
            "security regression", "regression test", "patch validation", "patch propagation"],
        "安全代码迁移、API/依赖升级、backport 与跨分支修复迁移": [
            "code migration", "api migration", "dependency upgrade", "backport", "cherry-pick"],
        "DevSecOps / CI-CD Agent、代码审查 Agent、release security": [
            "devsecops", "ci/cd", "continuous integration", "code review", "release security"],
        "软件仓库知识图谱、依赖图、调用图与历史感知检索": [
            "repository knowledge graph", "software dependency graph", "code dependency graph", "call graph", "program graph", "history-aware"],
        "代码 Agent 的长期记忆、规划、工具使用、失败恢复与可复现评测": [
            "coding agent", "agent memory", "tool use", "agent evaluation", "reproducibility"],
        "编译优化感知的代码语义恢复、binary/source 对齐、debug 信息缺失恢复": [
            "compiler optimization", "optimization-aware", "binary-source", "debug information", "semantic recovery"],
        "Firmware/embedded repository reasoning 与跨版本漏洞追踪": [
            "firmware", "embedded device", "repository reasoning", "affected version", "version history"],
    },
}


def normalise(value: object) -> str:
    return " " + re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", str(value or "").lower())) + " "


def phrase_hits(text: str, terms: Iterable[str]) -> set[str]:
    found = set()
    for term in terms:
        needle = normalise(term).strip()
        if needle and f" {needle} " in text:
            found.add(term)
    return found


def evidence_for(title: str, abstract: str, terms: Iterable[str], direction: str) -> list[dict]:
    title_hits = phrase_hits(title, terms)
    abstract_hits = phrase_hits(abstract, terms)
    return [
        {"phrase": phrase, "field": field, "direction": direction}
        for field, values in (("title", title_hits), ("abstract", abstract_hits))
        for phrase in sorted(values, key=str.lower)
    ]


def is_noncomputing_security_only(text: str, security_hits: set[str], cyber_hits: set[str]) -> bool:
    noncomputing = phrase_hits(text, NON_COMPUTING_SECURITY)
    computing_specific = (security_hits - {"security", "secure"}) | cyber_hits
    return bool(noncomputing) and not computing_specific


def direction_evidence(group: str, title: str, abstract: str) -> dict[str, list[dict]]:
    return {
        name: evidence
        for name, terms in DIRECTIONS[group].items()
        if (evidence := evidence_for(title, abstract, terms, name))
    }


def sort_evidence(evidence: Iterable[dict]) -> list[dict]:
    unique = {(normalise(item["phrase"]).strip(), item["field"], item["direction"]): item for item in evidence}
    return sorted(unique.values(), key=lambda item: (item["field"], item["phrase"].lower(), item["direction"]))


def classify(record: dict) -> dict | None:
    """Return transparent group-level selection metadata, or None if unmatched."""
    title = normalise(record.get("title"))
    abstract = normalise(record.get("abstract"))
    text = title + abstract

    ai_hits = phrase_hits(text, AI_METHODS)
    security_hits = phrase_hits(text, SECURITY_CORE)
    title_bare_security_hits = phrase_hits(title, ["security", "secure"])
    abstract_bare_security_hits = phrase_hits(abstract, ["security", "secure"])
    abstract_security_count = abstract.count(" security ") + abstract.count(" secure ")
    abstract_security_carriers = phrase_hits(abstract, COMPUTING_SECURITY_CARRIERS)
    foundation_hits = phrase_hits(text, FOUNDATION_SECURITY_TASKS)
    ambiguous_security_hits = phrase_hits(text, AMBIGUOUS_SECURITY_TERMS)
    cyber_hits = phrase_hits(text, CYBER_TASKS)
    lifecycle_hits = phrase_hits(text, LIFECYCLE_SE)
    ai_asset_hits = phrase_hits(text, AI_SYSTEM_ASSETS)
    ai_safety_risk_hits = phrase_hits(text, AI_SAFETY_RISKS)
    ai_safety_direct_hits = phrase_hits(text, AI_SAFETY_DIRECT_RISKS)
    ai_safety_context_hits = phrase_hits(text, AI_SAFETY_CONTEXT)
    se_hits = phrase_hits(text, SE_SIGNALS)
    se_structural_hits = phrase_hits(text, SE_STRUCTURAL_SIGNALS)
    title_se_structural_hits = phrase_hits(title, SE_STRUCTURAL_SIGNALS)
    abstract_se_gate_hits = phrase_hits(abstract, SE_ABSTRACT_GATE_SIGNALS)
    low_relevance_ml_domain = bool(phrase_hits(text, LOW_RELEVANCE_ML_DOMAINS))
    noncomputing_only = is_noncomputing_security_only(text, security_hits, cyber_hits)

    # A bare security/secure phrase remains a valid foundation entrance.  In an
    # abstract it must be repeated or tied to a computing object, so an
    # incidental one-word mention in a vision/knowledge-graph paper does not
    # dominate the screening decision.  Ambiguous verbs are never entrances.
    specific_foundation = bool(foundation_hits or lifecycle_hits)
    nonbare_security_hits = security_hits - {"security", "secure"}
    bare_security_confident = bool(title_bare_security_hits) or bool(
        abstract_bare_security_hits and (abstract_security_count >= 2 or abstract_security_carriers)
    )
    traditional_security = bool((nonbare_security_hits or specific_foundation or bare_security_confident) and not noncomputing_only)
    if low_relevance_ml_domain and not (specific_foundation or (security_hits - {"security", "secure"})):
        traditional_security = False
    # A direct AI safety attack phrase (e.g. prompt injection) is sufficient.
    # Otherwise require an AI-system asset plus an AI-specific risk or context;
    # a generic security mention near an LLM is not enough.
    ai_safety = bool(ai_safety_direct_hits) or bool(ai_asset_hits and (ai_safety_risk_hits or ai_safety_context_hits))
    cyber_operation = bool(foundation_hits or lifecycle_hits)
    ai_for_sec_direct = bool(ai_hits and traditional_security and cyber_operation)
    # Pure AI-system-security papers belong primarily to AI Safety.  They enter
    # AI for Sec too only if they also address a traditional cyber task.
    ai_for_sec_foundation = traditional_security and (not ai_safety or cyber_operation)
    se_confident = bool(title_se_structural_hits or abstract_se_gate_hits)
    ai_for_se_direct = bool(ai_hits and se_confident and traditional_security)
    ai_for_se_foundation = bool(se_confident and traditional_security)

    selections: dict[str, dict] = {}
    for group, allowed, mode in (
        ("AI for Sec", ai_for_sec_direct or ai_for_sec_foundation,
         "ai_direct" if ai_for_sec_direct else "security_foundation"),
        ("AI Safety", ai_safety,
         "ai_direct" if (ai_asset_hits or ai_hits) else "boundary"),
        ("AI for SE", ai_for_se_direct or ai_for_se_foundation,
         "ai_direct" if ai_for_se_direct else "security_foundation"),
    ):
        if not allowed:
            continue
        by_direction = direction_evidence(group, title, abstract)
        base_evidence: list[dict] = []
        if group == "AI for Sec":
            base_evidence += evidence_for(title, abstract, SECURITY_CORE + FOUNDATION_SECURITY_TASKS + LIFECYCLE_SE, "安全基础入口")
            if ai_for_sec_direct:
                base_evidence += evidence_for(title, abstract, AI_METHODS, "AI 方法入口")
        elif group == "AI Safety":
            base_evidence += evidence_for(title, abstract, AI_SYSTEM_ASSETS + AI_SAFETY_RISKS + AI_SAFETY_CONTEXT, "AI 系统安全入口")
            if not base_evidence:
                base_evidence += evidence_for(title, abstract, ["ai safety", "model safety", "agent safety"], "AI 安全边界入口")
        else:
            base_evidence += evidence_for(title, abstract, SE_STRUCTURAL_SIGNALS + SECURITY_CORE + LIFECYCLE_SE, "安全软件工程入口")
            if ai_for_se_direct:
                base_evidence += evidence_for(title, abstract, AI_METHODS, "AI 方法入口")
        evidence = sort_evidence(base_evidence + [item for values in by_direction.values() for item in values])
        selections[group] = {
            "candidate_mode": mode,
            "candidate_subdirections": sorted(by_direction),
            "match_evidence": evidence,
        }

    if not selections:
        return None
    return {
        "candidate_groups": list(selections),
        "group_selection": selections,
        "abstract_available": bool(str(record.get("abstract") or "").strip()),
    }


def live_files() -> list[Path]:
    return sorted(
        path for path in SOURCE.rglob("*-2026.json")
        if not any(part.startswith("_") for part in path.relative_to(SOURCE).parts)
    )


def make_document(name: str, papers: list[dict], total_records: int) -> dict:
    groups = Counter(group for row in papers for group in row["selection"]["candidate_groups"])
    modes = Counter(
        selection["candidate_mode"]
        for row in papers
        for selection in row["selection"]["group_selection"].values()
    )
    return {
        "name": name,
        "schema_version": "2026-keyword-candidate-pools-v1",
        "generated_on": date.today().isoformat(),
        "input": {
            "source": "Source/2026 live JSON only (underscore-prefixed backup/audit directories excluded)",
            "fields_used_for_matching": ["title", "abstract"],
            "source_papers_modified": False,
            "total_papers_scanned": total_records,
        },
        "policy": {
            "purpose": "High-recall, evidence-auditable candidate retrieval; not final classification or reading priority.",
            "multi_label": True,
            "security_is_a_standalone_foundation_trigger": True,
            "bare_terms_not_triggers": ["agent", "memory", "model", "analysis"],
            "unmatched_means": "Not matched by this v1 keyword policy; it is not permanently excluded from the library.",
            "candidate_modes": {
                "ai_direct": "Explicit AI/Agent method and relevant security or security-oriented software-engineering task.",
                "security_foundation": "Directly relevant security, program-analysis, lifecycle, binary, or formal-methods foundation without explicit AI evidence.",
                "boundary": "A direct AI-system-security risk phrase without a separately recognized AI-system asset phrase.",
            },
        },
        "summary": {
            "papers_in_this_file": len(papers),
            "union_candidate_papers": len(papers) if name == "候选池" else None,
            "group_memberships_in_this_file": dict(sorted(groups.items())),
            "candidate_modes_in_this_file": dict(sorted(modes.items())),
        },
        "papers": papers,
    }


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    total_records = 0
    for path in live_files():
        records = json.loads(path.read_text(encoding="utf-8"))
        for source_index, record in enumerate(records):
            total_records += 1
            selection = classify(record)
            if selection is None:
                continue
            rows.append({
                "source_file": str(path.relative_to(SOURCE)).replace("\\", "/"),
                "source_index": source_index,
                "selection": selection,
                "paper": record,
            })

    rows.sort(key=lambda row: (row["paper"].get("venue", ""), row["paper"].get("title", "").lower()))
    outputs = {
        "候选池": rows,
        "AI for Sec": [row for row in rows if "AI for Sec" in row["selection"]["candidate_groups"]],
        "AI Safety": [row for row in rows if "AI Safety" in row["selection"]["candidate_groups"]],
        "AI for SE": [row for row in rows if "AI for SE" in row["selection"]["candidate_groups"]],
    }
    for name, papers in outputs.items():
        destination = OUTPUT / f"{name}.json"
        destination.write_text(
            json.dumps(make_document(name, papers, total_records), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    print(json.dumps({
        "scanned": total_records,
        "候选池": len(outputs["候选池"]),
        "AI for Sec": len(outputs["AI for Sec"]),
        "AI Safety": len(outputs["AI Safety"]),
        "AI for SE": len(outputs["AI for SE"]),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
