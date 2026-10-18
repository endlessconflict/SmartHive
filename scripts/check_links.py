"""Fail when a relative link in any Markdown file points at a file that does not exist.

    python scripts/check_links.py [root]

Anchors and web links are not checked.
"""

import re
import sys
from pathlib import Path

SKIP = {".git", ".venv", "node_modules", "vendor"}
LINK = re.compile(r"\]\(([^)#\s]+)(#[^)]*)?\)")


def broken_links(root: Path) -> list[str]:
    bad = []
    for f in sorted(root.rglob("*.md")):
        if SKIP & set(f.relative_to(root).parts):
            continue
        for m in LINK.finditer(f.read_text(encoding="utf-8")):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            if not (f.parent / target).resolve().exists():
                bad.append(f"{f.relative_to(root)} -> {target}")
    return bad


if __name__ == "__main__":
    problems = broken_links(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print("\n".join(problems) or "no broken links")
    sys.exit(1 if problems else 0)
