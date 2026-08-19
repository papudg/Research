"""Load, save, and export fixed blueprint manifests."""
from __future__ import annotations

import json

from icaa.multipolicy_benchmark import build_manifest
from icaa.paths import MANIFEST_DIR


def manifest_path(seed: int, count: int = 80) -> str:
    return str(MANIFEST_DIR / f'manifest_seed{seed}_{count}.json')


def export_manifest(seed: int = 42, count: int = 80) -> str:
    manifest = build_manifest(seed=seed, count=count)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)
    path = manifest_path(seed, count)
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(manifest, handle, indent=2)
    return path


def load_manifest(seed: int = 42, count: int = 80):
    path = manifest_path(seed, count)
    if not MANIFEST_DIR.joinpath(f'manifest_seed{seed}_{count}.json').exists():
        return build_manifest(seed=seed, count=count)
    with open(path, encoding='utf-8') as handle:
        return json.load(handle)


def export_robustness_manifests(seeds=(42, 43, 44, 45, 46), count: int = 80) -> list[str]:
    return [export_manifest(seed=seed, count=count) for seed in seeds]
