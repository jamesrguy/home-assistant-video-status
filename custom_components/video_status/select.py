"""Select platform for Video Status."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
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
    """Create select entities for this config entry."""
    coordinator: VideoStatusCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CaptureStateSelect(coordinator, entry)])


class CaptureStateSelect(SelectEntity):
    """Dropdown to choose which state the next captured sample is labelled as."""

    _attr_has_entity_name = True
    _attr_translation_key = "capture_state"
    _attr_icon = "mdi:tag-outline"

    def __init__(
        self, coordinator: VideoStatusCoordinator, entry: ConfigEntry
    ) -> None:
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_capture_state"
        self._attr_options = list(coordinator.states)
        self._attr_current_option = coordinator.capture_target_state

    @property
    def device_info(self) -> DeviceInfo:
        return DeviceInfo(
            identifiers={(DOMAIN, self._entry.entry_id)},
            name=self._entry.title,
            manufacturer="Video Status",
            model="RTSP Camera Monitor",
            sw_version="1.0.0",
        )

    async def async_select_option(self, option: str) -> None:
        """Update the selected capture target state."""
        self._attr_current_option = option
        self._coordinator.capture_target_state = option
        self.async_write_ha_state()
