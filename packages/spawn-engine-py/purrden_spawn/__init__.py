"""Purrden spawn engine (Python authoritative implementation)."""
import json
import os

from .engine import resolve_spawn

__all__ = ["resolve_spawn", "load_content"]


def load_content(base_dir: str) -> dict:
    """Load the shared content/ data files (cats, ruleset, exp LUT)."""
    def read(name: str) -> dict:
        with open(os.path.join(base_dir, "content", name), encoding="utf-8") as f:
            return json.load(f)

    return {
        "cats": read("cats.json")["cats"],
        "ruleset": read("ruleset.json"),
        "lut": read("exp_lut.json"),
    }
