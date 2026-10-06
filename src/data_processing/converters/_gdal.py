"""Run the unified ``gdal`` command line (GDAL 3.13 or newer).

The ``gdal`` command is still provisional upstream, so every call goes through here.
"""

import subprocess


def run_gdal(*args: str) -> None:
    """Run ``gdal <args>``, raising ``RuntimeError`` with GDAL's stderr on failure."""
    try:
        subprocess.run(["gdal", *args], check=True, capture_output=True, text=True)
    except FileNotFoundError as e:
        raise RuntimeError("The `gdal` command was not found; install GDAL 3.13 or newer.") from e
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"gdal {' '.join(args[:2])} failed: {e.stderr.strip()}") from e
