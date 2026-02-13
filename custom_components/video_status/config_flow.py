"""Config flow for Video Status."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

from .const import (
    CONF_API_KEY,
    CONF_API_MODEL,
    CONF_INFERENCE_MODE,
    CONF_PASSWORD,
    CONF_RTSP_URL,
    CONF_SCAN_INTERVAL,
    CONF_STATES,
    CONF_USERNAME,
    DEFAULT_API_MODEL,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_STATES,
    DOMAIN,
    INFERENCE_API,
    INFERENCE_LOCAL,
)
from .frame_capture import validate_rtsp_url

_LOGGER = logging.getLogger(__name__)


class VideoStatusConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Video Status."""

    VERSION = 1

    def __init__(self) -> None:
        self._user_input: dict[str, Any] = {}

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1 — basic camera and inference configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not validate_rtsp_url(user_input[CONF_RTSP_URL]):
                errors[CONF_RTSP_URL] = "invalid_rtsp_url"

            states = [
                s.strip()
                for s in user_input.get(CONF_STATES, "").split(",")
                if s.strip()
            ]
            if len(states) < 2:
                errors[CONF_STATES] = "need_two_states"

            if not errors:
                self._user_input = user_input
                if user_input[CONF_INFERENCE_MODE] == INFERENCE_API:
                    return await self.async_step_api_config()
                return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME): str,
                vol.Required(CONF_RTSP_URL): str,
                vol.Optional(CONF_USERNAME): str,
                vol.Optional(CONF_PASSWORD): str,
                vol.Required(
                    CONF_INFERENCE_MODE, default=INFERENCE_LOCAL
                ): vol.In(
                    {
                        INFERENCE_LOCAL: "On-Device (Local)",
                        INFERENCE_API: "API (OpenRouter)",
                    }
                ),
                vol.Required(CONF_STATES, default=DEFAULT_STATES): str,
                vol.Required(
                    CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL
                ): vol.All(int, vol.Range(min=5, max=3600)),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_api_config(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2 — OpenRouter API credentials (only when mode=api)."""
        errors: dict[str, str] = {}

        if user_input is not None:
            if not user_input.get(CONF_API_KEY):
                errors[CONF_API_KEY] = "missing_api_key"

            if not errors:
                self._user_input.update(user_input)
                return self._create_entry()

        schema = vol.Schema(
            {
                vol.Required(CONF_API_KEY): str,
                vol.Required(
                    CONF_API_MODEL, default=DEFAULT_API_MODEL
                ): str,
            }
        )

        return self.async_show_form(
            step_id="api_config",
            data_schema=schema,
            errors=errors,
        )

    def _create_entry(self) -> config_entries.ConfigFlowResult:
        return self.async_create_entry(
            title=self._user_input[CONF_NAME],
            data=self._user_input,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> VideoStatusOptionsFlow:
        return VideoStatusOptionsFlow(config_entry)


class VideoStatusOptionsFlow(config_entries.OptionsFlow):
    """Allow the user to adjust scan_interval after setup."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SCAN_INTERVAL,
                    default=self.config_entry.data.get(
                        CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL
                    ),
                ): vol.All(int, vol.Range(min=5, max=3600)),
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
