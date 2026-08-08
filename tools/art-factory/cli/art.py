#!/usr/bin/env python3
"""Purrden Art Factory CLI.

Examples:
  python tools/art-factory/cli/art.py models scan
  python tools/art-factory/cli/art.py qa path/to/sprite.png
  python tools/art-factory/cli/art.py licenses
  python tools/art-factory/cli/art.py plan art/specs/cat-mizzle-v1.yaml
  python tools/art-factory/cli/art.py job art/specs/cat-mizzle-v1.yaml --dry-run --promote
  python tools/art-factory/cli/art.py comfy ping
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "art-factory"))

from purrden_art.comfy_client import (  # noqa: E402
    ComfyClient,
    ComfyError,
    ComfyUnreachable,
    GenerationRequest,
    build_sdxl_pixel_workflow,
)
from purrden_art.pipeline import run_job  # noqa: E402
from purrden_art.prompt_compiler import compile_plan  # noqa: E402
from purrden_art.qa import qa_png, report_json  # noqa: E402
from purrden_art.registry import (  # noqa: E402
    persist_registry,
    records_to_json,
    scan_models,
)
from purrden_art.repair import repair_to_sprite  # noqa: E402


def cmd_models_scan(args: argparse.Namespace) -> int:
    model_root = Path(
        args.root
        or os.environ.get("PURRDEN_ART_MODEL_ROOT")
        or r"C:\Users\losth\Desktop\pixel art models"
    )
    db = ROOT / ".art-factory" / "art.db"
    try:
        records = scan_models(model_root, repo_root=ROOT)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 2
    persist_registry(records, db)
    print(records_to_json(records))
    print(
        f"\n# scanned {len(records)} file(s) from {model_root} → {db}",
        file=sys.stderr,
    )
    return 0


def cmd_qa(args: argparse.Namespace) -> int:
    report = qa_png(
        Path(args.path),
        expect_w=args.width,
        expect_h=args.height,
        max_colors=args.max_colors,
    )
    print(report_json(report))
    return 0 if report.passed else 1


def cmd_licenses(_args: argparse.Namespace) -> int:
    path = ROOT / "art" / "provenance" / "model-licenses.yaml"
    print(path.read_text(encoding="utf-8"))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    recipe = Path(args.recipe) if args.recipe else (
        ROOT / "art" / "workflows" / "recipes" / "cat-master-v3.yaml"
    )
    plan = compile_plan(Path(args.spec), recipe, seed=args.seed)
    print(json.dumps(plan.to_dict(), indent=2))
    return 0


def cmd_repair(args: argparse.Namespace) -> int:
    dest = Path(args.out) if args.out else Path(args.path).with_name(
        Path(args.path).stem + "_32.png"
    )
    result = repair_to_sprite(Path(args.path), dest, run_qa=True)
    payload = {
        "source": str(result.source),
        "repaired": str(result.repaired),
        "opaque_colors": result.opaque_colors,
        "bbox": result.bbox,
        "qa": result.qa.to_dict() if result.qa else None,
    }
    print(json.dumps(payload, indent=2))
    return 0 if result.qa and result.qa.passed else 1


def cmd_job(args: argparse.Namespace) -> int:
    job = run_job(
        Path(args.spec),
        repo_root=ROOT,
        dry_run=not args.live,
        seed=args.seed,
        comfy_url=args.comfy_url,
        auto_promote=args.promote,
    )
    print(json.dumps(job.to_dict(), indent=2))
    if job.state.value == "FAILED":
        return 1
    if job.state.value == "PROMOTED":
        return 0
    # REVIEW is success for non-promote runs
    return 0


def cmd_comfy_ping(args: argparse.Namespace) -> int:
    client = ComfyClient(args.url)
    try:
        stats = client.ping()
    except (ComfyUnreachable, ComfyError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 2
    print(json.dumps({"ok": True, "url": client.base_url, "stats": stats}, indent=2))
    return 0


def cmd_comfy_validate(args: argparse.Namespace) -> int:
    """Validate a GenerationRequest + workflow build without submitting."""
    req = GenerationRequest(
        positive=args.positive or "Pixel Art, 8 bit, cute cat sprite, fewP",
        checkpoint=args.checkpoint,
        steps=args.steps,
        cfg=args.cfg,
        seed=args.seed,
        width=args.width,
        height=args.height,
    )
    try:
        v = req.validated()
        wf = build_sdxl_pixel_workflow(v)
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "request": {
                    "checkpoint": v.checkpoint,
                    "width": v.width,
                    "height": v.height,
                    "steps": v.steps,
                    "cfg": v.cfg,
                    "seed": v.seed,
                    "positive": v.positive,
                },
                "node_count": len(wf),
                "class_types": sorted({n["class_type"] for n in wf.values()}),
            },
            indent=2,
        )
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="art", description="Purrden Art Factory")
    sub = p.add_subparsers(dest="cmd", required=True)

    m = sub.add_parser("models", help="model registry")
    m_sub = m.add_subparsers(dest="models_cmd", required=True)
    scan = m_sub.add_parser("scan", help="inventory + hash local model root")
    scan.add_argument("--root", help="override PURRDEN_ART_MODEL_ROOT")
    scan.set_defaults(func=cmd_models_scan)

    qa = sub.add_parser("qa", help="hard pixel QA on a PNG")
    qa.add_argument("path")
    qa.add_argument("--width", type=int, default=32)
    qa.add_argument("--height", type=int, default=32)
    qa.add_argument("--max-colors", type=int, default=9)
    qa.set_defaults(func=cmd_qa)

    lic = sub.add_parser("licenses", help="print model license registry")
    lic.set_defaults(func=cmd_licenses)

    plan = sub.add_parser("plan", help="compile asset spec → prompt plan")
    plan.add_argument("spec")
    plan.add_argument("--recipe")
    plan.add_argument("--seed", type=int, default=0)
    plan.set_defaults(func=cmd_plan)

    rep = sub.add_parser("repair", help="run pixel repair chain on an image")
    rep.add_argument("path")
    rep.add_argument("--out")
    rep.set_defaults(func=cmd_repair)

    job = sub.add_parser("job", help="run Art Factory state machine for one spec")
    job.add_argument("spec")
    job.add_argument(
        "--live",
        action="store_true",
        help="submit to local ComfyUI (default is dry-run fixture)",
    )
    job.add_argument(
        "--promote",
        action="store_true",
        help="auto-promote QA-passing candidate (still writes provenance)",
    )
    job.add_argument("--seed", type=int, default=42)
    job.add_argument("--comfy-url", default=None)
    job.set_defaults(func=cmd_job)

    comfy = sub.add_parser("comfy", help="ComfyUI client utilities")
    csub = comfy.add_subparsers(dest="comfy_cmd", required=True)
    ping = csub.add_parser("ping", help="GET /system_stats")
    ping.add_argument("--url", default=None)
    ping.set_defaults(func=cmd_comfy_ping)
    val = csub.add_parser("validate", help="validate request + build workflow only")
    val.add_argument("--positive", default=None)
    val.add_argument(
        "--checkpoint",
        default="pixelArtDiffusionXL_spriteShaper.safetensors",
    )
    val.add_argument("--steps", type=int, default=30)
    val.add_argument("--cfg", type=float, default=5.5)
    val.add_argument("--seed", type=int, default=0)
    val.add_argument("--width", type=int, default=512)
    val.add_argument("--height", type=int, default=512)
    val.set_defaults(func=cmd_comfy_validate)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
