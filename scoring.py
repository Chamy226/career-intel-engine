"""Career-ops job scoring (bands A-H).

A = exceptional, apply immediately
B = strong match, apply this cycle
C = good match, tailor then apply
D = stretch / adjacent, optional
E = weak match, park
F = low priority
G = poor fit
H = do not apply (red flags)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

BANDS: tuple[tuple[int, str, str], ...] = (
    (90, "A", "Immediate apply — exceptional match"),
    (80, "B", "Apply this cycle — strong match"),
    (70, "C", "Tailor and apply — good match"),
    (60, "D", "Stretch / adjacent — optional"),
    (50, "E", "Weak match — park and watch"),
    (40, "F", "Low priority"),
    (25, "G", "Poor fit"),
    (0, "H", "Do not apply — red flags"),
)

ARCHETYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sre": (
        "sre",
        "site reliability",
        "reliability",
        "observability",
        "kubernetes",
        "prometheus",
        "on-call",
        "incident",
        "terraform",
        "slo",
        "sla",
    ),
    "backend": (
        "backend",
        "python",
        "fastapi",
        "django",
        "postgres",
        "api",
        "microservices",
        "redis",
        "sql",
    ),
    "fullstack": ("fullstack", "full-stack", "react", "next.js", "typescript", "node"),
    "data": ("data engineer", "etl", "warehouse", "dbt", "spark", "airflow"),
    "ml": ("machine learning", "ml engineer", "llm", "pytorch", "nlp"),
    "security": ("security", "appsec", "soc", "iam", "threat"),
    "devops": ("devops", "ci/cd", "github actions", "docker", "kubernetes", "terraform"),
}

RED_FLAGS = (
    "unpaid",
    "equity only",
    "crypto bro",
    "get rich",
    "no experience required but senior",
    "send crypto",
    "whatsapp interview only",
)

POSITIVE_SIGNALS = (
    "python",
    "fastapi",
    "postgres",
    "supabase",
    "docker",
    "kubernetes",
    "terraform",
    "observability",
    "distributed systems",
    "aws",
    "gcp",
)


@dataclass
class JobScore:
    score: int
    band: str
    rationale: str
    reasons: list[str] = field(default_factory=list)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").lower()).strip()


def band_for_score(score: int) -> tuple[str, str]:
    clamped = max(0, min(100, int(score)))
    for threshold, band, label in BANDS:
        if clamped >= threshold:
            return band, label
    return "H", BANDS[-1][2]


def score_job(title: str, description: str, archetype: str) -> JobScore:
    """Deterministic A-H scorer used before Groq pitch / CV generation."""
    blob = _normalize(f"{title} {description}")
    archetype_key = _normalize(archetype).replace(" ", "")
    reasons: list[str] = []
    score = 55

    if any(flag in blob for flag in RED_FLAGS):
        reasons.append("Red-flag language in the posting")
        return JobScore(score=10, band="H", rationale=BANDS[-1][2], reasons=reasons)

    keywords = ARCHETYPE_KEYWORDS.get(archetype_key, ())
    if not keywords:
        for key, values in ARCHETYPE_KEYWORDS.items():
            if key in archetype_key or archetype_key in key:
                keywords = values
                break

    title_l = _normalize(title)
    if archetype_key and archetype_key in title_l.replace(" ", ""):
        score += 18
        reasons.append("Archetype appears in the job title")
    elif any(k in title_l for k in keywords[:4]):
        score += 12
        reasons.append("Title overlaps the target archetype")

    hits = [kw for kw in keywords if kw in blob]
    score += min(20, len(hits) * 3)
    if hits:
        reasons.append(f"Archetype keyword hits: {', '.join(hits[:6])}")

    stack_hits = [kw for kw in POSITIVE_SIGNALS if kw in blob]
    score += min(15, len(stack_hits) * 2)
    if stack_hits:
        reasons.append(f"Stack overlap: {', '.join(stack_hits[:6])}")

    if "remote" in blob or "hybrid" in blob:
        score += 3
        reasons.append("Remote/hybrid mentioned")

    if re.search(r"\b(staff|principal|director|vp)\b", title_l) and archetype_key in {
        "backend",
        "sre",
        "devops",
    }:
        score -= 8
        reasons.append("Seniority may be above current target band")

    score = max(0, min(100, score))
    band, rationale = band_for_score(score)
    if not reasons:
        reasons.append("Neutral posting — insufficient keyword overlap")
    return JobScore(score=score, band=band, rationale=rationale, reasons=reasons)
