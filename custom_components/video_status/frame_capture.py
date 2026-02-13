"""RTSP frame capture using ffmpeg subprocess."""
from __future__ import annotations

import io
import logging
import subprocess

from PIL import Image

_LOGGER = logging.getLogger(__name__)

FFMPEG_TIMEOUT = 30


def capture_frame_sync(rtsp_url: str) -> Image.Image | None:
    """Capture a single frame from an RTSP stream using ffmpeg.

    This is a blocking call and must be run in an executor.
    """
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
            _LOGGER.error("ffmpeg exited with code %d: %s", result.returncode, stderr)
            return None

        if not result.stdout:
            _LOGGER.error("ffmpeg produced no output")
            return None

        return Image.open(io.BytesIO(result.stdout))

    except subprocess.TimeoutExpired:
        _LOGGER.error("ffmpeg timed out after %d seconds", FFMPEG_TIMEOUT)
        return None
    except Exception:
        _LOGGER.exception("Error capturing frame from %s", rtsp_url)
        return None


async def async_capture_frame(hass, rtsp_url: str) -> Image.Image | None:
    """Capture a single frame from an RTSP stream asynchronously."""
    return await hass.async_add_executor_job(capture_frame_sync, rtsp_url)


def validate_rtsp_url(url: str) -> bool:
    """Check if the URL looks like a valid RTSP URL."""
    return url.lower().startswith(("rtsp://", "rtsps://"))
