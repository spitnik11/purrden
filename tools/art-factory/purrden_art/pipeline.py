"""Art Factory orchestration — explicit state machine (no LangGraph/AutoGPT).

States:
  SPEC_VALIDATED → MODELS_RESOLVED → PLANNED → GENERATING → REPAIRING
  → HARD_QA → (CRITIQUE skipped in Phase 0) → REVIEW → PROMOTED | FAILED
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable

from .comfy_client import ComfyClient, ComfyError, ComfyUnreachable, GenerationRequest
from .prompt_compiler import PromptPlan, compile_plan
from .qa import QaReport
from .repair import make_fixture_cat_png, repair_to_sprite
from .registry import ModelRecord, scan_models


class JobState(str, Enum):
    CREATED = "CREATED"
    SPEC_VALIDATED = "SPEC_VALIDATED"
    MODELS_RESOLVED = "MODELS_RESOLVED"
    PLANNED = "PLANNED"
    GENERATING = "GENERATING"
    REPAIRING = "REPAIRING"
    HARD_QA = "HARD_QA"
    CRITIQUE = "CRITIQUE"  # reserved; Phase 0 skips VLM
    REVIEW = "REVIEW"
    PROMOTED = "PROMOTED"
    FAILED = "FAILED"


TERMINAL = {JobState.PROMOTED, JobState.FAILED}


@dataclass
class JobEvent:
    state: str
    at: float
    detail: str = ""


@dataclass
class ArtJob:
    job_id: str
    asset_id: str
    state: JobState
    workbench: str
    dry_run: bool = True
    seed: int = 0
    plan: dict[str, Any] | None = None
    raw_paths: list[str] = field(default_factory=list)
    repaired_paths: list[str] = field(default_factory=list)
    qa_reports: list[dict[str, Any]] = field(default_factory=list)
    accepted_path: str | None = None
    provenance_path: str | None = None
    error: str | None = None
    events: list[JobEvent] = field(default_factory=list)
    model_hits: list[dict[str, Any]] = field(default_factory=list)

    def log(self, state: JobState, detail: str = "") -> None:
        self.state = state
        self.events.append(JobEvent(state=state.value, at=time.time(), detail=detail))

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["state"] = self.state.value
        return d


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _job_dir(root: Path, job_id: str) -> Path:
    return root / ".art-factory" / "workbench" / job_id


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_spec(spec_path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:
        raise RuntimeError("PyYAML required: pip install pyyaml") from e
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("spec root must be a mapping")
    for key in ("id", "class", "sprite", "generation"):
        if key not in data:
            raise ValueError(f"spec missing required key: {key}")
    sprite = data["sprite"]
    if sprite.get("native_width") != 32 or sprite.get("native_height") != 32:
        raise ValueError("Phase 0 only supports 32×32 cat sprites")
    if sprite.get("alpha") != "binary":
        raise ValueError("sprite.alpha must be binary")
    return data


def _load_registry_from_db(db_path: Path) -> list[ModelRecord]:
    if not db_path.is_file():
        return []
    import sqlite3

    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(
            "SELECT path, rel_path, name, sha256, size_bytes, role, format, "
            "license_status, shipping_status FROM model_registry"
        ).fetchall()
    finally:
        conn.close()
    return [
        ModelRecord(
            path=r[0],
            rel_path=r[1],
            name=r[2],
            sha256=r[3],
            size_bytes=r[4],
            role=r[5],
            format=r[6],
            license_status=r[7],
            shipping_status=r[8],
        )
        for r in rows
    ]


def resolve_models_for_plan(
    plan: PromptPlan,
    model_root: Path | None,
    repo_root: Path,
    *,
    rescan: bool = False,
) -> list[ModelRecord]:
    """Resolve models from art.db when present; full scan only if empty or rescan=True."""
    db_path = repo_root / ".art-factory" / "art.db"
    records: list[ModelRecord] = []
    if not rescan:
        records = _load_registry_from_db(db_path)
    if not records and model_root is not None and model_root.is_dir():
        records = scan_models(model_root, repo_root=repo_root)
        from .registry import persist_registry

        persist_registry(records, db_path)
    needed = {plan.checkpoint.lower()}
    for l in plan.loras:
        needed.add(l["name"].lower())
    hits = [
        r
        for r in records
        if r.name.lower() in needed
        or any(n in r.name.lower() for n in needed)
        or any(r.name.lower() in n for n in needed)
    ]
    return hits


def run_job(
    spec_path: Path,
    *,
    recipe_path: Path | None = None,
    repo_root: Path | None = None,
    model_root: Path | None = None,
    dry_run: bool = True,
    seed: int = 42,
    comfy_url: str | None = None,
    auto_promote: bool = False,
    generate_fn: Callable[[GenerationRequest, Path], list[Path]] | None = None,
) -> ArtJob:
    """Execute the Art Factory state machine for one asset spec."""
    root = repo_root or _repo_root()
    recipe_path = recipe_path or (
        root / "art" / "workflows" / "recipes" / "cat-master-v3.yaml"
    )
    job_id = f"job-{uuid.uuid4().hex[:12]}"
    wb = _job_dir(root, job_id)
    wb.mkdir(parents=True, exist_ok=True)
    (wb / "raw").mkdir(exist_ok=True)
    (wb / "repaired").mkdir(exist_ok=True)
    (wb / "qa").mkdir(exist_ok=True)

    job = ArtJob(
        job_id=job_id,
        asset_id="unknown",
        state=JobState.CREATED,
        workbench=str(wb),
        dry_run=dry_run,
        seed=seed,
    )

    try:
        # SPEC_VALIDATED
        spec = validate_spec(spec_path)
        job.asset_id = str(spec["id"])
        job.log(JobState.SPEC_VALIDATED, f"spec={spec_path.name}")

        # PLANNED (plan before models so we know what to resolve)
        plan = compile_plan(spec_path, recipe_path, seed=seed)
        job.plan = plan.to_dict()
        _write_json(wb / "plan.json", job.plan)
        job.log(JobState.PLANNED, f"plan_sha={plan.plan_sha256[:12]}")

        # MODELS_RESOLVED
        mroot = model_root or Path(
            os.environ.get(
                "PURRDEN_ART_MODEL_ROOT",
                r"C:\Users\losth\Desktop\pixel art models",
            )
        )
        hits = resolve_models_for_plan(plan, mroot, root)
        job.model_hits = [
            {
                "name": h.name,
                "sha256": h.sha256,
                "license_status": h.license_status,
                "shipping_status": h.shipping_status,
                "role": h.role,
            }
            for h in hits
        ]
        _write_json(wb / "models.json", job.model_hits)
        # In dry-run, missing models are OK; live mode requires hits for known keys
        if not dry_run and not hits:
            job.log(JobState.FAILED, "no local models resolved for live generation")
            job.error = "models not found under PURRDEN_ART_MODEL_ROOT"
            _write_json(wb / "job.json", job.to_dict())
            return job
        # shipping gate for promotion later
        blocked = [
            h
            for h in hits
            if h.shipping_status
            not in {"GREEN", "APPROVED_FOR_GENERATED_ASSETS"}
        ]
        job.log(
            JobState.MODELS_RESOLVED,
            f"hits={len(hits)} blocked_for_ship={len(blocked)}",
        )

        # GENERATING
        job.log(JobState.GENERATING, "start")
        raw_paths: list[Path] = []
        if generate_fn is not None:
            raw_paths = generate_fn(plan.to_generation_request(), wb)
        elif dry_run:
            fixture = make_fixture_cat_png(wb / "raw" / "candidate_00.png")
            raw_paths = [fixture]
            job.log(JobState.GENERATING, "dry_run fixture candidate")
        else:
            client = ComfyClient(comfy_url)
            client.ping()
            result, paths = client.generate(
                plan.to_generation_request(), wb, timeout_s=900.0
            )
            if result.status != "completed" or not paths:
                job.error = result.error or f"generation status={result.status}"
                job.log(JobState.FAILED, job.error)
                _write_json(wb / "job.json", job.to_dict())
                return job
            raw_paths = paths
            job.log(JobState.GENERATING, f"prompt_id={result.prompt_id} n={len(paths)}")

        job.raw_paths = [str(p) for p in raw_paths]

        # REPAIRING + HARD_QA
        job.log(JobState.REPAIRING, f"candidates={len(raw_paths)}")
        best: tuple[Path, QaReport] | None = None
        for i, raw in enumerate(raw_paths):
            out = wb / "repaired" / f"candidate_{i:02d}_32.png"
            repaired = repair_to_sprite(raw, out, run_qa=True)
            report = repaired.qa
            assert report is not None
            job.qa_reports.append(report.to_dict())
            _write_json(wb / "qa" / f"candidate_{i:02d}.json", report.to_dict())
            if report.passed and best is None:
                best = (repaired.repaired, report)

        job.log(JobState.HARD_QA, f"passed_any={best is not None}")

        # CRITIQUE skipped in Phase 0 (no VLM dependency)
        job.log(JobState.CRITIQUE, "skipped_phase0")

        if best is None:
            job.error = "no candidate passed hard QA"
            job.log(JobState.FAILED, job.error)
            _write_json(wb / "job.json", job.to_dict())
            return job

        # REVIEW — human gate (auto_promote only for dry-run tests / explicit flag)
        job.accepted_path = str(best[0])
        job.log(JobState.REVIEW, f"candidate={best[0].name}")

        if not auto_promote:
            # Leave in REVIEW for human promotion
            _write_json(wb / "job.json", job.to_dict())
            return job

        # PROMOTED
        if blocked and not dry_run:
            job.error = "cannot promote: model shipping_status not approved"
            job.log(JobState.FAILED, job.error)
            _write_json(wb / "job.json", job.to_dict())
            return job

        # Dry-run fixtures never enter art/accepted (shipping tree).
        # Live promotions write to art/accepted + provenance sidecars.
        if dry_run:
            accepted_dir = wb / "promoted-dry"
        else:
            accepted_dir = root / "art" / "accepted" / job.asset_id.replace(":", "_")
        accepted_dir.mkdir(parents=True, exist_ok=True)
        dest_png = accepted_dir / "idle_0.png"
        shutil.copy2(best[0], dest_png)
        prov = {
            "asset_id": f"{job.asset_id}:idle:0",
            "asset_sha256": _file_sha256(dest_png),
            "spec_sha256": plan.spec_sha256,
            "recipe_sha256": plan.recipe_sha256,
            "plan_sha256": plan.plan_sha256,
            "style_bible": "art/style-bible.yaml",
            "workflow": "constrained_sdxl_pixel_v1",
            "dry_run": dry_run,
            "seed": seed,
            "cfg": plan.cfg,
            "steps": plan.steps,
            "checkpoint": {
                "name": plan.checkpoint,
                "sha256": next(
                    (h.sha256 for h in hits if plan.checkpoint in h.name), None
                ),
                "license_status": next(
                    (
                        h.license_status
                        for h in hits
                        if plan.checkpoint in h.name
                    ),
                    "UNKNOWN",
                ),
            },
            "loras": [
                {
                    "name": l["name"],
                    "strength": l["strength"],
                    "sha256": next(
                        (h.sha256 for h in hits if l["name"] in h.name), None
                    ),
                }
                for l in plan.loras
            ],
            "repair_pipeline": "pixel-fix-v1",
            "palette": "palette:purrden-core:v1",
            "hard_qa_version": "0.1",
            "human_promotion": True,
            "job_id": job_id,
        }
        prov_path = accepted_dir / "idle_0.provenance.json"
        _write_json(prov_path, prov)
        if not dry_run:
            prov_mirror = (
                root
                / "art"
                / "provenance"
                / f"{job.asset_id.replace(':', '_')}_idle_0.json"
            )
            _write_json(prov_mirror, prov)
        job.accepted_path = str(dest_png)
        job.provenance_path = str(prov_path)
        job.log(JobState.PROMOTED, str(dest_png))
        _write_json(wb / "job.json", job.to_dict())
        return job

    except (ComfyUnreachable, ComfyError) as e:
        job.error = str(e)
        job.log(JobState.FAILED, job.error)
        _write_json(wb / "job.json", job.to_dict())
        return job
    except Exception as e:  # noqa: BLE001
        job.error = f"{type(e).__name__}: {e}"
        job.log(JobState.FAILED, job.error)
        _write_json(wb / "job.json", job.to_dict())
        return job
