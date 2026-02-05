"""Run version bump, clean dist, build, then twine upload. Used by: pipenv run release."""
from __future__ import annotations

import glob
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"
DIST_DIR = ROOT / "dist"

VERSION_PATTERN = re.compile(r'^version\s*=\s*["\'](\d+)\.(\d+)\.(\d+)["\']', re.MULTILINE)
VERSION_REPLACEMENT = 'version = "{major}.{minor}.{patch}"'


def get_current_version() -> tuple[int, int, int]:
    text = PYPROJECT.read_text(encoding="utf-8")
    m = VERSION_PATTERN.search(text)
    if not m:
        raise SystemExit("Could not find version in pyproject.toml")
    return int(m.group(1)), int(m.group(2)), int(m.group(3))


def bump_patch(major: int, minor: int, patch: int) -> tuple[int, int, int]:
    return major, minor, patch + 1


def set_version(major: int, minor: int, patch: int) -> None:
    new_version = f"{major}.{minor}.{patch}"
    text = PYPROJECT.read_text(encoding="utf-8")
    text = VERSION_PATTERN.sub(
        VERSION_REPLACEMENT.format(major=major, minor=minor, patch=patch), text, count=1
    )
    PYPROJECT.write_text(text, encoding="utf-8")
    print(f"Bumped version to {new_version}")


def clean_dist() -> None:
    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print("Cleaned dist/")
    DIST_DIR.mkdir(parents=True, exist_ok=True)


def main() -> int:
    major, minor, patch = get_current_version()
    major, minor, patch = bump_patch(major, minor, patch)
    set_version(major, minor, patch)
    clean_dist()

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
