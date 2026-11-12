from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Optional

from py_bandcamp import BandCamp

_DEFAULT_SEEDS = [
    "https://bandcamp.com/tag/electronic",
    "https://bandcamp.com/tag/hip-hop",
    "https://bandcamp.com/tag/jazz",
    "https://bandcamp.com/tag/metal",
    "https://bandcamp.com/tag/folk",
]


def _entity_to_dict(entity) -> dict:
    if hasattr(entity, "model_dump"):
        return entity.model_dump()
    if dataclasses.is_dataclass(entity):
        return dataclasses.asdict(entity)
    return vars(entity)


def export_jsonl(
    path: str | Path,
    *,
    seeds: Optional[list[str]] = None,
    max_artists: int = 0,
    seen: Optional[set] = None,
    delay: float = 1.0,
    verbose: bool = False,
) -> int:
    import time

    path = Path(path)
    sidecar = Path(str(path) + ".seen")

    if seen is None:
        seen = set()
    if sidecar.exists():
        for line in sidecar.read_text().splitlines():
            line = line.strip()
            if line:
                seen.add(line)

    if seeds is None:
        seeds = list(_DEFAULT_SEEDS)

    count = 0
    with path.open("a", encoding="utf-8") as fout:
        for entity in BandCamp.crawl(seeds, max_artists=max_artists, seen=seen):
            row = _entity_to_dict(entity)
            fout.write(json.dumps(row, default=str) + "\n")
            fout.flush()
            count += 1
            if verbose and count % 25 == 0:
                print(f"[bandcamp] {count} entities written", flush=True)
            if delay > 0:
                time.sleep(delay)

    sidecar.write_text("\n".join(sorted(seen)) + "\n")
    return count


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Export Bandcamp entities to JSONL")
    parser.add_argument("--out", default="bandcamp.jsonl", help="Output JSONL file")
    parser.add_argument("--limit", type=int, default=0, help="Max artists (0=unlimited)")
    parser.add_argument("--seeds", nargs="+", default=None, help="Seed URLs")
    parser.add_argument("--delay", type=float, default=1.0, help="Delay between requests")
    parser.add_argument("--quiet", action="store_true", help="Suppress progress output")
    args = parser.parse_args()

    n = export_jsonl(
        args.out,
        seeds=args.seeds,
        max_artists=args.limit,
        delay=args.delay,
        verbose=not args.quiet,
    )
    print(f"Done: {n} entities written to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
