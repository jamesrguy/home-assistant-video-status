"""Constants for the Video Status integration."""
from __future__ import annotations

DOMAIN = "video_status"
PLATFORMS: list[str] = ["sensor"]

# Configuration keys
CONF_RTSP_URL = "rtsp_url"
CONF_INFERENCE_MODE = "inference_mode"
CONF_STATES = "states"
CONF_SCAN_INTERVAL = "scan_interval"
CONF_API_KEY = "api_key"
CONF_API_MODEL = "api_model"

# Inference modes
INFERENCE_LOCAL = "local"
INFERENCE_API = "api"

# Defaults
DEFAULT_SCAN_INTERVAL = 30
DEFAULT_API_MODEL = "google/gemini-flash-1.5-8b"
DEFAULT_STATES = "open,closed"

# Storage paths (relative to hass config dir)
STORAGE_DIR = "video_status"
TRAINING_DIR = "training"
MODEL_FILE = "model.json"
