"""Persona injection — voice packs + system prompts loaded per request.

The agent code never references brand strings. Personas are data files
keyed by `voice_pack_id` and resolved at runtime.
"""
