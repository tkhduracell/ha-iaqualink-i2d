"""Select entities for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, DURATION_OPTIONS
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity

_DURATION_BY_SECONDS = {seconds: label for label, seconds in DURATION_OPTIONS.items()}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the custom-speed duration select."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([CustomSpeedDurationSelect(coordinator)])


class CustomSpeedDurationSelect(IAqualinkI2DEntity, SelectEntity):
    """Preferred run duration applied when setting/starting a custom speed.

    This is a local preference (not written to the device on its own); the RPM
    number, the Start custom speed button, and the set_custom_speed service use
    it as the timer value.
    """

    _attr_translation_key = "custom_speed_duration"
    _attr_icon = "mdi:timer-outline"
    _attr_options = list(DURATION_OPTIONS)

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_custom_duration"

    @property
    def current_option(self) -> str | None:
        secs = self.coordinator.selected_duration_seconds
        if secs in _DURATION_BY_SECONDS:
            return _DURATION_BY_SECONDS[secs]
        # A configured default that isn't exactly a preset still needs to show
        # something; snap to the nearest preset for display.
        nearest = min(DURATION_OPTIONS.values(), key=lambda v: abs(v - secs))
        return _DURATION_BY_SECONDS[nearest]

    async def async_select_option(self, option: str) -> None:
        self.coordinator.selected_duration_seconds = DURATION_OPTIONS[option]
        self.async_write_ha_state()
