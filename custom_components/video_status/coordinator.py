"""DataUpdateCoordinator for Video Status."""
from __future__ import annotations

from datetime import datetime, timedelta
import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api_classifier import APIClassifier
from .classifier import LocalClassifier, crop_roi
from .const import (
    CONF_API_KEY,
    CONF_API_MODEL,
    CONF_INFERENCE_MODE,
    CONF_PASSWORD,
    CONF_ROI_H,
    CONF_ROI_W,
    CONF_ROI_X,
    CONF_ROI_Y,
    CONF_RTSP_URL,
    CONF_SCAN_INTERVAL,
    CONF_STATES,
    CONF_USERNAME,
    DEFAULT_API_MODEL,
    DEFAULT_ROI_H,
    DEFAULT_ROI_W,
    DEFAULT_ROI_X,
    DEFAULT_ROI_Y,
    DEFAULT_SCAN_INTERVAL,
    INFERENCE_API,
    INFERENCE_LOCAL,
    MODEL_FILE,
    STORAGE_DIR,
    TRAINING_DIR,
)
from .frame_capture import build_rtsp_url, capture_frame_sync

_LOGGER = logging.getLogger(__name__)


class VideoStatusCoordinator(DataUpdateCoordinator[dict]):
    """Periodically capture an RTSP frame and classify it."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self.rtsp_url: str = build_rtsp_url(
            entry.data[CONF_RTSP_URL],
            username=entry.data.get(CONF_USERNAME),
            password=entry.data.get(CONF_PASSWORD),
        )
        self.inference_mode: str = entry.data[CONF_INFERENCE_MODE]
        self.states: list[str] = [
            s.strip()
            for s in entry.data.get(CONF_STATES, "").split(",")
            if s.strip()
        ]

        scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

        # Storage paths under <config>/video_status/<entry_id>/
        self.storage_path = Path(hass.config.path(STORAGE_DIR)) / entry.entry_id
        self.training_path = self.storage_path / TRAINING_DIR
        self.model_path = self.storage_path / MODEL_FILE

        # Last captured frame (full, before ROI crop)
        self.last_frame: Image.Image | None = None

        # Target state for the Capture Sample button (set by the select entity)
        self.capture_target_state: str = self.states[0] if self.states else ""

        # Classifiers
        self.local_classifier = LocalClassifier()
        self.api_classifier: APIClassifier | None = None

        if self.inference_mode == INFERENCE_API:
            self.api_classifier = APIClassifier(
                api_key=entry.data.get(CONF_API_KEY, ""),
                model=entry.data.get(CONF_API_MODEL, DEFAULT_API_MODEL),
                states=self.states,
            )

        # Try loading an existing trained model
        self.model_loaded = self.local_classifier.load(self.model_path)

        # Create training folders so the user can drop images in
        self._ensure_training_dirs()

        super().__init__(
            hass,
            _LOGGER,
            name=f"Video Status ({entry.title})",
            update_interval=timedelta(seconds=scan_interval),
            config_entry=entry,
        )

    # ------------------------------------------------------------------
    # ROI helpers
    # ------------------------------------------------------------------

    @property
    def roi(self) -> tuple[int, int, int, int]:
        """Return (x%, y%, w%, h%) from options, falling back to defaults."""
        opts = self.entry.options
        return (
            opts.get(CONF_ROI_X, DEFAULT_ROI_X),
            opts.get(CONF_ROI_Y, DEFAULT_ROI_Y),
            opts.get(CONF_ROI_W, DEFAULT_ROI_W),
            opts.get(CONF_ROI_H, DEFAULT_ROI_H),
        )

    @property
    def has_roi(self) -> bool:
        return self.roi != (DEFAULT_ROI_X, DEFAULT_ROI_Y, DEFAULT_ROI_W, DEFAULT_ROI_H)

    def _apply_roi(self, image: Image.Image) -> Image.Image:
        """Crop *image* to the configured ROI."""
        rx, ry, rw, rh = self.roi
        return crop_roi(image, rx, ry, rw, rh)

    # ------------------------------------------------------------------
    # Camera image with ROI overlay
    # ------------------------------------------------------------------

    def get_annotated_frame_bytes(self) -> bytes | None:
        """Return the last frame as JPEG bytes with the ROI box drawn on."""
        if self.last_frame is None:
            return None

        img = self.last_frame.copy()

        # Draw ROI rectangle if not full-frame
        if self.has_roi:
            rx, ry, rw, rh = self.roi
            w, h = img.size
            left = int(w * rx / 100)
            upper = int(h * ry / 100)
            right = int(w * min(rx + rw, 100) / 100)
            lower = int(h * min(ry + rh, 100) / 100)

            draw = ImageDraw.Draw(img)
            for offset in range(2):  # 2-pixel wide outline
                draw.rectangle(
                    (left + offset, upper + offset, right - offset, lower - offset),
                    outline="lime",
                )

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_training_dirs(self) -> None:
        """Create a sub-folder per state inside the training directory."""
        for state in self.states:
            (self.training_path / state).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Polling
    # ------------------------------------------------------------------

    async def _async_update_data(self) -> dict:
        """Capture a frame and classify it."""
        try:
            frame = await self.hass.async_add_executor_job(
                capture_frame_sync, self.rtsp_url
            )
            if frame is None:
                raise UpdateFailed("Failed to capture frame from RTSP stream")

            # Store the full frame for the camera entity
            self.last_frame = frame

            # Crop to ROI for classification
            cropped = self._apply_roi(frame)

            # --- API mode ---
            if self.inference_mode == INFERENCE_API and self.api_classifier:
                state, confidence, scores = await self.api_classifier.classify(cropped)

            # --- Local mode (trained) ---
            elif self.inference_mode == INFERENCE_LOCAL and self.local_classifier.trained:
                state, confidence, scores = await self.hass.async_add_executor_job(
                    self.local_classifier.classify, cropped
                )

            # --- Local mode (not yet trained) ---
            else:
                return {
                    "state": "untrained",
                    "confidence": 0.0,
                    "scores": {},
                    "model_ready": False,
                    "last_updated": datetime.now().isoformat(),
                    "states": self.states,
                }

            return {
                "state": state,
                "confidence": round(confidence, 3),
                "scores": {k: round(v, 3) for k, v in scores.items()},
                "model_ready": True,
                "last_updated": datetime.now().isoformat(),
                "states": self.states,
            }

        except UpdateFailed:
            raise
        except Exception as err:
            raise UpdateFailed(f"Video analysis error: {err}") from err

    # ------------------------------------------------------------------
    # Services / button actions
    # ------------------------------------------------------------------

    async def async_train_model(self) -> dict[str, int]:
        """Train the local classifier from images in the training directory."""
        state_counts = await self.hass.async_add_executor_job(
            self.local_classifier.train, str(self.training_path)
        )
        await self.hass.async_add_executor_job(
            self.local_classifier.save, str(self.model_path)
        )
        self.model_loaded = True
        await self.async_request_refresh()
        return state_counts

    async def async_capture_sample(self, state_name: str) -> str:
        """Capture a frame and save it as a training sample for *state_name*."""
        if state_name not in self.states:
            raise ValueError(
                f"Unknown state '{state_name}'. Valid: {self.states}"
            )

        frame = await self.hass.async_add_executor_job(
            capture_frame_sync, self.rtsp_url
        )
        if frame is None:
            raise RuntimeError("Failed to capture frame from RTSP stream")

        # Apply ROI so training samples match what the classifier will see
        cropped = self._apply_roi(frame)

        state_dir = self.training_path / state_name
        state_dir.mkdir(parents=True, exist_ok=True)

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = state_dir / f"sample_{ts}.jpg"

        await self.hass.async_add_executor_job(cropped.save, str(filepath), "JPEG")
        _LOGGER.info("Saved training sample: %s", filepath)
        return str(filepath)
