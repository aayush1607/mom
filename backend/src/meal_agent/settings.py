"""Runtime settings loaded from environment variables.

All configuration enters the process here. Nothing else reads `os.environ`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AzureOpenAISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AZURE_OPENAI_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    endpoint: str = Field(..., description="Azure OpenAI endpoint URL")
    api_key: str = Field(..., description="Azure OpenAI API key")
    api_version: str = Field("2024-08-01-preview", description="Azure OpenAI API version")
    deployment_router: str = Field("gpt-4o-mini", description="Cheap model for routing/parsing")
    deployment_picker: str = Field("gpt-4o", description="Stronger model for the dish pick")


class SwiggyMCPSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SWIGGY_MCP_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    food_url: str = Field("https://mcp.swiggy.com/food", description="Swiggy Food MCP endpoint")
    dineout_url: str = Field(
        "https://mcp.swiggy.com/dineout", description="Swiggy Dineout MCP endpoint"
    )
    transport: str = Field(
        "streamable_http", description="MCP transport: 'streamable_http' or 'sse'"
    )
    dineout_enabled: bool = Field(False, description="Skip dineout server (v1 uses food only)")
    auth_token_env: str = Field(
        "SWIGGY_OAUTH_TOKEN",
        description="Env var holding the per-user OAuth token at request time",
    )


class StorageSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="POSTGRES_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    dsn: str = Field(..., description="postgresql://user:pass@host:5432/db")
    pool_min: int = Field(1)
    pool_max: int = Field(10)


class AgentSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AGENT_", env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    max_swap_count: int = Field(1, description="Hard cap on 'Something else' taps per run")
    discover_top_n: int = Field(15, description="Restaurants pulled in discover step")
    shortlist_top_n: int = Field(3, description="Restaurants whose menus we fetch")
    interrupt_timeout_min: int = Field(
        60,
        description="Run is auto-cancelled if user doesn't respond within this window",
    )
    live_orders_enabled: bool = Field(
        False,
        description=(
            "MUST be True for `place_order` to actually call Swiggy's "
            "place_food_order. Default False — node returns a synthetic "
            "DRYRUN order id and never spends money. Set "
            "AGENT_LIVE_ORDERS_ENABLED=true in env to flip."
        ),
    )
    block_cod: bool = Field(
        True,
        description=(
            "If True, strip Cash / COD from cart payment_methods and refuse "
            "to confirm if no non-cash method remains. mom UX requires "
            "the user to pre-pay in-app."
        ),
    )


class Settings(BaseSettings):
    """Top-level settings container."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    log_level: str = Field("INFO")
    persona_packs_dir: Path = Field(
        default_factory=lambda: Path(__file__).parent / "persona" / "packs",
        description="Directory containing voice-pack YAML files",
    )

    azure_openai: AzureOpenAISettings = Field(default_factory=AzureOpenAISettings)  # type: ignore[arg-type]
    swiggy: SwiggyMCPSettings = Field(default_factory=SwiggyMCPSettings)  # type: ignore[arg-type]
    storage: StorageSettings = Field(default_factory=StorageSettings)  # type: ignore[arg-type]
    agent: AgentSettings = Field(default_factory=AgentSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton."""
    return Settings()  # type: ignore[call-arg]
