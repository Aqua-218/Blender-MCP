from __future__ import annotations

import re
import sys
from pathlib import Path

ALLOWED_PREFIXES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
)

HEADER_RE = re.compile(
    rf"^({'|'.join(ALLOWED_PREFIXES)})(\([a-z0-9][a-z0-9._/-]*\))?!?: [a-z].+$"
)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1:
        print("Expected a single commit message file path.", file=sys.stderr)
        return 1

    message_path = Path(args[0])
    header = message_path.read_text(encoding="utf-8").splitlines()[0].strip()

    if header.startswith(("Merge ", "Revert ", "fixup! ", "squash! ")):
        return 0

    if len(header) > 72:
        print("Commit subject must be 72 characters or fewer.", file=sys.stderr)
        return 1

    if not HEADER_RE.match(header):
        print(
            "Commit subject must follow Conventional Commits: <type>(<scope>): <description>",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())