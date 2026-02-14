"""Button platform for Video Status."""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import VideoStatusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create button entities for this config entry."""
    coordinator: VideoStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            CaptureSampleButton(coordinator, entry),
            TrainModelButton(coordinator, entry),
        ]
    )


class _BaseButton(ButtonEntity):
    """Shared base for Video Status buttons."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Video Status",
            model="RTSP Camera Monitor",
            sw_version="1.0.0",
        )


class CaptureSampleButton(_BaseButton):
    """Captures a frame and saves it as a training sample for the selected state."""

    _attr_translation_key = "capture_sample"
    _attr_icon = "mdi:camera-plus"

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_capture_sample"

    async def async_press(self) -> None:
        target = self._coordinator.capture_target_state
        if not target:
            _LOGGER.error("No capture target state selected")
            return
        path = await self._coordinator.async_capture_sample(target)
        _LOGGER.info("Captured sample for '%s': %s", target, path)


class TrainModelButton(_BaseButton):
    """Trains the on-device classifier from the collected training images."""

    _attr_translation_key = "train_model"
    _attr_icon = "mdi:brain"

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_train_model"

    async def async_press(self) -> None:
        counts = await self._coordinator.async_train_model()
        _LOGGER.info("Model trained: %s", counts)
