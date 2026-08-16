"""Art Factory unit tests — no ComfyUI required."""
from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools" / "art-factory"))

from purrden_art.comfy_client import (  # noqa: E402
    ComfyValidationError,
    GenerationRequest,
    LoraRef,
    assert_safe_model_name,
    build_sdxl_pixel_workflow,
)
from purrden_art.pipeline import JobState, run_job  # noqa: E402
from purrden_art.prompt_compiler import compile_plan  # noqa: E402
from purrden_art.repair import make_fixture_cat_png, remove_edge_background, repair_to_sprite  # noqa: E402


class ComfyValidationTests(unittest.TestCase):
    def test_path_traversal_rejected(self):
        with self.assertRaises(ComfyValidationError):
            assert_safe_model_name("../evil.safetensors")
        with self.assertRaises(ComfyValidationError):
            assert_safe_model_name("foo/bar.safetensors")

    def test_lora_strength_bounds(self):
        with self.assertRaises(ComfyValidationError):
            LoraRef("x.safetensors", 2.0).validated()

    def test_workflow_only_allowed_nodes(self):
        req = GenerationRequest(
            positive="Pixel Art, 8 bit, cat, fewP",
            checkpoint="pixelArtDiffusionXL_spriteShaper.safetensors",
            loras=[LoraRef("ArsMJStyleSDXL_-_Pixel_Art.safetensors", 0.55)],
        )
        wf = build_sdxl_pixel_workflow(req)
        classes = {n["class_type"] for n in wf.values()}
        allowed = {
            "CheckpointLoaderSimple",
            "LoraLoader",
            "CLIPTextEncode",
            "EmptyLatentImage",
            "KSampler",
            "VAEDecode",
            "SaveImage",
        }
        self.assertTrue(classes <= allowed)
        self.assertIn("LoraLoader", classes)


class RepairTests(unittest.TestCase):
    def test_opaque_edge_background_becomes_transparent(self):
        from PIL import Image

        im = Image.new("RGBA", (12, 12), (231, 220, 190, 255))
        for y in range(3, 9):
            for x in range(4, 8):
                im.putpixel((x, y), (80, 100, 125, 255))
        repaired = remove_edge_background(im)
        self.assertEqual(repaired.getpixel((0, 0))[3], 0)
        self.assertEqual(repaired.getpixel((5, 5))[3], 255)

        inset = Image.new("RGBA", (14, 14), (0, 0, 0, 0))
        for y in range(2, 12):
            for x in range(2, 12):
                inset.putpixel((x, y), (231, 220, 190, 255))
        inset.putpixel((7, 7), (80, 100, 125, 255))
        repaired = remove_edge_background(inset)
        self.assertEqual(repaired.getpixel((2, 2))[3], 0)
        self.assertEqual(repaired.getpixel((7, 7))[3], 255)

    def test_fixture_repairs_to_32_and_passes_qa(self):
        with tempfile.TemporaryDirectory() as td:
            raw = make_fixture_cat_png(Path(td) / "raw.png", size=256)
            out = Path(td) / "out.png"
            result = repair_to_sprite(raw, out, run_qa=True)
            self.assertTrue(out.is_file())
            self.assertEqual(result.native_size, (32, 32))
            self.assertIsNotNone(result.qa)
            if not result.qa.passed:
                self.fail(json.dumps(result.qa.to_dict(), indent=2))


class CompilerTests(unittest.TestCase):
    def test_compile_mizzle(self):
        plan = compile_plan(
            ROOT / "art" / "specs" / "cat-mizzle-v1.yaml",
            ROOT / "art" / "workflows" / "recipes" / "cat-master-v3.yaml",
            seed=7,
        )
        self.assertEqual(plan.asset_id, "cat:mizzle:v1")
        self.assertTrue(plan.positive.startswith("Pixel Art"))
        self.assertIn("fewP", plan.positive)
        self.assertIn("manyP", plan.negative)
        req = plan.to_generation_request()
        v = req.validated()
        self.assertEqual(v.seed, 7)


class PipelineDryRunTests(unittest.TestCase):
    def test_dry_run_reaches_review_or_promoted(self):
        job = run_job(
            ROOT / "art" / "specs" / "cat-mizzle-v1.yaml",
            repo_root=ROOT,
            dry_run=True,
            seed=99,
            auto_promote=False,
        )
        self.assertIn(job.state, {JobState.REVIEW, JobState.PROMOTED})
        self.assertIsNone(job.error)
        states = [e.state for e in job.events]
        self.assertIn(JobState.SPEC_VALIDATED.value, states)
        self.assertIn(JobState.PLANNED.value, states)
        self.assertIn(JobState.HARD_QA.value, states)

    def test_dry_run_promote_writes_provenance(self):
        job = run_job(
            ROOT / "art" / "specs" / "cat-tabby-v1.yaml",
            repo_root=ROOT,
            dry_run=True,
            seed=1,
            auto_promote=True,
        )
        self.assertEqual(job.state, JobState.PROMOTED)
        self.assertTrue(job.accepted_path and Path(job.accepted_path).is_file())
        self.assertTrue(job.provenance_path and Path(job.provenance_path).is_file())
        prov = json.loads(Path(job.provenance_path).read_text(encoding="utf-8"))
        self.assertTrue(prov["asset_id"].startswith("cat:tabby:v1"))
        self.assertTrue(prov["dry_run"])
        self.assertEqual(len(prov["asset_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
