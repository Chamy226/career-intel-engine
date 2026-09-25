"""career-intel-engine — n8n-triggered FastAPI job processor."""

from __future__ import annotations

import os
import secrets
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Annotated, Any

import httpx
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, Header, HTTPException
from groq import Groq
from pydantic import BaseModel, Field, HttpUrl
from supabase import Client, create_client

from cv_generator import generate_tailored_cv
from scoring import score_job

load_dotenv()

GROQ_MODEL = "openai/gpt-oss-20b"
ATS_STRICT_SYSTEMS = {"greenhouse", "lever"}
ALLOWED_JOB_STATUSES = frozenset(
    {
        "New",
        "Applied",
        "Phone Screen",
        "Tech Interview",
        "Final Round",
        "Offer",
        "Rejected",
    }
)

# Hardcoded ATS-optimized base content per archetype.
# Groq only rewrites/adapts this block to the target JD (faster + cheaper + grounded).
ARCHETYPE_PROMPTS: dict[str, str] = {
    "Data": """Professional Summary
MBA-qualified Senior Data Analyst with a track record of translating complex operational and user data into clear, prioritized insights for stakeholders. Combines advanced analytics with design thinking to build intuitive dashboards and visualizations that drive decision-making. Skilled in using Figma to prototype data presentation layers, align cross-functional teams, and ensure insights are both accurate and actionable.

Core Competencies
Advanced SQL · Python (pandas, scikit-learn) · A/B Testing · Statistical Analysis · Data Visualization · Tableau / Power BI · Stakeholder Management · Product Analytics · Figma UI Prototyping · Dashboard Design · Event Tracking Architecture

Experience Bullet Points
Designed and maintained an event-tracking data pipeline and standardized property dictionary that unified analytics across a customer-facing mobile application, eliminating inconsistent logging and enabling reliable product decision-making.
Conducted statistical analysis and performance evaluation of advertising and conversion data, reallocating budget toward higher-performing segments and improving overall return on investment.
Partnered with product and design teams to redesign dashboard and reporting interfaces in Figma, aligning UI/UX prototypes with business rules and stakeholder needs before engineering handoff.
Built interactive analytics dashboards tracking key metrics (conversion rates, peak usage patterns, and top-performing products), delivering actionable insights that supported prioritization of product backlog and operational improvements.""",
    "Product": """Professional Summary
MBA-qualified Product Owner / Business Analyst with insurtech experience turning ambiguous stakeholder needs into prioritized backlogs, clear acceptance criteria, and shippable increments. Bridges product analytics, UX, and engineering through Jira, Confluence, and Figma, while using lightweight prototypes to validate concepts before development. Focused on customer outcomes, sprint discipline, and cross-functional alignment in Bangkok or remote product teams.

Core Competencies
Agile / Scrum · Jira Backlog Ownership · Confluence Specs · User Story Mapping · Stakeholder Management · Acceptance Criteria · Product Analytics · Event Tracking · Figma Prototyping · Roadmapping · Discovery & Prioritization · Flutter / Mobile Collaboration

Experience Bullet Points
Owned the Jira backlog and sprint prioritization for a cross-platform Flutter product team, translating stakeholder requirements into Confluence specifications with clear acceptance criteria and measurable outcomes.
Designed and implemented the event dictionary and standardized tracking properties for a customer mobile app, enabling consistent product analytics instead of ad-hoc logging and supporting evidence-based backlog decisions.
Led the end-to-end UI/UX redesign of an internal surveyor application in Figma, facilitating structured review sessions to align prototypes with business rules before engineering handoff.
Rapidly prototyped internal product concepts with AI coding assistants to compress ideation-to-validation cycle time and de-risk features before committing sprint capacity.
Launched and operated a US-market Shopify storefront end-to-end (catalog, checkout, ads, operations), using conversion data to prioritize assortment and growth experiments.""",
    "AI": """Professional Summary
MBA-qualified AI Automation specialist who designs LLM-powered workflows, API integrations, and decision-support tools that reduce manual work without sacrificing reliability. Hands-on with Groq/OpenAI APIs, n8n orchestration, Python services, and Telegram UX patterns, including rate-limit handling, graceful degradation, and auditable run state. Combines product sense with engineering delivery to ship automation that operators actually use.

Core Competencies
LLM Prompt Engineering · Groq / OpenAI APIs · n8n Workflow Automation · Python · Streamlit · SQLite · API Integration · Telegram Bots · Circuit Breakers / Rate Limits · Multi-Tenant Architecture · Supabase / PostgreSQL · Next.js · PDPA-aware Data Design

Experience Bullet Points
Architected CashRun AI, a multi-tenant financial tracker (Python, SQLite, Streamlit) with strict user-level data isolation, WAL-mode concurrency, and AI-assisted natural-language expense parsing via Groq/OpenAI APIs.
Engineered production-minded LLM integration featuring a 429-rate-limit circuit breaker and graceful degradation so automation remains usable when upstream model APIs throttle.
Designed a premium Telegram operator UX with inline keyboards, scoped reporting commands, AI-generated financial summaries, and a safe undo path for reversible actions.
Built ScanJai, a bilingual QR ordering SaaS (Next.js 14, TypeScript, Supabase) with role-based access, tier-gated features, realtime Kanban operations, and analytics on scan conversion and peak demand.
Implemented an Interactive Brokers market-data and risk pipeline with reconnect-safe clients, position sizing, stop logic, portfolio heat caps, and n8n-driven macro/regime filters before order execution.""",
}

supabase: Client | None = None
groq_client: Groq | None = None


class ProcessJobRequest(BaseModel):
    title: str
    company_name: str
    url: HttpUrl
    description: str = ""
    archetype: str
    ats_system: str = Field(
        default="Unknown",
        description="Greenhouse, Lever, Workday, Unknown, ...",
    )


class HealthResponse(BaseModel):
    status: str
    supabase: bool
    groq: bool


class ProcessJobResponse(BaseModel):
    status: str
    job_id: str
    job_number: int | None = None
    pdf_path: str | None = None
    duplicate: bool = False
    score_band: str | None = None
    score: int | None = None
    ats_strict: bool = False


class UpdateJobStatusRequest(BaseModel):
    job_number: int
    new_status: str


class UpdateJobStatusResponse(BaseModel):
    status: str
    message: str


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _supabase_key() -> str:
    return _env("SUPABASE_KEY") or _env("SUPABASE_SECRET_KEY") or _env("SUPABASE_SERVICE_ROLE_KEY")


def get_supabase() -> Client:
    if supabase is None:
        raise HTTPException(status_code=503, detail="Supabase client is not configured")
    return supabase


def get_groq() -> Groq:
    if groq_client is None:
        raise HTTPException(status_code=503, detail="Groq client is not configured")
    return groq_client


def require_api_key(x_api_key: Annotated[str | None, Header()] = None) -> None:
    expected = _env("API_KEY")
    if not expected:
        raise HTTPException(status_code=503, detail="API_KEY is not configured")
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _archetype_key(archetype: str) -> str:
    key = (archetype or "").strip()
    aliases = {
        "data": "Data",
        "data analyst": "Data",
        "analytics": "Data",
        "product": "Product",
        "product owner": "Product",
        "po": "Product",
        "pm": "Product",
        "ai": "AI",
        "ai automation": "AI",
        "automation": "AI",
        "llm": "AI",
    }
    return aliases.get(key.lower(), key if key in ARCHETYPE_PROMPTS else "Data")


def _generate_pitch(payload: ProcessJobRequest, band: str, rationale: str) -> str:
    archetype = _archetype_key(payload.archetype)
    base_template = ARCHETYPE_PROMPTS[archetype]
    prompt = f"""You are adapting a proven CV archetype template to a specific job.

Use the ARCHETYPE TEMPLATE below as the factual source of truth for summary tone, competencies, and bullet framing.
Write a 3-4 sentence professional resume summary tailored to this role.
Reuse and lightly rewrite phrases from the template; weave in exact keywords from the job description for ATS match (Greenhouse/Lever).
Do not invent employers, degrees, metrics, or tools that are absent from the template and job description.
Do not use first-person. Plain prose only. No markdown, no bullets.

ARCHETYPE: {archetype}
ARCHETYPE TEMPLATE:
{base_template}

Job title: {payload.title}
Company: {payload.company_name}
Score band: {band} ({rationale})
ATS: {payload.ats_system}
Job description:
{payload.description[:6000]}
"""
    completion = get_groq().chat.completions.create(
        model=GROQ_MODEL,
        temperature=0.3,
        max_tokens=280,
        messages=[
            {
                "role": "system",
                "content": (
                    "You write ATS-optimized resume summaries grounded in a provided "
                    "archetype template. Plain prose only. No markdown, no bullets."
                ),
            },
            {"role": "user", "content": prompt},
        ],
    )
    text = (completion.choices[0].message.content or "").strip()
    if not text:
        raise HTTPException(status_code=502, detail="Groq returned an empty pitch")
    return text


def _find_job_by_url(url: str) -> dict[str, Any] | None:
    result = (
        get_supabase()
        .table("jobs")
        .select("id,job_number,url,status,cv_path,score_band,score")
        .eq("url", url)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    return rows[0] if rows else None


def _upsert_company(name: str) -> str | None:
    client = get_supabase()
    existing = (
        client.table("companies").select("id,name").eq("name", name).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]
    created = client.table("companies").insert({"name": name}).execute()
    if created.data:
        return created.data[0]["id"]
    return None


def _insert_job(payload: ProcessJobRequest, band: str, score: int) -> dict[str, Any]:
    row: dict[str, Any] = {
        "title": payload.title,
        "company_name": payload.company_name,
        "url": str(payload.url),
        "description": payload.description,
        "archetype": payload.archetype,
        "ats_system": payload.ats_system,
        "status": "New",
        "score_band": band,
        "score": score,
    }
    company_id = _upsert_company(payload.company_name)
    if company_id:
        row["company_id"] = company_id

    result = get_supabase().table("jobs").insert(row).execute()
    if not result.data:
        raise HTTPException(status_code=502, detail="Supabase insert returned no row")
    return result.data[0]


def _update_cv_path(job_id: str, pdf_path: str) -> None:
    get_supabase().table("jobs").update({"cv_path": pdf_path}).eq("id", job_id).execute()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global supabase, groq_client
    url = _env("SUPABASE_URL")
    key = _supabase_key()
    groq_key = _env("GROQ_API_KEY")
    if url and key:
        supabase = create_client(url, key)
    if groq_key:
        groq_client = Groq(api_key=groq_key)
    yield


app = FastAPI(
    title="career-intel-engine",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(
        status="ok",
        supabase=bool(_env("SUPABASE_URL") and _supabase_key()),
        groq=bool(_env("GROQ_API_KEY")),
    )


@app.post("/process-job", response_model=ProcessJobResponse)
async def process_job(payload: ProcessJobRequest) -> ProcessJobResponse:
    url = str(payload.url)
    existing = _find_job_by_url(url)
    if existing:
        return ProcessJobResponse(
            status="duplicate",
            job_id=str(existing["id"]),
            job_number=existing.get("job_number"),
            pdf_path=existing.get("cv_path"),
            duplicate=True,
            score_band=existing.get("score_band"),
            score=existing.get("score"),
            ats_strict=payload.ats_system.strip().lower() in ATS_STRICT_SYSTEMS,
        )

    scored = score_job(payload.title, payload.description, payload.archetype)
    job = _insert_job(payload, scored.band, scored.score)
    job_id = str(job["id"])

    pitch = _generate_pitch(payload, scored.band, scored.rationale)
    try:
        pdf_path = generate_tailored_cv(
            job_title=payload.title,
            company_name=payload.company_name,
            archetype=payload.archetype,
            ai_pitch=pitch,
            ats_system=payload.ats_system,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    _update_cv_path(job_id, pdf_path)

    try:
        bot_token = _env("TELEGRAM_BOT_TOKEN")
        chat_id = _env("TELEGRAM_CHAT_ID")
        if bot_token and chat_id:
            text = (
                "🎯 *NEW LEAD PROCESSED*\n\n"
                f"💼 *Role:* {payload.title} @ {payload.company_name}\n"
                f"🧠 *Score:* {scored.band} ({scored.score}/100)\n"
                "📄 *PDF:* Generated successfully\n\n"
                "_System is ready for n8n integration._"
            )
            async with httpx.AsyncClient(timeout=10.0) as client:
                await client.post(
                    f"https://api.telegram.org/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": chat_id,
                        "text": text,
                        "parse_mode": "Markdown",
                    },
                )
    except Exception:
        pass

    return ProcessJobResponse(
        status="created",
        job_id=job_id,
        job_number=job.get("job_number"),
        pdf_path=pdf_path,
        duplicate=False,
        score_band=scored.band,
        score=scored.score,
        ats_strict=payload.ats_system.strip().lower() in ATS_STRICT_SYSTEMS,
    )


@app.post("/update-job-status", response_model=UpdateJobStatusResponse)
def update_job_status(
    payload: UpdateJobStatusRequest,
    _: None = Depends(require_api_key),
) -> UpdateJobStatusResponse:
    new_status = payload.new_status.strip()
    if new_status not in ALLOWED_JOB_STATUSES:
        allowed = ", ".join(sorted(ALLOWED_JOB_STATUSES))
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{payload.new_status}'. Allowed: {allowed}",
        )

    client = get_supabase()
    existing = (
        client.table("jobs")
        .select("id,job_number")
        .eq("job_number", payload.job_number)
        .limit(1)
        .execute()
    )
    if not existing.data:
        raise HTTPException(
            status_code=404,
            detail=f"Job number {payload.job_number} not found",
        )

    result = (
        client.table("jobs")
        .update(
            {
                "status": new_status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        .eq("job_number", payload.job_number)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to update job number {payload.job_number}",
        )

    return UpdateJobStatusResponse(
        status="success",
        message=f"Job {payload.job_number} updated to {new_status}",
    )
