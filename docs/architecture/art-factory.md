# Art Factory architecture (Phase 0)

Developer-only build-time pipeline. **Never** part of the shipped PWA or cloud runtime.

## Boundary

```text
asset-spec YAML  →  prompt plan  →  constrained Comfy graph  →  raw PNG
       ↓                                                         ↓
 style bible                                              pixel repair
       ↓                                                         ↓
 model registry (SHA + license)  ←  hard QA  ←  32×32 quantized sprite
                                                         ↓
                                              human promote → art/accepted + provenance
```

## State machine

```text
CREATED → SPEC_VALIDATED → MODELS_RESOLVED → PLANNED → GENERATING
  → REPAIRING → HARD_QA → CRITIQUE (skipped Phase 0) → REVIEW
  → PROMOTED | FAILED
```

Implemented in `tools/art-factory/purrden_art/pipeline.py` as plain Python — not LangGraph/AutoGPT.

## ComfyUI client

`purrden_art/comfy_client.py` ports **concepts** from private `z-image-studio` (validate → submit →
history/queue reconcile → contained download). Purrden does **not** depend on that private repo.

Rules:

- Loopback URL only (unless `PURRDEN_ART_ALLOW_REMOTE_COMFY=1`)
- No path traversal in model/LoRA names
- Dimensions / steps / CFG / LoRA strength clamped
- Only allow-listed node `class_type`s in submitted graphs
- Downloads only into the job workbench directory

## Dry-run vs live

| Mode | Generation | Promote target |
|---|---|---|
| default (`art job SPEC`) | synthetic fixture PNG | `.art-factory/workbench/.../promoted-dry/` |
| `--live` | local ComfyUI | `art/accepted/<asset>/` + provenance |

CI always uses dry-run. Live generation is workstation-only.

## CLI

```bash
python tools/art-factory/cli/art.py models scan
python tools/art-factory/cli/art.py plan art/specs/cat-mizzle-v1.yaml
python tools/art-factory/cli/art.py job art/specs/cat-mizzle-v1.yaml --promote
python tools/art-factory/cli/art.py comfy ping          # requires ComfyUI
python tools/art-factory/cli/art.py job SPEC --live     # requires ComfyUI
```
