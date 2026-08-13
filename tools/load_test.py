"""Tiny dependency-free health/world load probe. Usage: python tools/load_test.py [base_url]."""
from concurrent.futures import ThreadPoolExecutor
from statistics import median
from time import perf_counter
from urllib.request import urlopen
import sys

base = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"


def hit(_: int) -> float:
    start = perf_counter()
    with urlopen(f"{base}/health", timeout=3) as response:
        assert response.status == 200
    return (perf_counter() - start) * 1000


with ThreadPoolExecutor(max_workers=20) as pool:
    times = list(pool.map(hit, range(200)))
print(f"requests=200 failures=0 median_ms={median(times):.1f} p95_ms={sorted(times)[189]:.1f}")
