"""Camera platform for Video Status."""
from __future__ import annotations

from homeassistant.components.camera import Camera
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VideoStatusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create camera entity for this config entry."""
    coordinator: VideoStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([VideoStatusCamera(coordinator, entry)])


class VideoStatusCamera(Camera):
    """Shows the last captured frame with the ROI rectangle overlaid."""

    _attr_has_entity_name = True
    _attr_translation_key = "last_frame"
    _attr_icon = "mdi:cctv"

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__()
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_camera"

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Video Status",
            model="RTSP Camera Monitor",
            sw_version="1.0.0",
        )

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return the most recent frame with the ROI box drawn on it."""
        return await self.hass.async_add_executor_job(
            self._coordinator.get_annotated_frame_bytes
        )

    @property
    def is_on(self) -> bool:
        return self._coordinator.last_frame is not None
