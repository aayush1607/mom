"""Azure OpenAI factory.

Two model deployments:
  - **router**: cheap model used for parsing/routing (interpret_prompt, shortlist)
  - **picker**: stronger model used for the final dish pick (pick_dish, compose_proposal)

Both go through `langchain-openai`'s `AzureChatOpenAI`, which gives us:
  - native tool/function calling
  - `with_structured_output(BaseModel)` for typed parses
  - retry + timeout policies via standard kwargs
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from langchain_openai import AzureChatOpenAI

from meal_agent.settings import get_settings


@dataclass(frozen=True)
class LLMs:
    """Bundle of pre-configured LLM clients passed into nodes."""

    router: AzureChatOpenAI
    picker: AzureChatOpenAI


@lru_cache(maxsize=1)
def build_llms() -> LLMs:
    """Process-wide LLM client singletons."""
    s = get_settings().azure_openai

    common = dict(
        azure_endpoint=s.endpoint,
        api_key=s.api_key,
        api_version=s.api_version,
        timeout=60,
        max_retries=2,
    )

    return LLMs(
        router=AzureChatOpenAI(
            azure_deployment=s.deployment_router,
            temperature=1,
            **common,  # type: ignore[arg-type]
        ),
        picker=AzureChatOpenAI(
            azure_deployment=s.deployment_picker,
            temperature=1,
            **common,  # type: ignore[arg-type]
        ),
    )


__all__ = ["LLMs", "build_llms"]
