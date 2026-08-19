"""Compatibility shim — install with `pip install -e .` and import from `icaa`."""
from icaa.generate import *  # noqa: F403

if __name__ == '__main__':
    from icaa.generate import main

    main()
