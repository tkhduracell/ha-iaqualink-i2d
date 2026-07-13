"""Button entities for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import IAqualinkError
from .const import DOMAIN
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the return-to-program button."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([ReturnToProgramButton(coordinator)])


class ReturnToProgramButton(IAqualinkI2DEntity, ButtonEntity):
    """Return the pump to its normal schedule (opmode=0)."""

    _attr_translation_key = "return_to_program"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_return_to_program"

    async def async_press(self) -> None:
        self._guard_writable("Return to schedule")
        try:
            await self._client.async_return_to_auto()
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to return to schedule: {err}") from err
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()
