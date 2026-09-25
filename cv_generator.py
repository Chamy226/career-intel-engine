"""Render archetype-specific HTML resumes and write ATS-aware PDFs."""

from __future__ import annotations

import re
from pathlib import Path

from dotenv import load_dotenv
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent
TEMPLATES_DIR = ROOT / "templates"
OUTPUT_DIR = ROOT / "output"
load_dotenv(ROOT / ".env")

ATS_STRICT_SYSTEMS = {"greenhouse", "lever"}


def candidate_profile():
    return {
        "name": "Abdel Icham Youmandja Zoundi",
        "title": "Data Analyst | Product Owner | AI Automation",
        "contact": "Bangkok, Thailand | Valid Thai Work Permit | +66 62 429 6037 | ichamzoundi@gmail.com",
        "links": "linkedin.com/in/ichamzoundi | github.com/chamy226",
        "summary": "MBA-qualified product and data professional (GPA 3.69) with hands-on insurtech experience translating user and operational data into prioritized backlog decisions. Combines product analytics (event tracking, Jira, Confluence, Figma) with Python, SQL, n8n, and LLM APIs to deliver tracking systems, automation workflows, and decision-support tools.",
        "experience": [
            {
                "role": "Product Development Assistant (Business Analyst / Product Owner focus)",
                "company": "Roojai (Insurtech)",
                "location": "Bangkok, Thailand",
                "dates": "May 2026 – Present",
                "bullets": [
                    "Designed and implemented the event dictionary and standardized tracking properties for the customer mobile app, enabling consistent product analytics instead of ad-hoc logging.",
                    "Owned the Jira backlog and sprint prioritization; translated stakeholder requirements into clear Confluence specifications for the cross-platform Flutter development team.",
                    "Led the end-to-end UI/UX redesign of the surveyor app in Figma, running structured review sessions to align prototypes with business rules before development handoff.",
                    "Rapidly prototyped internal product concepts using AI coding assistants (Cursor, Claude), reducing ideation-to-validation cycle time.",
                ],
            },
            {
                "role": "E-commerce Project Lead",
                "company": "Independent Venture",
                "location": "Remote",
                "dates": "Jan 2022 – Jan 2026",
                "bullets": [
                    "Built and launched a complete US-market Shopify store (sourcing, catalog, PayPal checkout) from zero to live operations.",
                    "Analyzed Meta Ads performance data (spend, conversion rates, creative) and reallocated budget toward higher-converting SKUs to improve ROI.",
                    "Automated inventory and finance tracking workflows, eliminating manual reconciliation and providing real-time stock and cash visibility.",
                    "Managed cross-border chargebacks, payment-gateway compliance, and customer escalations.",
                ],
            },
        ],
        "projects": [
            {
                "name": "CashRun AI — Multi-Tenant Financial Tracker",
                "stack": "Python, SQLite, Streamlit, Groq/OpenAI APIs, Telegram",
                "bullets": [
                    "Architected a multi-tenant, AI-powered financial tracker with strict user-level data isolation and WAL-mode concurrency.",
                    "Engineered a natural-language parsing engine featuring a 429-rate-limit circuit breaker and graceful degradation.",
                    "Designed a premium Telegram UX with inline keyboards, user-scoped reporting (/report, /history), AI-generated financial insights (/ai_summary), and a safe /undo command.",
                ],
            },
            {
                "name": "ScanJai — Bilingual QR Ordering SaaS",
                "stack": "Next.js 14, TypeScript, Supabase, PostgreSQL, Realtime",
                "bullets": [
                    "Architected a bilingual (Thai/English) self-service QR ordering SaaS for Thai SMBs.",
                    "Implemented role-based access, tier-gated feature flags (Starter/Growth/Pro), and a real-time Kanban board for merchant order management.",
                    "Built an analytics dashboard tracking QR scan conversion rates, peak hours, and top-selling products, with CSV/PDF export capabilities.",
                    "Enforced strict data privacy (PDPA compliance), mobile-first 4G optimization, and fail-closed security via Supabase Row Level Security (RLS).",
                ],
            },
            {
                "name": "Algorithmic Trading Engine (Interactive Brokers)",
                "stack": "Python, ib_insync, SQLite, n8n, pandas",
                "bullets": [
                    "Built a robust market-data pipeline (historical bars, caching, IBKR API) with reconnect-safe client handling.",
                    "Implemented dollar-based position sizing, hard and trailing stops, portfolio heat caps, and macro/regime filters (via n8n) before order execution.",
                    "Persisted positions and run state in SQLite while logging fills, errors, and cycle events for full auditability.",
                ],
            },
        ],
        "education": [
            {
                "degree": "MBA, Marketing Management",
                "school": "Kasem Bundit University, Bangkok",
                "dates": "Oct 2022 – Jan 2026",
                "details": "GPA: 3.69/4.0 | Thesis: AI Chatbots in Education (SPSS analysis)",
            },
            {
                "degree": "B.Eng, Civil Engineering",
                "school": "Kasem Bundit University, Bangkok",
                "dates": "2019 – 2022",
                "details": "GPA: 3.16/4.0 | Coursework: Project Management, Structural Design",
            },
        ],
        "skills": {
            "Data & Analytics": "SQL, Python (pandas), Advanced Excel, SPSS, Product Analytics",
            "Product Management": "Jira, Confluence, Figma, Agile/Scrum, Stakeholder Management",
            "Automation & AI": "n8n, Groq/OpenAI APIs, Streamlit, SQLite, LLM Prompt Engineering",
            "Full-Stack": "Next.js 14, TypeScript, Supabase, PostgreSQL",
            "Commerce & Growth": "Shopify, Meta Business Manager, Conversion Analysis",
        },
        "certifications": [
            "Tata Group — GenAI Powered Data Analytics (The Forage)",
            "Luke Barousse — Data Analytics Crash Course",
            "Google Agile Essentials (Coursera)",
            "Anthropic — AI Fluency Framework & Foundations · Claude Code 101",
        ],
        "languages": "English (Fluent), French (Fluent), Thai (Conversational)",
    }


def is_ats_strict(ats_system: str | None) -> bool:
    return (ats_system or "").strip().lower() in ATS_STRICT_SYSTEMS


def _slug(value: str, fallback: str = "Unknown") -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", value or "").strip("_")
    return cleaned or fallback


def _template_name(archetype: str) -> str:
    slug = _slug(archetype, fallback="base").lower()
    candidate = TEMPLATES_DIR / f"{slug}.html"
    if candidate.exists():
        return candidate.name
    return "base.html"


def _jinja_env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def _render_html(
    job_title: str,
    company_name: str,
    archetype: str,
    ai_pitch: str,
    ats_system: str,
    profile: dict | None = None,
) -> str:
    data = profile or candidate_profile()
    tailored = (ai_pitch or "").strip()
    env = _jinja_env()
    template = env.get_template(_template_name(archetype))
    return template.render(
        job_title=job_title,
        company_name=company_name,
        archetype=archetype,
        ai_pitch=tailored,
        summary=tailored or data.get("summary", ""),
        ats_system=ats_system,
        ats_strict=is_ats_strict(ats_system),
        profile=data,
    )


def generate_tailored_cv(
    job_title: str,
    company_name: str,
    archetype: str,
    ai_pitch: str,
    ats_system: str,
    profile: dict | None = None,
) -> str:
    """Render HTML for the archetype and write `output/CV_{Company}_{Archetype}.pdf`.

    Greenhouse and Lever get `ats_strict=True`, which applies a CSS class that
    hides tables, columns, images, and chrome so parsers see a single column.
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html = _render_html(
        job_title=job_title,
        company_name=company_name,
        archetype=archetype,
        ai_pitch=ai_pitch,
        ats_system=ats_system,
        profile=profile,
    )

    try:
        from weasyprint import HTML
    except OSError as exc:
        raise RuntimeError(
            "WeasyPrint is missing system libraries (Pango/Cairo). "
            "On macOS: brew install pango cairo gdk-pixbuf libffi. "
            "On Debian/Ubuntu: apt install libpango-1.0-0 libpangoft2-1.0-0 "
            "libcairo2 libgdk-pixbuf-2.0-0 libffi-dev shared-mime-info."
        ) from exc

    filename = f"CV_{_slug(company_name)}_{_slug(archetype)}.pdf"
    pdf_path = OUTPUT_DIR / filename
    HTML(string=html, base_url=str(TEMPLATES_DIR)).write_pdf(str(pdf_path))
    return str(pdf_path)
