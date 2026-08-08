"""Purrden Art Factory — developer-only build-time sprite production.

Never imported by the shipped browser game or cloud API runtime.
"""

__version__ = "0.2.0"

from .pipeline import JobState, run_job

__all__ = ["JobState", "run_job", "__version__"]
