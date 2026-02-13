"""RTSP frame capture using ffmpeg subprocess."""
from __future__ import annotations

import io
import logging
import subprocess
from urllib.parse import quote, urlparse, urlunparse

from PIL import Image

_LOGGER = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30


def build_rtsp_url(
    base_url: str,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Inject credentials into an RTSP URL if provided.

    Existing credentials embedded in *base_url* are replaced when both
    *username* and *password* are supplied.  Credentials are
    percent-encoded so special characters are safe.
    """
    if not username:
        return base_url

    parsed = urlparse(base_url)

    # Percent-encode user/pass to handle special chars (@ : etc.)
    netloc_auth = quote(username, safe="")
    if password:
        netloc_auth += ":" + quote(password, safe="")

    # Rebuild netloc as  user:pass@host[:port]
    host_part = parsed.hostname or ""
    if parsed.port:
        host_part += f":{parsed.port}"
    new_netloc = f"{netloc_auth}@{host_part}"

    return urlunparse(parsed._replace(netloc=new_netloc))


def _sanitise_url(url: str) -> str:
    """Strip credentials from a URL for safe logging."""
    parsed = urlparse(url)
    if parsed.username:
        host_part = parsed.hostname or ""
        if parsed.port:
            host_part += f":{parsed.port}"
        safe = urlunparse(parsed._replace(netloc=f"***@{host_part}"))
        return safe
    return url


def capture_frame_sync(rtsp_url: str) -> Image.Image | None:
    """Capture a single frame from an RTSP stream using ffmpeg.

    This is a blocking call and must be run in an executor.
    """
    safe_url = _sanitise_url(rtsp_url)
    try:
        result = subprocess.run(
            [
                "ffmpeg",
                "-rtsp_transport", "tcp",
                "-i", rtsp_url,
                "-frames:v", "1",
                "-f", "image2",
                "-vcodec", "mjpeg",
                "-q:v", "2",
                "-loglevel", "error",
                "pipe:1",
            ],
            capture_output=True,
            timeout=FFMPEG_TIMEOUT,
        )

        if result.returncode != 0:
            stderr = result.stderr.decode(errors="replace")[:500]
            _LOGGER.error(
                "ffmpeg exited with code %d for %s: %s",
                result.returncode, safe_url, stderr,
            )
            return None

        if not result.stdout:
            _LOGGER.error("ffmpeg produced no output for %s", safe_url)
            return None

        return Image.open(io.BytesIO(result.stdout))

    except subprocess.TimeoutExpired:
        _LOGGER.error("ffmpeg timed out after %ds for %s", FFMPEG_TIMEOUT, safe_url)
        return None
    except Exception:
        _LOGGER.exception("Error capturing frame from %s", safe_url)
        return None


async def async_capture_frame(hass, rtsp_url: str) -> Image.Image | None:
    """Capture a single frame from an RTSP stream asynchronously."""
    return await hass.async_add_executor_job(capture_frame_sync, rtsp_url)


def validate_rtsp_url(url: str) -> bool:
    """Check if the URL looks like a valid RTSP URL."""
    return url.lower().startswith(("rtsp://", "rtsps://"))
