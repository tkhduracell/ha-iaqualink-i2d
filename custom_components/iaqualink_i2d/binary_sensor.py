"""Binary sensor entities for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the priming binary sensor."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PumpPrimingBinarySensor(coordinator)])


class PumpPrimingBinarySensor(IAqualinkI2DEntity, BinarySensorEntity):
    """True while the pump is priming (primingtimer >= 0)."""

    _attr_translation_key = "priming"
    _attr_device_class = BinarySensorDeviceClass.RUNNING
    _attr_icon = "mdi:water-pump"

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_priming"

    @property
    def is_on(self) -> bool | None:
        value = self._data.get("primingtimer")
        try:
            return int(value) >= 0
        except (TypeError, ValueError):
            return None
