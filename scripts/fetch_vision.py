"""Download the pinned SmartHive-Vision release, verify its checksums and unpack it into vendor/vision/.

    python scripts/fetch_vision.py             # download + verify + unpack models
    python scripts/fetch_vision.py --install   # also pip install the wheel into the current environment

Needs the GitHub CLI (`gh auth login`) because the vision repository is private.
"""

import argparse
import hashlib
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "vendor" / "vision"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--install", action="store_true", help="pip install the wheel into the current environment")
    args = ap.parse_args()

    lock = tomllib.loads((ROOT / "vision.lock").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    for name, expected in lock["sha256"].items():
        target = OUT / name
        if not target.exists() or sha256(target) != expected:
            subprocess.run(
                ["gh", "release", "download", f"v{lock['version']}", "-R", lock["repo"], "-p", name, "-D", str(OUT), "--clobber"],
                check=True,
            )
        if sha256(target) != expected:
            sys.exit(f"checksum mismatch for {name}: the release no longer matches vision.lock")
        print(f"ok  {name}")

    with tarfile.open(OUT / f"smarthive-models-{lock['version']}.tar.gz") as tar:
        tar.extractall(OUT, filter="data")
    if args.install:
        wheel = OUT / f"smarthive_vision-{lock['version']}-py3-none-any.whl"
        subprocess.run([sys.executable, "-m", "pip", "install", str(wheel)], check=True)


if __name__ == "__main__":
    main()
