"""Diagnostics support for Midea AC LAN."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import (
    CONF_DEVICE_ID,
    CONF_TOKEN,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

from .connection_manager import CONNECTION_MANAGERS
from .const import CONF_KEY, DOMAIN

TO_REDACT = {CONF_TOKEN, CONF_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: ConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry.

    Returns
    -------
    Dictionary of config

    """
    device_id = entry.data.get(CONF_DEVICE_ID)
    manager = hass.data.get(DOMAIN, {}).get(CONNECTION_MANAGERS, {}).get(device_id)
    runtime = manager.diagnostic_data if manager is not None else None
    return {
        "entry": async_redact_data(entry.as_dict(), TO_REDACT),
        "runtime_connection": runtime,
    }
