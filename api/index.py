"""Vercel entry point. Vercel serves frontend/dist itself; this function only answers /api/*."""
from server.app import app  # noqa: F401
