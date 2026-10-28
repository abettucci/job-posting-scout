import os
from dataclasses import dataclass


@dataclass
class Config:
    users_table: str
    searches_table: str
    profiles_table: str
    jobs_table: str
    telegram_codes_table: str
    interviews_table: str
    resumes_table: str
    cv_history_table: str
    company_size_cache_table: str
    scrape_runs_table: str
    ai_usage_table: str
    ai_paid_daily_budget_usd: float
    gemini_free_tier_confirmed: bool
    telegram_bot_token: str
    waweb_sidecar_url: str
    waweb_shared_secret: str
    gemini_api_key: str
    groq_api_key: str
    openrouter_api_key: str
    anthropic_api_key: str
    omniroute_base_url: str
    omniroute_api_key: str
    omniroute_model: str
    jwt_secret: str
    linkedin_email: str
    linkedin_password: str
    region: str
    environment: str
    frontend_url: str


def get_config() -> Config:
    region = os.environ.get("AWS_REGION", "us-east-2")

    return Config(
        users_table=os.environ.get("USERS_TABLE", ""),
        searches_table=os.environ.get("SEARCHES_TABLE", ""),
        profiles_table=os.environ.get("PROFILES_TABLE", ""),
        jobs_table=os.environ.get("JOBS_TABLE", ""),
        telegram_codes_table=os.environ.get("TELEGRAM_CODES_TABLE", ""),
        interviews_table=os.environ.get("INTERVIEWS_TABLE", ""),
        resumes_table=os.environ.get("RESUMES_TABLE", ""),
        cv_history_table=os.environ.get("CV_HISTORY_TABLE", ""),
        company_size_cache_table=os.environ.get("COMPANY_SIZE_CACHE_TABLE", ""),
        scrape_runs_table=os.environ.get("SCRAPE_RUNS_TABLE", ""),
        ai_usage_table=os.environ.get("AI_USAGE_TABLE", ""),
        ai_paid_daily_budget_usd=float(os.environ.get("AI_PAID_DAILY_BUDGET_USD", "1.00")),
        gemini_free_tier_confirmed=os.environ.get("GEMINI_FREE_TIER_CONFIRMED", "false").lower() == "true",
        telegram_bot_token=os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        waweb_sidecar_url=os.environ.get("WAWEB_SIDECAR_URL", ""),
        waweb_shared_secret=os.environ.get("WAWEB_SHARED_SECRET", ""),
        gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
        groq_api_key=os.environ.get("GROQ_API_KEY", ""),
        openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", ""),
        anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        # Legacy OmniRoute values remain configurable but aren't in the default AI cascade.
        omniroute_base_url=os.environ.get("OMNIROUTE_BASE_URL", ""),
        omniroute_api_key=os.environ.get("OMNIROUTE_API_KEY", ""),
        omniroute_model=os.environ.get("OMNIROUTE_MODEL", "auto"),
        jwt_secret=os.environ.get("JWT_SECRET", "change-me"),
        linkedin_email=os.environ.get("LINKEDIN_EMAIL", ""),
        linkedin_password=os.environ.get("LINKEDIN_PASSWORD", ""),
        region=region,
        environment=os.environ.get("ENVIRONMENT", "prod"),
        frontend_url=os.environ.get("FRONTEND_URL", "http://localhost:3000"),
    )