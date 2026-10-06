"""Upload tilesets (MBTiles, GeoTIFF) to Mapbox with the Uploads API.

See https://docs.mapbox.com/api/maps/uploads/. The token must be a secret token with the
``uploads:write`` scope.
"""

import re
import time
from pathlib import Path

import boto3
import requests
from rich.progress import Progress

UPLOADS_API = "https://api.mapbox.com/uploads/v1"
REQUEST_TIMEOUT = 30
TILESET_NAME_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,32}")


def validate_tileset_name(tileset: str) -> None:
    """Raise ``ValueError`` unless ``tileset`` is a valid Mapbox tileset name.

    The name excludes the ``username.`` prefix: at most 32 letters, digits, ``-`` or ``_``.
    """
    if not TILESET_NAME_PATTERN.fullmatch(tileset):
        raise ValueError(
            f"Invalid tileset name {tileset!r}: use 1 to 32 letters, digits, '-' or '_'."
        )


def get_s3_credentials(username: str, token: str) -> dict:
    """Request temporary S3 credentials for Mapbox's staging bucket."""
    response = requests.post(
        f"{UPLOADS_API}/{username}/credentials",
        params={"access_token": token},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()


def upload_to_staging(source: Path, credentials: dict) -> None:
    """Upload ``source`` to the staging bucket described by ``credentials``."""
    session = boto3.Session(
        aws_access_key_id=credentials["accessKeyId"],
        aws_secret_access_key=credentials["secretAccessKey"],
        aws_session_token=credentials["sessionToken"],
    )
    s3 = session.client("s3", region_name="us-east-1", endpoint_url="https://s3.amazonaws.com")
    s3.upload_file(str(source), credentials["bucket"], credentials["key"])


def create_upload(username: str, token: str, credentials: dict, tileset: str, name: str) -> str:
    """Ask Mapbox to create or replace ``username.tileset`` from the staged file.

    Returns:
        The id of the upload, used to poll its status.
    """
    response = requests.post(
        f"{UPLOADS_API}/{username}",
        params={"access_token": token},
        json={"url": credentials["url"], "tileset": f"{username}.{tileset}", "name": name},
        timeout=REQUEST_TIMEOUT,
    )
    response.raise_for_status()
    return response.json()["id"]


def wait_for_upload(
    username: str,
    token: str,
    upload_id: str,
    poll_seconds: float = 5,
    timeout_seconds: float = 3600,
) -> dict:
    """Poll an upload until Mapbox finishes processing it.

    Returns:
        The final upload status.

    Raises:
        RuntimeError: If Mapbox reports an error for the upload.
        TimeoutError: If the upload is not complete after ``timeout_seconds``.
    """
    deadline = time.monotonic() + timeout_seconds
    with Progress() as progress:
        task = progress.add_task("Processing tileset in Mapbox", total=100)
        while True:
            response = requests.get(
                f"{UPLOADS_API}/{username}/{upload_id}",
                params={"access_token": token},
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
            status = response.json()

            if status["error"]:
                raise RuntimeError(f"Mapbox upload {upload_id} failed: {status['error']}")
            progress.update(task, completed=round(status["progress"] * 100))
            if status["complete"]:
                return status
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Mapbox upload {upload_id} not complete after {timeout_seconds}s"
                )
            time.sleep(poll_seconds)


def upload_tileset(
    source: Path,
    tileset: str,
    username: str,
    token: str,
    name: str | None = None,
) -> dict:
    """Upload ``source`` to Mapbox as ``username.tileset`` and wait until it is ready.

    Args:
        source: File to upload (``.mbtiles``, ``.tif``, ``.geojson``, ...).
        tileset: Tileset name without the ``username.`` prefix.
        username: Mapbox account name.
        token: Mapbox secret token with the ``uploads:write`` scope.
        name: Display name in Mapbox Studio. Defaults to ``tileset``.

    Returns:
        The final upload status.
    """
    validate_tileset_name(tileset)
    credentials = get_s3_credentials(username, token)
    upload_to_staging(source, credentials)
    upload_id = create_upload(username, token, credentials, tileset, name or tileset)
    return wait_for_upload(username, token, upload_id)
