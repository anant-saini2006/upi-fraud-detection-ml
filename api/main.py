"""Convenient FastAPI entry point.

Both ``uvicorn api.main:app`` and ``uvicorn api.index:app`` serve the same
application.  Keeping this conventional module name makes the service easier
to recognise in a capstone demonstration.
"""

from api.index import app

__all__ = ["app"]
