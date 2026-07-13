"""RPM number entity for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import IAqualinkError
from .const import (
    ATTR_DURATION_SECONDS,
    ATTR_RPM,
    DEFAULT_RPM_MAX,
    DEFAULT_RPM_MIN,
    DOMAIN,
    RPM_STEP,
    SERVICE_RETURN_TO_SCHEDULE,
    SERVICE_SET_CUSTOM_SPEED,
)
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the RPM number entity and register entity services."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PumpRpmNumber(coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_CUSTOM_SPEED,
        {
            # Hardware envelope; the actual request is further clamped to the
            # device-reported globalrpmmin/globalrpmmax before sending.
            vol.Required(ATTR_RPM): vol.All(
                vol.Coerce(int), vol.Range(min=600, max=3450)
            ),
            vol.Optional(ATTR_DURATION_SECONDS): vol.All(
                vol.Coerce(int), vol.Range(min=60, max=86340)
            ),
        },
        "async_service_set_custom_speed",
    )
    platform.async_register_entity_service(
        SERVICE_RETURN_TO_SCHEDULE,
        {},
        "async_service_return_to_schedule",
    )


class PumpRpmNumber(IAqualinkI2DEntity, NumberEntity):
    """Target RPM for the pump (raw RPM), applied as a custom speed."""

    _attr_translation_key = "pump_rpm"
    _attr_icon = "mdi:speedometer"
    _attr_native_unit_of_measurement = "RPM"
    _attr_mode = NumberMode.BOX
    _attr_native_step = RPM_STEP

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_rpm"

    @property
    def native_min_value(self) -> float:
        return float(self._data.get("globalrpmmin", DEFAULT_RPM_MIN))

    @property
    def native_max_value(self) -> float:
        return float(self._data.get("globalrpmmax", DEFAULT_RPM_MAX))

    @property
    def native_value(self) -> float | None:
        value = self._data.get("rpmtarget")
        try:
            return float(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    async def async_set_native_value(self, value: float) -> None:
        await self._apply_custom_speed(
            int(value), self.coordinator.selected_duration_seconds
        )

    async def async_service_set_custom_speed(
        self, rpm: int, duration_seconds: int | None = None
    ) -> None:
        duration = (
            duration_seconds
            if duration_seconds is not None
            else self.coordinator.selected_duration_seconds
        )
        await self._apply_custom_speed(rpm, duration)

    async def async_service_return_to_schedule(self) -> None:
        self._guard_writable("Return to schedule")
        try:
            await self._client.async_return_to_auto()
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to return to schedule: {err}") from err
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()

    async def _apply_custom_speed(self, rpm: int, duration_seconds: int) -> None:
        self._guard_writable("Set pump speed")
        rpm_min = int(self._data.get("globalrpmmin", DEFAULT_RPM_MIN))
        rpm_max = int(self._data.get("globalrpmmax", DEFAULT_RPM_MAX))
        _LOGGER.debug(
            "[iaqualink_i2d] set custom speed %s RPM (clamp %s-%s) for %ss",
            rpm,
            rpm_min,
            rpm_max,
            duration_seconds,
        )
        try:
            await self._client.async_set_custom_speed(
                rpm, duration_seconds, rpm_min, rpm_max
            )
        except IAqualinkError as err:
            # Refresh so entities reflect the pump's real (possibly rolled-back)
            # state even when the command failed.
            self.coordinator.enable_fast_refresh()
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"Unable to set pump speed: {err}") from err
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()
