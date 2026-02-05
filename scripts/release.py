"""Run build then twine upload. Used by: pipenv run release."""
from __future__ import annotations

import glob
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    r = subprocess.run([sys.executable, "-m", "build"], cwd=ROOT)
    if r.returncode != 0:
        return r.returncode
    dist_files = sorted(glob.glob(str(ROOT / "dist" / "*")))
    if not dist_files:
        print("No files in dist/", file=sys.stderr)
        return 1
    return subprocess.run(
        [sys.executable, "-m", "twine", "upload", *dist_files],
        cwd=ROOT,
    ).returncode


if __name__ == "__main__":
    sys.exit(main())
