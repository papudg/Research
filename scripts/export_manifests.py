#!/usr/bin/env python
"""Export fixed blueprint manifests for seeds 42-46 to data/manifests/."""
from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = os.path.join(ROOT, 'src')
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from icaa.manifest import export_robustness_manifests  # noqa: E402


def main() -> int:
    paths = export_robustness_manifests()
    for path in paths:
        print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
