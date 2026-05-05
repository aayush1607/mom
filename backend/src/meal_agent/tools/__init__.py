"""External tools — LLM and MCP clients.

Kept thin and async. Singletons created at app lifespan; injected into nodes
via the `Deps` container.
"""
