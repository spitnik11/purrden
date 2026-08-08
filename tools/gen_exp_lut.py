"""Generate the versioned integer exp lookup table (the cross-runtime compatibility contract).

Both the TypeScript/JS and Python spawn engines READ this committed table instead of calling
exp() at spawn time, so the two runtimes can never disagree on floating-point exponentiation.

weights[i] = round(exp(-(step * i) / 1000) * scale), for i in 0..max_index
  index i  ->  a score-difference of (step*i) milli-logits below the top candidate
  scale    ->  fixed-point factor so the smallest bucket is still a nonzero integer

Run:  python tools/gen_exp_lut.py   (writes content/exp_lut.json)
"""
import json
import math
import os

VERSION = "exp-lut:v1"
SCALE = 1_000_000_000          # exp(0)*scale = 1e9; exp(-16)*scale ~= 113 (still nonzero)
STEP_MILLILOGITS = 10          # score-difference resolution
MAX_INDEX = 1600               # 1600 * 10 = 16000 mlog = e^-16 clamp floor

def main() -> None:
    weights = [round(math.exp(-(STEP_MILLILOGITS * i) / 1000.0) * SCALE) for i in range(MAX_INDEX + 1)]
    assert weights[0] == SCALE, weights[0]
    assert weights[-1] > 0, "clamp floor must stay nonzero so no eligible cat gets weight 0"
    assert all(a >= b for a, b in zip(weights, weights[1:])), "table must be monotonically non-increasing"
    out = {
        "version": VERSION,
        "scale": SCALE,
        "step_millilogits": STEP_MILLILOGITS,
        "max_index": MAX_INDEX,
        "weights": weights,
    }
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    path = os.path.join(here, "content", "exp_lut.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"wrote {path}: {len(weights)} weights, scale={SCALE}, "
          f"top={weights[0]}, floor={weights[-1]}")

if __name__ == "__main__":
    main()
