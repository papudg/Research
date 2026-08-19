"""Compatibility shim — install with `pip install -e .` and import from `icaa`."""
from icaa.joint_policy_comparison import *  # noqa: F403

if __name__ == '__main__':
    from icaa.joint_policy_comparison import main

    main()
