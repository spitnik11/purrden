"""Bounded ComfyUI HTTP client for the Purrden Art Factory.

Ported as *concepts* from the private z-image-studio Comfy client — not a dependency.
Only talks to a configured base URL (default loopback). Never submits arbitrary
agent-authored graphs; only validated, recipe-built prompts.

Capabilities:
  - GET /system_stats, /object_info, /queue, /history/{id}
  - POST /prompt (validated payload)
  - GET /view (download image into a contained workbench path)
  - History/queue reconciliation (poll); WebSocket is optional later

Security boundary:
  - base URL must be loopback unless PURRDEN_ART_ALLOW_REMOTE_COMFY=1
  - model/LoRA names must not contain path traversal
  - dimensions, steps, CFG, LoRA strengths clamped to recipe limits
  - outputs only written under a caller-supplied workbench directory
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._\- ]{0,250}$")
SAFE_SUBFOLDER = re.compile(r"^[A-Za-z0-9._\-/]{0,200}$")

DEFAULT_LIMITS = {
    "width_min": 256,
    "width_max": 1536,
    "height_min": 256,
    "height_max": 1536,
    "steps_min": 1,
    "steps_max": 60,
    "cfg_min": 1.0,
    "cfg_max": 15.0,
    "lora_strength_min": 0.0,
    "lora_strength_max": 1.0,
    "batch_max": 4,
    "prompt_max": 2000,
    "negative_max": 1500,
}


class ComfyError(RuntimeError):
    pass


class ComfyValidationError(ComfyError):
    pass


class ComfyUnreachable(ComfyError):
    pass


def _assert_loopback(url: str) -> None:
    if os.environ.get("PURRDEN_ART_ALLOW_REMOTE_COMFY") == "1":
        return
    host = (urlparse(url).hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ComfyValidationError(
            f"ComfyUI URL must be loopback ({url}). "
            "Set PURRDEN_ART_ALLOW_REMOTE_COMFY=1 only for trusted remote labs."
        )


def assert_safe_model_name(name: str, field: str = "model") -> str:
    name = (name or "").strip()
    if not name:
        raise ComfyValidationError(f"{field} name is empty")
    if ".." in name or "/" in name or "\\" in name or name.startswith("."):
        raise ComfyValidationError(f"{field} rejects path traversal: {name!r}")
    if not SAFE_NAME.match(name):
        raise ComfyValidationError(f"{field} has invalid characters: {name!r}")
    return name


@dataclass
class LoraRef:
    name: str
    strength: float = 0.55

    def validated(self, limits: dict = DEFAULT_LIMITS) -> "LoraRef":
        name = assert_safe_model_name(self.name, "lora")
        lo, hi = limits["lora_strength_min"], limits["lora_strength_max"]
        if not (lo <= self.strength <= hi):
            raise ComfyValidationError(
                f"lora strength {self.strength} outside [{lo}, {hi}]"
            )
        return LoraRef(name=name, strength=float(self.strength))


@dataclass
class GenerationRequest:
    """Typed input for a constrained SDXL txt2img job (semantic hi-res only)."""

    positive: str
    negative: str = "manyP, blurry, antialias, gradient, photograph, realistic fur, text"
    checkpoint: str = "pixelArtDiffusionXL_spriteShaper.safetensors"
    width: int = 512
    height: int = 512
    seed: int = 0
    steps: int = 30
    cfg: float = 5.5
    batch_size: int = 1
    loras: list[LoraRef] = field(default_factory=list)
    sampler: str = "euler"
    scheduler: str = "normal"
    filename_prefix: str = "purrden"

    def validated(self, limits: dict = DEFAULT_LIMITS) -> "GenerationRequest":
        pos = (self.positive or "").strip()
        neg = (self.negative or "").strip()
        if not pos:
            raise ComfyValidationError("positive prompt is required")
        if len(pos) > limits["prompt_max"]:
            raise ComfyValidationError("positive prompt too long")
        if len(neg) > limits["negative_max"]:
            raise ComfyValidationError("negative prompt too long")
        ckpt = assert_safe_model_name(self.checkpoint, "checkpoint")
        if not (limits["width_min"] <= self.width <= limits["width_max"]):
            raise ComfyValidationError(f"width out of range: {self.width}")
        if not (limits["height_min"] <= self.height <= limits["height_max"]):
            raise ComfyValidationError(f"height out of range: {self.height}")
        if self.width % 8 or self.height % 8:
            raise ComfyValidationError("width/height must be multiples of 8")
        if not (limits["steps_min"] <= self.steps <= limits["steps_max"]):
            raise ComfyValidationError(f"steps out of range: {self.steps}")
        if not (limits["cfg_min"] <= self.cfg <= limits["cfg_max"]):
            raise ComfyValidationError(f"cfg out of range: {self.cfg}")
        if not (1 <= self.batch_size <= limits["batch_max"]):
            raise ComfyValidationError(f"batch_size out of range: {self.batch_size}")
        if self.seed < 0:
            raise ComfyValidationError("seed must be >= 0")
        prefix = self.filename_prefix.strip() or "purrden"
        if not re.match(r"^[A-Za-z0-9_./\-]{1,64}$", prefix) or ".." in prefix:
            raise ComfyValidationError(f"invalid filename_prefix: {prefix!r}")
        loras = [LoraRef(l.name, l.strength).validated(limits) for l in self.loras]
        if len(loras) > 4:
            raise ComfyValidationError("at most 4 LoRAs")
        return GenerationRequest(
            positive=pos,
            negative=neg,
            checkpoint=ckpt,
            width=int(self.width),
            height=int(self.height),
            seed=int(self.seed),
            steps=int(self.steps),
            cfg=float(self.cfg),
            batch_size=int(self.batch_size),
            loras=loras,
            sampler=self.sampler,
            scheduler=self.scheduler,
            filename_prefix=prefix,
        )


def build_sdxl_pixel_workflow(req: GenerationRequest) -> dict[str, Any]:
    """Constrained API-format graph. No agent-authored nodes."""
    r = req.validated()
    model_ref: Any = ["4", 0]
    clip_ref: Any = ["4", 1]

    workflow: dict[str, Any] = {
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": r.checkpoint},
        },
    }

    # Chain LoRAs: 10, 11, ...
    next_model, next_clip = model_ref, clip_ref
    for i, lora in enumerate(r.loras):
        node_id = str(10 + i)
        workflow[node_id] = {
            "class_type": "LoraLoader",
            "inputs": {
                "model": next_model,
                "clip": next_clip,
                "lora_name": lora.name,
                "strength_model": lora.strength,
                "strength_clip": lora.strength,
            },
        }
        next_model = [node_id, 0]
        next_clip = [node_id, 1]

    workflow["6"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": r.positive, "clip": next_clip},
    }
    workflow["7"] = {
        "class_type": "CLIPTextEncode",
        "inputs": {"text": r.negative, "clip": next_clip},
    }
    workflow["5"] = {
        "class_type": "EmptyLatentImage",
        "inputs": {
            "width": r.width,
            "height": r.height,
            "batch_size": r.batch_size,
        },
    }
    workflow["3"] = {
        "class_type": "KSampler",
        "inputs": {
            "seed": r.seed,
            "steps": r.steps,
            "cfg": r.cfg,
            "sampler_name": r.sampler,
            "scheduler": r.scheduler,
            "denoise": 1.0,
            "model": next_model,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
        },
    }
    workflow["8"] = {
        "class_type": "VAEDecode",
        "inputs": {"samples": ["3", 0], "vae": ["4", 2]},
    }
    workflow["9"] = {
        "class_type": "SaveImage",
        "inputs": {"filename_prefix": r.filename_prefix, "images": ["8", 0]},
    }
    return workflow


@dataclass
class HistoryImage:
    filename: str
    subfolder: str
    type: str  # output | temp | input


@dataclass
class JobResult:
    prompt_id: str
    status: str  # completed | failed | timeout | missing
    images: list[HistoryImage] = field(default_factory=list)
    raw_history: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ComfyClient:
    def __init__(self, base_url: str | None = None, timeout_s: float = 30.0):
        self.base_url = (base_url or os.environ.get("COMFYUI_URL") or "http://127.0.0.1:8188").rstrip("/")
        _assert_loopback(self.base_url)
        self.timeout_s = timeout_s
        self.client_id = str(uuid.uuid4())
        self._object_info: dict[str, Any] | None = None
        self._object_info_at = 0.0

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            self._url(path), data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout_s) as resp:
                raw = resp.read()
                if not raw:
                    return None
                return json.loads(raw.decode("utf-8"))
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:500]
            raise ComfyError(f"ComfyUI HTTP {e.code} on {path}: {detail}") from e
        except urllib.error.URLError as e:
            raise ComfyUnreachable(
                f"Cannot reach ComfyUI at {self.base_url}: {e.reason}"
            ) from e
        except TimeoutError as e:
            raise ComfyUnreachable(
                f"ComfyUI timed out at {self.base_url}"
            ) from e

    def ping(self) -> dict[str, Any]:
        return self._request("GET", "/system_stats", timeout=5.0)

    def object_info(self, force: bool = False) -> dict[str, Any]:
        now = time.time()
        if (
            not force
            and self._object_info is not None
            and now - self._object_info_at < 30
        ):
            return self._object_info
        info = self._request("GET", "/object_info", timeout=60.0)
        self._object_info = info
        self._object_info_at = now
        return info

    def list_checkpoints(self) -> list[str]:
        info = self.object_info()
        node = info.get("CheckpointLoaderSimple") or {}
        inputs = (node.get("input") or {}).get("required") or {}
        names = inputs.get("ckpt_name")
        if isinstance(names, list) and names and isinstance(names[0], list):
            return list(names[0])
        return []

    def list_loras(self) -> list[str]:
        info = self.object_info()
        node = info.get("LoraLoader") or {}
        inputs = (node.get("input") or {}).get("required") or {}
        names = inputs.get("lora_name")
        if isinstance(names, list) and names and isinstance(names[0], list):
            return list(names[0])
        return []

    def validate_models_available(self, req: GenerationRequest) -> list[str]:
        """Return list of missing model names (empty = ok). Soft-check via object_info."""
        r = req.validated()
        missing: list[str] = []
        try:
            ckpts = set(self.list_checkpoints())
            loras = set(self.list_loras())
        except ComfyError:
            # Offline / unreachable — caller decides
            raise
        if r.checkpoint not in ckpts:
            # Comfy sometimes lists without extension or with subfolder
            if not any(r.checkpoint in c or c.endswith(r.checkpoint) for c in ckpts):
                missing.append(r.checkpoint)
        for lora in r.loras:
            if lora.name not in loras and not any(
                lora.name in x or x.endswith(lora.name) for x in loras
            ):
                missing.append(lora.name)
        return missing

    def submit(self, workflow: dict[str, Any]) -> str:
        if not isinstance(workflow, dict) or not workflow:
            raise ComfyValidationError("workflow must be a non-empty dict")
        # Reject unknown top-level abuse
        for node_id, node in workflow.items():
            if not str(node_id).isdigit():
                raise ComfyValidationError(f"invalid node id: {node_id!r}")
            if not isinstance(node, dict) or "class_type" not in node:
                raise ComfyValidationError(f"node {node_id} missing class_type")
            allowed = {
                "CheckpointLoaderSimple",
                "LoraLoader",
                "CLIPTextEncode",
                "EmptyLatentImage",
                "KSampler",
                "VAEDecode",
                "SaveImage",
            }
            if node["class_type"] not in allowed:
                raise ComfyValidationError(
                    f"disallowed node class_type: {node['class_type']}"
                )
        body = {"prompt": workflow, "client_id": self.client_id}
        resp = self._request("POST", "/prompt", body=body, timeout=60.0)
        prompt_id = (resp or {}).get("prompt_id")
        if not prompt_id:
            raise ComfyError(f"ComfyUI submit missing prompt_id: {resp!r}")
        return str(prompt_id)

    def history(self, prompt_id: str) -> dict[str, Any]:
        safe = urllib.parse.quote(prompt_id, safe="")
        return self._request("GET", f"/history/{safe}") or {}

    def queue(self) -> dict[str, Any]:
        return self._request("GET", "/queue") or {}

    def _images_from_history_entry(self, entry: dict[str, Any]) -> list[HistoryImage]:
        images: list[HistoryImage] = []
        outputs = entry.get("outputs") or {}
        for _nid, out in outputs.items():
            for img in out.get("images") or []:
                fn = img.get("filename") or ""
                if not fn or ".." in fn:
                    continue
                sub = img.get("subfolder") or ""
                if ".." in sub:
                    continue
                images.append(
                    HistoryImage(
                        filename=fn,
                        subfolder=sub,
                        type=img.get("type") or "output",
                    )
                )
        return images

    def wait_for_job(
        self,
        prompt_id: str,
        *,
        timeout_s: float = 600.0,
        poll_s: float = 1.0,
    ) -> JobResult:
        """Reconcile via history + queue. Missing progress ≠ success."""
        deadline = time.time() + timeout_s
        while time.time() < deadline:
            hist = self.history(prompt_id)
            entry = hist.get(prompt_id)
            if entry:
                status_obj = entry.get("status") or {}
                # Comfy history status: completed / error keys vary by version
                if status_obj.get("status_str") == "error" or status_obj.get("completed") is False:
                    msgs = status_obj.get("messages") or []
                    return JobResult(
                        prompt_id=prompt_id,
                        status="failed",
                        raw_history=entry,
                        error=str(msgs)[:800] if msgs else "comfy reported error",
                    )
                images = self._images_from_history_entry(entry)
                # Treat presence of outputs as completed (history only appears when done)
                if images or status_obj.get("completed") is True:
                    return JobResult(
                        prompt_id=prompt_id,
                        status="completed" if images else "failed",
                        images=images,
                        raw_history=entry,
                        error=None if images else "completed without images",
                    )
            time.sleep(poll_s)
        return JobResult(prompt_id=prompt_id, status="timeout", error="wait_for_job timed out")

    def download_image(
        self,
        image: HistoryImage,
        dest_dir: Path,
        *,
        filename: str | None = None,
    ) -> Path:
        """Download into dest_dir only. dest_dir must already exist and be the workbench."""
        dest_dir = dest_dir.resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)
        out_name = filename or Path(image.filename).name
        if ".." in out_name or "/" in out_name or "\\" in out_name:
            raise ComfyValidationError(f"refusing unsafe dest name: {out_name!r}")
        dest = (dest_dir / out_name).resolve()
        if dest_dir not in dest.parents and dest != dest_dir:
            raise ComfyValidationError("download path escaped workbench")
        if not dest.is_relative_to(dest_dir):
            raise ComfyValidationError("download path escaped workbench")

        q = urllib.parse.urlencode(
            {
                "filename": image.filename,
                "subfolder": image.subfolder,
                "type": image.type,
            }
        )
        url = self._url(f"/view?{q}")
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
                data = resp.read()
        except urllib.error.URLError as e:
            raise ComfyError(f"failed to download image: {e}") from e
        if len(data) < 32:
            raise ComfyError("downloaded image too small")
        # PNG or WEBP magic
        if not (data[:8] == b"\x89PNG\r\n\x1a\n" or data[:4] == b"RIFF"):
            raise ComfyError("downloaded file is not PNG/WEBP")
        dest.write_bytes(data)
        return dest

    def generate(
        self,
        req: GenerationRequest,
        workbench: Path,
        *,
        timeout_s: float = 600.0,
        check_models: bool = True,
    ) -> tuple[JobResult, list[Path]]:
        """Validate → build workflow → submit → wait → download into workbench/raw."""
        r = req.validated()
        if check_models:
            missing = self.validate_models_available(r)
            if missing:
                raise ComfyValidationError(f"models not visible to ComfyUI: {missing}")
        workflow = build_sdxl_pixel_workflow(r)
        prompt_id = self.submit(workflow)
        result = self.wait_for_job(prompt_id, timeout_s=timeout_s)
        paths: list[Path] = []
        if result.status == "completed":
            raw_dir = Path(workbench) / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            for i, img in enumerate(result.images):
                paths.append(
                    self.download_image(img, raw_dir, filename=f"candidate_{i:02d}.png")
                )
        return result, paths
