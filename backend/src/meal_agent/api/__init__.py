"""FastAPI app entrypoint."""

from meal_agent.api.app import app, create_app

__all__ = ["app", "create_app"]
