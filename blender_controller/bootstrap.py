from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

if "--" in sys.argv:
    sys.argv = [sys.argv[0], *sys.argv[sys.argv.index("--") + 1 :]]


def _main() -> None:
    from blender_controller.host import main

    main()

if __name__ == "__main__":  # pragma: no cover - exercised inside Blender runtime
    _main()
