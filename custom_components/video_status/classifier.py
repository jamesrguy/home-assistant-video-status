"""On-device image classifier using histogram and structural features.

Uses only Pillow + numpy (no heavy ML frameworks) to keep the footprint
small enough for low-powered Home Assistant hosts.

Approach:
  1. Resize the image to a fixed dimension.
  2. Extract colour histograms, spatial colour averages and edge histograms.
  3. During training, compute the mean feature vector (centroid) per state.
  4. During inference, classify by cosine similarity to each centroid.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image

_LOGGER = logging.getLogger(__name__)

# Feature extraction parameters
RESIZE_DIM = 128
HIST_BINS = 32
GRID_SIZE = 4
SOFTMAX_TEMPERATURE = 10.0

IMAGE_EXTENSIONS = frozenset((".jpg", ".jpeg", ".png", ".bmp", ".webp"))


def crop_roi(
    image: Image.Image,
    roi_x: int = 0,
    roi_y: int = 0,
    roi_w: int = 100,
    roi_h: int = 100,
) -> Image.Image:
    """Crop an image to a region of interest given as percentages (0-100).

    A full-frame ROI (0, 0, 100, 100) returns the image unchanged.
    """
    if (roi_x, roi_y, roi_w, roi_h) == (0, 0, 100, 100):
        return image

    w, h = image.size
    left = int(w * roi_x / 100)
    upper = int(h * roi_y / 100)
    right = int(w * min(roi_x + roi_w, 100) / 100)
    lower = int(h * min(roi_y + roi_h, 100) / 100)

    # Guard against degenerate boxes
    right = max(right, left + 1)
    lower = max(lower, upper + 1)

    return image.crop((left, upper, right, lower))


def extract_features(image: Image.Image) -> np.ndarray:
    """Extract a compact feature vector from an image.

    Returns a 1-D float32 array of length:
        3*HIST_BINS  (per-channel colour histograms)
      + HIST_BINS    (grayscale histogram)
      + GRID_SIZE**2 * 3  (spatial colour averages)
      + HIST_BINS    (edge intensity histogram)
      = 208 with the defaults above.
    """
    img = image.convert("RGB").resize((RESIZE_DIM, RESIZE_DIM))
    arr = np.array(img, dtype=np.float32) / 255.0

    parts: list[np.ndarray] = []

    # --- Per-channel colour histograms (96 dims) ---
    for ch in range(3):
        hist, _ = np.histogram(arr[:, :, ch], bins=HIST_BINS, range=(0.0, 1.0))
        parts.append(hist.astype(np.float32) / (hist.sum() + 1e-8))

    # --- Grayscale histogram (32 dims) ---
    gray = arr.mean(axis=2)
    hist, _ = np.histogram(gray, bins=HIST_BINS, range=(0.0, 1.0))
    parts.append(hist.astype(np.float32) / (hist.sum() + 1e-8))

    # --- Spatial colour averages (48 dims) ---
    cell_h = RESIZE_DIM // GRID_SIZE
    cell_w = RESIZE_DIM // GRID_SIZE
    for gy in range(GRID_SIZE):
        for gx in range(GRID_SIZE):
            cell = arr[
                gy * cell_h : (gy + 1) * cell_h,
                gx * cell_w : (gx + 1) * cell_w,
            ]
            parts.append(cell.mean(axis=(0, 1)))  # 3 values (RGB)

    # --- Edge intensity histogram (32 dims) ---
    # Simple gradient magnitude via finite differences
    grad_x = np.diff(gray, axis=1)  # (H, W-1)
    grad_y = np.diff(gray, axis=0)  # (H-1, W)
    # Crop to matching size
    gx_crop = grad_x[:-1, :]
    gy_crop = grad_y[:, :-1]
    edges = np.sqrt(gx_crop ** 2 + gy_crop ** 2)
    edges = edges / (edges.max() + 1e-8)
    hist, _ = np.histogram(edges, bins=HIST_BINS, range=(0.0, 1.0))
    parts.append(hist.astype(np.float32) / (hist.sum() + 1e-8))

    return np.concatenate(parts)


class LocalClassifier:
    """Nearest-centroid classifier over histogram features."""

    def __init__(self) -> None:
        self.centroids: dict[str, np.ndarray] = {}
        self.trained: bool = False

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def train(self, training_dir: str | Path) -> dict[str, int]:
        """Train from a directory tree of ``state_name/image.*`` folders.

        Returns a dict mapping each state to the number of images used.
        Raises if fewer than two valid states are found.
        """
        training_dir = Path(training_dir)
        if not training_dir.exists():
            raise FileNotFoundError(f"Training directory not found: {training_dir}")

        state_counts: dict[str, int] = {}
        new_centroids: dict[str, np.ndarray] = {}

        for state_dir in sorted(training_dir.iterdir()):
            if not state_dir.is_dir():
                continue

            state_name = state_dir.name
            features_list: list[np.ndarray] = []

            for img_path in sorted(state_dir.iterdir()):
                if img_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                try:
                    img = Image.open(img_path)
                    features_list.append(extract_features(img))
                except Exception:
                    _LOGGER.warning("Skipping unreadable image: %s", img_path)

            if not features_list:
                _LOGGER.warning("No valid images for state '%s' — skipped", state_name)
                continue

            new_centroids[state_name] = np.mean(features_list, axis=0)
            state_counts[state_name] = len(features_list)
            _LOGGER.info(
                "State '%s': trained on %d images", state_name, len(features_list)
            )

        if len(new_centroids) < 2:
            raise ValueError(
                f"Need at least 2 states with images, found {len(new_centroids)}"
            )

        self.centroids = new_centroids
        self.trained = True
        return state_counts

    # ------------------------------------------------------------------
    # Inference
    # ------------------------------------------------------------------

    def classify(
        self, image: Image.Image
    ) -> tuple[str, float, dict[str, float]]:
        """Classify an image.

        Returns ``(predicted_state, confidence, all_scores)`` where
        *all_scores* maps every known state to a probability in [0, 1].
        """
        if not self.trained:
            raise RuntimeError("Classifier has not been trained")

        features = extract_features(image)

        # Cosine similarity to each centroid
        similarities: dict[str, float] = {}
        feat_norm = np.linalg.norm(features) + 1e-8
        for state, centroid in self.centroids.items():
            cos_sim = float(
                np.dot(features, centroid)
                / (feat_norm * (np.linalg.norm(centroid) + 1e-8))
            )
            similarities[state] = cos_sim

        # Softmax over similarities to get probabilities
        max_sim = max(similarities.values())
        exp_sims = {
            s: np.exp((v - max_sim) * SOFTMAX_TEMPERATURE)
            for s, v in similarities.items()
        }
        total = sum(exp_sims.values())
        scores = {s: float(v / total) for s, v in exp_sims.items()}

        best_state = max(scores, key=lambda k: scores[k])
        return best_state, scores[best_state], scores

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Serialise the trained model to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "centroids": {
                state: centroid.tolist()
                for state, centroid in self.centroids.items()
            },
            "trained": self.trained,
        }
        path.write_text(json.dumps(data))
        _LOGGER.info("Model saved to %s", path)

    def load(self, path: str | Path) -> bool:
        """Load a previously saved model. Returns *True* on success."""
        path = Path(path)
        if not path.exists():
            return False
        try:
            data = json.loads(path.read_text())
            self.centroids = {
                state: np.array(vec, dtype=np.float32)
                for state, vec in data["centroids"].items()
            }
            self.trained = data.get("trained", True)
            _LOGGER.info(
                "Model loaded from %s (states: %s)", path, list(self.centroids.keys())
            )
            return True
        except Exception:
            _LOGGER.exception("Failed to load model from %s", path)
            return False
