"""Download and unpack source files."""

import zipfile
from pathlib import Path

import requests


def download_file(url: str, dest: Path, timeout: float = 60) -> Path:
    """Stream ``url`` to ``dest``, creating parent directories as needed.

    Args:
        url: URL of the file to download.
        dest: Local path to write the file to.
        timeout: Seconds to wait for the server to connect or send data.

    Returns:
        The path the file was written to.

    Raises:
        requests.HTTPError: If the server answers with an error status.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    with requests.get(url, stream=True, timeout=timeout) as response:
        response.raise_for_status()
        with dest.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1024 * 1024):
                file.write(chunk)
    return dest


def unzip(zip_path: Path, dest: Path | None = None) -> Path:
    """Extract ``zip_path`` into ``dest``.

    Args:
        zip_path: Path to the zip archive.
        dest: Directory to extract into. Defaults to a folder next to the archive with the
            same name, without the ``.zip`` suffix.

    Returns:
        The directory the archive was extracted into.
    """
    dest = dest or zip_path.with_suffix("")
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    return dest
