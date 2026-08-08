#!/usr/bin/env python3
"""Purrden Art Factory CLI.

Examples:
  python tools/art-factory/cli/art.py models scan
  python tools/art-factory/cli/art.py qa path/to/sprite.png
  python tools/art-factory/cli/art.py licenses
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "art-factory"))

from purrden_art.qa import qa_png, report_json  # noqa: E402
from purrden_art.registry import (  # noqa: E402
    persist_registry,
    records_to_json,
    scan_models,
)


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

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
