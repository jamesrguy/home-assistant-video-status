"""Sensor platform for Video Status."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import VideoStatusCoordinator


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create sensor entities for this config entry."""
    coordinator: VideoStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            VideoStatusStateSensor(coordinator, entry),
            VideoStatusConfidenceSensor(coordinator, entry),
        ]
    )


class _BaseVideoStatusEntity(CoordinatorEntity[VideoStatusCoordinator], SensorEntity):
    """Shared base for all Video Status sensors."""

    _attr_has_entity_name = True

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
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


class VideoStatusStateSensor(_BaseVideoStatusEntity):
    """Reports the detected visual state (e.g. 'open', 'closed')."""

    _attr_translation_key = "status"
    _attr_icon = "mdi:eye"

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_status"

    @property
    def native_value(self) -> str | None:
        if self.coordinator.data is None:
            return None
        return self.coordinator.data.get("state")

    @property
    def extra_state_attributes(self) -> dict:
        if self.coordinator.data is None:
            return {}
        return {
            "scores": self.coordinator.data.get("scores", {}),
            "model_ready": self.coordinator.data.get("model_ready", False),
            "available_states": self.coordinator.data.get("states", []),
            "last_analysis": self.coordinator.data.get("last_updated"),
            "inference_mode": self.coordinator.inference_mode,
            "training_path": str(self.coordinator.training_path),
        }


class VideoStatusConfidenceSensor(_BaseVideoStatusEntity):
    """Reports the classification confidence as a percentage."""

    _attr_translation_key = "confidence"
    _attr_icon = "mdi:gauge"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator, entry)
        self._attr_unique_id = f"{entry.entry_id}_confidence"

    @property
    def native_value(self) -> float | None:
        if self.coordinator.data is None:
            return None
        confidence = self.coordinator.data.get("confidence", 0)
        return round(confidence * 100, 1)
