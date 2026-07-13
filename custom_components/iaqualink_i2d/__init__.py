"""The iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    IAqualinkAuthError,
    IAqualinkError,
    IAqualinkI2DClient,
)
from .const import (
    CONF_DEFAULT_DURATION,
    CONF_FAST_DURATION,
    CONF_FAST_INTERVAL,
    CONF_NORMAL_INTERVAL,
    CONF_SERIAL,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_FAST_DURATION,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_NORMAL_INTERVAL,
    DOMAIN,
)
from .coordinator import IAqualinkI2DCoordinator

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up iAquaLink iQPump (i2d) from a config entry."""
    session = async_get_clientsession(hass)
    client = IAqualinkI2DClient(
        session,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
        entry.data.get(CONF_SERIAL),
    )

    try:
        await client.login()
    except IAqualinkAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except IAqualinkError as err:
        raise ConfigEntryNotReady(str(err)) from err

    options = entry.options
    coordinator = IAqualinkI2DCoordinator(
        hass,
        client,
        normal_interval=options.get(CONF_NORMAL_INTERVAL, DEFAULT_NORMAL_INTERVAL),
        fast_interval=options.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
        fast_duration=options.get(CONF_FAST_DURATION, DEFAULT_FAST_DURATION),
        default_duration_seconds=options.get(
            CONF_DEFAULT_DURATION, DEFAULT_DURATION_SECONDS
        ),
    )
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
