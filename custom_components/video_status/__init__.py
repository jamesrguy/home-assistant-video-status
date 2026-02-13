"""The Video Status integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, PLATFORMS
from .coordinator import VideoStatusCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Video Status from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    coordinator = VideoStatusCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = coordinator
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    _register_services(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return ok


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


def _register_services(hass: HomeAssistant) -> None:
    """Register integration-level services (idempotent)."""
    if hass.services.has_service(DOMAIN, "train_model"):
        return

    async def _handle_train_model(call: ServiceCall) -> None:
        entry_id: str = call.data["entry_id"]
        coordinator = _get_coordinator(hass, entry_id)
        counts = await coordinator.async_train_model()
        _LOGGER.info("Model trained: %s", counts)

    async def _handle_capture_sample(call: ServiceCall) -> None:
        entry_id: str = call.data["entry_id"]
        state_name: str = call.data["state"]
        coordinator = _get_coordinator(hass, entry_id)
        path = await coordinator.async_capture_sample(state_name)
        _LOGGER.info("Sample saved: %s", path)

    hass.services.async_register(
        DOMAIN,
        "train_model",
        _handle_train_model,
        schema=vol.Schema({vol.Required("entry_id"): cv.string}),
    )

    hass.services.async_register(
        DOMAIN,
        "capture_sample",
        _handle_capture_sample,
        schema=vol.Schema(
            {
                vol.Required("entry_id"): cv.string,
                vol.Required("state"): cv.string,
            }
        ),
    )


def _get_coordinator(hass: HomeAssistant, entry_id: str) -> VideoStatusCoordinator:
    """Look up a coordinator by config-entry ID, or raise."""
    coordinator = hass.data.get(DOMAIN, {}).get(entry_id)
    if coordinator is None:
        raise ValueError(f"No Video Status entry with id '{entry_id}'")
    return coordinator
