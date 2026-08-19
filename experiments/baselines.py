"""Compatibility shim — install with `pip install -e .` and import from `icaa`."""
from icaa.baselines import *  # noqa: F403

if __name__ == '__main__':
    from icaa.baselines import main

    main()
