from __future__ import annotations

import os
import shutil
import subprocess
import threading
from pathlib import Path
from textwrap import dedent

_REQUIRED_PACKAGES = ("react", "react-dom", "esbuild")
_NODE_CACHE_ROOT = Path(__file__).resolve().parents[2] / ".pyxle-node-cache"
_PACKAGE_JSON = (
    dedent(
        """
        {
            "name": "pyxle-ssr-test",
            "private": true,
            "version": "0.0.1",
            "type": "module",
            "dependencies": {
                "react": "^18.3.1",
                "react-dom": "^18.3.1"
            },
            "devDependencies": {
                "esbuild": "^0.24.0"
            }
        }
        """
    ).strip()
    + "\n"
)
_CACHE_LOCK = threading.Lock()


def ensure_test_node_modules(project_root: Path) -> None:
    """Populate ``node_modules`` for SSR tests using an auto-managed npm cache."""

    package_json = project_root / "package.json"
    if not package_json.exists():
        package_json.write_text(_PACKAGE_JSON, encoding="utf-8")

    dest_root = project_root / "node_modules"
    dest_root.mkdir(parents=True, exist_ok=True)

    cache_node_modules = _ensure_cached_node_modules()
    for package in _REQUIRED_PACKAGES:
        src = cache_node_modules / package
        if not src.exists():
            raise RuntimeError(f"npm cache is missing expected package '{package}'.")

        dest = dest_root / package
        if dest.exists():
            continue

        try:
            os.symlink(src, dest, target_is_directory=True)
        except (AttributeError, NotImplementedError, OSError):
            shutil.copytree(src, dest)


def _ensure_cached_node_modules() -> Path:
    cache_root = _NODE_CACHE_ROOT
    node_modules = cache_root / "node_modules"

    with _CACHE_LOCK:
        cache_root.mkdir(parents=True, exist_ok=True)
        package_json = cache_root / "package.json"
        if not package_json.exists():
            package_json.write_text(_PACKAGE_JSON, encoding="utf-8")

        missing = [pkg for pkg in _REQUIRED_PACKAGES if not (node_modules / pkg).exists()]
        if not missing:
            return node_modules

        npm_executable = shutil.which("npm")
        if npm_executable is None:
            raise RuntimeError("npm executable not found. Install Node.js to run SSR renderer tests.")

        process = subprocess.run(  # noqa: S603
            [npm_executable, "install"],
            cwd=str(cache_root),
            capture_output=True,
            text=True,
            check=False,
        )
        if process.returncode != 0:
            raise RuntimeError(
                "Failed to install Node dependencies for SSR tests:\n{output}".format(
                    output=process.stderr or process.stdout
                )
            )

        still_missing = [pkg for pkg in _REQUIRED_PACKAGES if not (node_modules / pkg).exists()]
        if still_missing:
            raise RuntimeError(
                "npm install completed but packages are missing: {packages}".format(packages=", ".join(still_missing))
            )

    return node_modules