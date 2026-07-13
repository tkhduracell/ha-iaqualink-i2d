"""Button entities for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import IAqualinkError
from .const import DEFAULT_RPM_MAX, DEFAULT_RPM_MIN, DOMAIN, OPMODE_CUSTOM
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the custom-speed and return-to-program buttons."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            StartCustomSpeedButton(coordinator),
            ReturnToProgramButton(coordinator),
        ]
    )


class StartCustomSpeedButton(IAqualinkI2DEntity, ButtonEntity):
    """Run the pump at its current custom RPM for the selected duration.

    Uses the pump's stored custom RPM (shown in the Custom speed RPM sensor) so
    it deterministically resumes/starts the configured speed. To change the
    speed, use the Pump RPM number (which applies immediately).
    """

    _attr_translation_key = "start_custom_speed"
    _attr_icon = "mdi:play-speed"

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_start_custom_speed"

    async def async_press(self) -> None:
        self._guard_writable("Start custom speed")
        rpm = int(
            self._data.get("customspeedrpm")
            or self._data.get("rpmtarget")
            or DEFAULT_RPM_MIN
        )
        rpm_min = int(self._data.get("globalrpmmin", DEFAULT_RPM_MIN))
        rpm_max = int(self._data.get("globalrpmmax", DEFAULT_RPM_MAX))
        try:
            await self._client.async_set_custom_speed(
                rpm, self.coordinator.selected_duration_seconds, rpm_min, rpm_max
            )
        except IAqualinkError as err:
            self.coordinator.enable_fast_refresh()
            await self.coordinator.async_request_refresh()
            raise HomeAssistantError(f"Unable to start custom speed: {err}") from err
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()


class ReturnToProgramButton(IAqualinkI2DEntity, ButtonEntity):
    """Return the pump to its normal schedule (opmode=0).

    Only available while the pump is in custom mode — there's nothing to return
    from otherwise.
    """

    _attr_translation_key = "return_to_program"
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_return_to_program"

    @property
    def available(self) -> bool:
        return (
            super().available
            and str(self._data.get("opmode")) == str(OPMODE_CUSTOM)
        )

    async def async_press(self) -> None:
        self._guard_writable("Return to schedule")
        try:
            await self._client.async_return_to_auto()
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to return to schedule: {err}") from err
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()
