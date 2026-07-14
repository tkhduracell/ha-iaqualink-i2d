"""Fan entity modelling the variable-speed pump.

HA's idiomatic type for a variable-speed device: speed is a percentage and
"schedule" is a preset mode (per the fan entity developer docs). Setting a
percentage puts the pump in custom mode; the "auto" preset hands control back
to the pump's own program.
"""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.fan import FanEntity, FanEntityFeature
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
    OPMODE_AUTO,
    OPMODE_OFF,
    OPMODE_LABELS,
    RPM_STEP,
    SERVICE_RETURN_TO_SCHEDULE,
    SERVICE_SET_CUSTOM_SPEED,
)
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity

PRESET_SCHEDULE = "auto"


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the pump fan entity and register its services."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([PoolPumpFan(coordinator)])

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
        SERVICE_SET_CUSTOM_SPEED,
        {
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
        SERVICE_RETURN_TO_SCHEDULE, {}, "async_service_return_to_schedule"
    )


class PoolPumpFan(IAqualinkI2DEntity, FanEntity):
    """The pump as a fan: percentage speed + 'auto' (schedule) preset."""

    _attr_translation_key = "pool_pump"
    _attr_icon = "mdi:pump"
    _attr_preset_modes = [PRESET_SCHEDULE]
    _attr_supported_features = (
        FanEntityFeature.SET_SPEED
        | FanEntityFeature.PRESET_MODE
        | FanEntityFeature.TURN_ON
        | FanEntityFeature.TURN_OFF
    )
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._client.serial}_pump"

    # ---------------------------------------------------------------- helpers

    def _rpm_bounds(self) -> tuple[int, int]:
        lo = _to_int(self._data.get("globalrpmmin")) or DEFAULT_RPM_MIN
        hi = _to_int(self._data.get("globalrpmmax")) or DEFAULT_RPM_MAX
        return lo, hi

    def _pct_to_rpm(self, percentage: float) -> int:
        lo, hi = self._rpm_bounds()
        rpm = lo + (percentage / 100) * (hi - lo)
        rpm = round(rpm / RPM_STEP) * RPM_STEP
        return max(lo, min(hi, int(rpm)))

    # ----------------------------------------------------------------- state

    @property
    def is_on(self) -> bool | None:
        runstate = self._data.get("runstate")
        if runstate is None:
            return None
        return runstate == "on"

    @property
    def percentage(self) -> int | None:
        if not self.is_on:
            return 0
        lo, hi = self._rpm_bounds()
        rpm = _to_int(self._data.get("rpmtarget"))
        if rpm is None or hi <= lo:
            return None
        pct = round((rpm - lo) / (hi - lo) * 100)
        return max(1, min(100, pct))

    @property
    def percentage_step(self) -> float:
        lo, hi = self._rpm_bounds()
        steps = max(1, (hi - lo) / RPM_STEP)
        return 100 / steps

    @property
    def preset_mode(self) -> str | None:
        if str(self._data.get("opmode")) == str(OPMODE_AUTO):
            return PRESET_SCHEDULE
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        motordata = self._data.get("motordata") or {}
        return {
            "target_rpm": _to_int(self._data.get("rpmtarget")),
            "custom_speed_rpm": _to_int(self._data.get("customspeedrpm")),
            "actual_rpm": _to_int(motordata.get("speed")),
            "operating_mode": OPMODE_LABELS.get(str(self._data.get("opmode"))),
        }

    # --------------------------------------------------------------- control

    async def async_set_percentage(self, percentage: int) -> None:
        self._guard_writable("Set pump speed")
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._apply_custom_rpm(self._pct_to_rpm(percentage))

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        self._guard_writable("Set pump mode")
        if preset_mode != PRESET_SCHEDULE:
            raise HomeAssistantError(f"Unknown preset mode: {preset_mode}")
        await self._return_to_schedule()

    async def async_turn_on(
        self,
        percentage: int | None = None,
        preset_mode: str | None = None,
        **kwargs: Any,
    ) -> None:
        self._guard_writable("Turn on pump")
        if preset_mode is not None:
            await self.async_set_preset_mode(preset_mode)
            return
        if percentage is not None and percentage > 0:
            await self._apply_custom_rpm(self._pct_to_rpm(percentage))
            return
        # Bare "on": run at the pump's stored custom RPM.
        rpm = _to_int(self._data.get("customspeedrpm")) or _to_int(
            self._data.get("rpmtarget")
        )
        lo, _ = self._rpm_bounds()
        await self._apply_custom_rpm(rpm or lo)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._guard_writable("Turn off pump")
        try:
            await self._client.async_set_opmode(OPMODE_OFF)
        except IAqualinkError as err:
            raise HomeAssistantError(f"Unable to turn off pump: {err}") from err
        await self._refresh_soon()

    # ---------------------------------------------------------- entity services

    async def async_service_set_custom_speed(
        self, rpm: int, duration_seconds: int | None = None
    ) -> None:
        self._guard_writable("Set custom speed")
        duration = (
            duration_seconds
            if duration_seconds is not None
            else self.coordinator.selected_duration_seconds
        )
        await self._apply_custom_rpm(rpm, duration)

    async def async_service_return_to_schedule(self) -> None:
        await self._return_to_schedule()

    # ---------------------------------------------------------------- internals

    async def _apply_custom_rpm(
        self, rpm: int, duration_seconds: int | None = None
    ) -> None:
        lo, hi = self._rpm_bounds()
        duration = (
            duration_seconds
            if duration_seconds is not None
            else self.coordinator.selected_duration_seconds
        )
        try:
            await self._client.async_set_custom_speed(rpm, duration, lo, hi)
        except IAqualinkError as err:
            await self._refresh_soon()
            raise HomeAssistantError(f"Unable to set pump speed: {err}") from err
        await self._refresh_soon()

    async def _return_to_schedule(self) -> None:
        self._guard_writable("Return to schedule")
        try:
            await self._client.async_return_to_auto()
        except IAqualinkError as err:
            raise HomeAssistantError(
                f"Unable to return to schedule: {err}"
            ) from err
        await self._refresh_soon()

    async def _refresh_soon(self) -> None:
        self.coordinator.enable_fast_refresh()
        await self.coordinator.async_request_refresh()
