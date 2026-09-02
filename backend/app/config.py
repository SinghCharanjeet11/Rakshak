"""Settings, env loading.

Deliberately importable from anywhere *except* `core/` — see invariant I2 in CLAUDE.md.
`core/` takes its rule-pack as an argument; it never reaches out to read configuration.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_DIR = Path(__file__).resolve().parent
RULES_DIR = APP_DIR / "rules"
SEED_DIR = APP_DIR / "seed"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- LLM (only llm/* reads these) ---
    OPENAI_API_KEY: str = ""
    LLM_MODEL: str = "gpt-4o-mini"

    # --- storage ---
    # Postgres only. Neon: use the -pooler host and ?sslmode=require.
    DATABASE_URL: str = "postgresql://localhost/rakshak"
    # Tests point this at a throwaway schema so a test run can never touch real rows.
    DB_SCHEMA: str = "public"
    DB_POOL_MAX: int = 10

    # --- rules ---
    ACTIVE_RULEPACK: str = "2026.04.21-1"

    # --- http ---
    FRONTEND_ORIGIN: str = "http://localhost:3000"
    API_PREFIX: str = "/api/v1"

    # Comma-separated `key:tenant` pairs, e.g. "sk_acme:acme,sk_globex:globex".
    # Left blank the API runs open and every caller resolves to the `X-Tenant-Id` header
    # (default "default"), which keeps the demo and the test suite frictionless. Set it
    # and the key becomes the only way to name a tenant — headers stop being trusted.
    API_KEYS: str = ""

    @property
    def api_key_map(self) -> dict[str, str]:
        pairs = (p.strip() for p in self.API_KEYS.split(",") if p.strip())
        return dict(p.split(":", 1) for p in pairs if ":" in p)

    # --- scoring: "base" (MVP) | "weighted" (SHOULD, severity-weighted) ---
    SCORING_MODE: str = "base"

    # --- default per-run budget (02-system-design.md B.1) ---
    BUDGET_MAX_TURNS: int = 25
    BUDGET_MAX_TOTAL_TURNS: int = 60
    BUDGET_MAX_TOKENS: int = 40_000
    BUDGET_MAX_COST_INR: float = 5.0
    BUDGET_MAX_ACTIONS: int = 500

    @property
    def llm_enabled(self) -> bool:
        return bool(self.OPENAI_API_KEY)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
