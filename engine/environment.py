"""
Env setup and cloning logic.

Creates and configures the ygo-env environment (deck path, script path).
Use create_env() to get an env (or wrapper) you can reset/step.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Optional

# Optional: set before importing to help engine find Lua scripts
YGO_ENV_ROOT: Optional[str] = os.environ.get("YGO_ENV_ROOT")


def create_env(
    deck_path: str | Path,
    ygo_env_root: str | Path | None = None,
    seed: Optional[int] = None,
    player: int = 0,
    engine_verbose: bool = False,
) -> Any:
    """
    Create a Yu-Gi-Oh! env (ygoenv) ready for reset/step.

    - deck_path: path to a .ydk deck file (used when you call reset).
    - ygo_env_root: root of ygo-env (e.g. petrademia/ygo-env) or sbl1996/ygo-agent clone.
      If not set, uses env var YGO_ENV_ROOT. Required so we can add it to
      sys.path and, if needed, run from a dir that has Lua scripts.
    - seed: optional RNG seed for reproducible hands.

    Returns a YgoEnvWrapper if ygoenv is available; otherwise raises
    with instructions to set up ygo-env.
    """
    root = ygo_env_root or YGO_ENV_ROOT
    if not root:
        raise RuntimeError(
            "ygo-env root not set. Clone petrademia/ygo-env (or see docs/ENGINE_SETUP.md), build it, then either:\n"
            "  export YGO_ENV_ROOT=/path/to/ygo-env\n"
            "  or pass ygo_env_root= to create_env(). See docs/ENGINE_SETUP.md"
        )
    root = Path(root).resolve()
    if not root.is_dir():
        raise RuntimeError(f"YGO_ENV_ROOT is not a directory: {root}")

    # So we can import ygoenv
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    try:
        import ygoenv  # type: ignore
    except ImportError as e:
        raise RuntimeError(
            "Could not import ygoenv. From the ygo-env repo run:\n"
            "  xmake f -m release -y && xmake && make\n"
            "Then run your script from the ygo-env directory (or ensure a symlink\n"
            "to third_party/ygopro-scripts exists in your cwd). See docs/ENGINE_SETUP.md"
        ) from e

    from engine.wrapper import YgoEnvWrapper

    wrapper = YgoEnvWrapper(
        deck_path=Path(deck_path),
        ygo_env_root=root,
        seed=seed,
        player=player,
        engine_verbose=engine_verbose,
    )
    return wrapper
