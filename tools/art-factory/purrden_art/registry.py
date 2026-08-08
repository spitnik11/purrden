"""Local model registry: scan a read-only model root, hash files, classify roles.

Does not download models. Does not write outside .art-factory/.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

ROLE_HINTS = {
    "checkpoint": (".safetensors", ".ckpt"),
    "lora": (".safetensors",),
    "vae": (".safetensors", ".pt"),
}


@dataclass
class ModelRecord:
    path: str
    rel_path: str
    name: str
    sha256: str
    size_bytes: int
    role: str
    format: str
    license_status: str = "UNKNOWN"
    shipping_status: str = "UNKNOWN"


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def _guess_role(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    name = path.name.lower()
    joined = "/".join(parts)
    if "lora" in joined or "loras" in joined:
        return "lora"
    if "vae" in joined:
        return "vae"
    if "upscale" in joined or "esrgan" in name:
        return "upscaler"
    if "controlnet" in joined:
        return "controlnet"
    if path.suffix.lower() in {".safetensors", ".ckpt", ".pt", ".pth"}:
        return "checkpoint"
    return "unknown"


def _guess_format(path: Path) -> str:
    return path.suffix.lower().lstrip(".") or "unknown"


def iter_model_files(root: Path) -> Iterable[Path]:
    if not root.is_dir():
        raise FileNotFoundError(f"Model root not found or not a directory: {root}")
    exts = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
    for dirpath, dirnames, filenames in os.walk(root):
        # skip hidden / cache dirs
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            p = Path(dirpath) / name
            if p.suffix.lower() in exts:
                yield p


def load_license_overrides(repo_root: Path) -> dict[str, dict]:
    """Match registry names against art/provenance/model-licenses.yaml keys (substring)."""
    try:
        import yaml  # optional
    except ImportError:
        yaml = None

    path = repo_root / "art" / "provenance" / "model-licenses.yaml"
    if not path.is_file():
        return {}
    text = path.read_text(encoding="utf-8")
    if yaml is not None:
        data = yaml.safe_load(text) or {}
        return data.get("models") or {}

    # Minimal fallback without PyYAML: only extract known keys we care about.
    overrides: dict[str, dict] = {}
    for key in (
        "pixelArtDiffusionXL_spriteShaper",
        "ArsMJStyleSDXL_-_Pixel_Art",
        "z-image",
    ):
        if key in text:
            if "APPROVED_FOR_GENERATED_ASSETS" in text or "GREEN" in text:
                overrides[key] = {
                    "license_status": "GREEN",
                    "shipping_status": "APPROVED_FOR_GENERATED_ASSETS",
                }
    return overrides


def apply_license(record: ModelRecord, overrides: dict[str, dict]) -> ModelRecord:
    stem = Path(record.name).stem
    for key, meta in overrides.items():
        if key.lower() in stem.lower() or stem.lower() in key.lower():
            record.license_status = meta.get("license_status", record.license_status)
            record.shipping_status = meta.get(
                "shipping_status", record.shipping_status
            )
            break
    return record


def scan_models(model_root: Path, repo_root: Path | None = None) -> list[ModelRecord]:
    root = model_root.resolve()
    overrides = load_license_overrides(repo_root) if repo_root else {}
    records: list[ModelRecord] = []
    for path in iter_model_files(root):
        rel = str(path.relative_to(root)).replace("\\", "/")
        rec = ModelRecord(
            path=str(path),
            rel_path=rel,
            name=path.name,
            sha256=_sha256_file(path),
            size_bytes=path.stat().st_size,
            role=_guess_role(path),
            format=_guess_format(path),
        )
        rec = apply_license(rec, overrides)
        records.append(rec)
    records.sort(key=lambda r: r.rel_path.lower())
    return records


def ensure_db(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS model_registry (
            sha256 TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            rel_path TEXT NOT NULL,
            path TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            role TEXT NOT NULL,
            format TEXT NOT NULL,
            license_status TEXT NOT NULL,
            shipping_status TEXT NOT NULL,
            scanned_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    conn.commit()
    return conn


def persist_registry(records: list[ModelRecord], db_path: Path) -> None:
    conn = ensure_db(db_path)
    try:
        conn.execute("DELETE FROM model_registry")
        conn.executemany(
            """
            INSERT INTO model_registry
            (sha256, name, rel_path, path, size_bytes, role, format, license_status, shipping_status)
            VALUES (:sha256, :name, :rel_path, :path, :size_bytes, :role, :format,
                    :license_status, :shipping_status)
            """,
            [asdict(r) for r in records],
        )
        conn.commit()
    finally:
        conn.close()


def records_to_json(records: list[ModelRecord]) -> str:
    return json.dumps([asdict(r) for r in records], indent=2)
