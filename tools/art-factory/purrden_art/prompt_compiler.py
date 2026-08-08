"""Compile asset-spec YAML + recipe into a GenerationRequest (and dry plan JSON).

Prompts are derived; the asset spec is the source of truth.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .comfy_client import GenerationRequest, LoraRef

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


def _load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise ValueError(f"YAML root must be a mapping: {path}")
        return data
    # Minimal fallback: only support flat-ish fixtures we author (not full YAML)
    raise RuntimeError(
        "PyYAML is required to load asset specs. Install with: pip install pyyaml"
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class PromptPlan:
    asset_id: str
    recipe_id: str
    positive: str
    negative: str
    checkpoint: str
    loras: list[dict[str, Any]] = field(default_factory=list)
    width: int = 512
    height: int = 512
    steps: int = 30
    cfg: float = 5.5
    seed: int = 0
    lora_strength: float = 0.55
    spec_sha256: str = ""
    recipe_sha256: str = ""
    plan_sha256: str = ""

    def to_generation_request(self) -> GenerationRequest:
        return GenerationRequest(
            positive=self.positive,
            negative=self.negative,
            checkpoint=self.checkpoint,
            width=self.width,
            height=self.height,
            seed=self.seed,
            steps=self.steps,
            cfg=self.cfg,
            loras=[LoraRef(name=l["name"], strength=l["strength"]) for l in self.loras],
            filename_prefix=re.sub(r"[^a-zA-Z0-9_\-]", "_", self.asset_id)[:48],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _motif_phrase(visual: dict) -> str:
    parts = []
    if visual.get("species"):
        parts.append(str(visual["species"]).replace("_", " "))
    if visual.get("coat"):
        parts.append(str(visual["coat"]).replace("_", " ") + " coat")
    if visual.get("silhouette"):
        parts.append(str(visual["silhouette"]).replace("_", " ") + " silhouette")
    if visual.get("pose"):
        parts.append(str(visual["pose"]).replace("_", " ") + " pose")
    if visual.get("personality"):
        parts.append(str(visual["personality"]).replace("_", " ") + " expression")
    for m in visual.get("motif") or []:
        parts.append(str(m).replace("_", " "))
    return ", ".join(parts)


def compile_plan(
    spec_path: Path,
    recipe_path: Path,
    *,
    seed: int = 0,
    lora_strength: float | None = None,
    checkpoint_filename: str | None = None,
    lora_filename: str | None = None,
) -> PromptPlan:
    spec_text = spec_path.read_text(encoding="utf-8")
    recipe_text = recipe_path.read_text(encoding="utf-8")
    spec = _load_yaml(spec_path)
    recipe = _load_yaml(recipe_path)

    visual = spec.get("visual") or {}
    motif = _motif_phrase(visual)

    # Recipe priors
    ckpt_meta = recipe.get("checkpoint") or {}
    prefix = (ckpt_meta.get("prompt_rules") or {}).get("prefix") or ["Pixel Art"]
    bit_hint = "8 bit"
    positive_core = ", ".join(
        [
            *prefix,
            bit_hint,
            "cute cat sprite",
            motif,
            "single subject",
            "centered",
            "simple shapes",
            "clean outline",
            "game asset",
            "transparent background",
        ]
    )
    # Keep short per model notes
    if len(positive_core) > 400:
        positive_core = positive_core[:400].rsplit(",", 1)[0]

    lora_meta = recipe.get("lora") or {}
    tags = lora_meta.get("tags") or {}
    few = tags.get("low_bit_positive") or "fewP"
    many = tags.get("low_bit_negative") or "manyP"
    positive = f"{positive_core}, {few}"
    negative = (
        f"{many}, photograph, photorealistic, 3d render, blurry, antialias, "
        "gradient, text, watermark, extra limbs, cropped ears, realistic fur"
    )

    strength = lora_strength
    if strength is None:
        strength = float((lora_meta.get("preferred_strength") or {}).get("min") or 0.55)
        # prefer mid of sweep if present
        sweep = (lora_meta.get("preferred_strength") or {}).get("sweep") or []
        if sweep:
            strength = float(sweep[min(1, len(sweep) - 1)])

    gen = ckpt_meta.get("generation") or {}
    cfg = float(gen.get("cfg_default") or 5.5)
    steps = int(gen.get("steps_default") or 30)

    ckpt = checkpoint_filename or "pixelArtDiffusionXL_spriteShaper.safetensors"
    lora_name = lora_filename or "ArsMJStyleSDXL_-_Pixel_Art.safetensors"

    plan = PromptPlan(
        asset_id=str(spec.get("id") or spec_path.stem),
        recipe_id=str(recipe.get("id") or recipe_path.stem),
        positive=positive,
        negative=negative,
        checkpoint=ckpt,
        loras=[{"name": lora_name, "strength": strength}],
        width=512,
        height=512,
        steps=steps,
        cfg=cfg,
        seed=int(seed),
        lora_strength=float(strength),
        spec_sha256=_sha256_text(spec_text),
        recipe_sha256=_sha256_text(recipe_text),
    )
    plan.plan_sha256 = _sha256_text(json.dumps(plan.to_dict(), sort_keys=True))
    return plan
