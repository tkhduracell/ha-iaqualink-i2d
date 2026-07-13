"""Sensor entities for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    REVOLUTIONS_PER_MINUTE,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, OPMODE_LABELS
from .coordinator import IAqualinkI2DCoordinator
from .entity import IAqualinkI2DEntity


def _to_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _motordata(data: dict[str, Any], key: str) -> int | None:
    return _to_int((data.get("motordata") or {}).get(key))


def _opmode_label(data: dict[str, Any]) -> str | None:
    return OPMODE_LABELS.get(str(data.get("opmode")))


@dataclass(frozen=True, kw_only=True)
class I2DSensorDescription(SensorEntityDescription):
    """Sensor description with a value extractor over the alldata dict."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[I2DSensorDescription, ...] = (
    I2DSensorDescription(
        key="motor_speed",
        translation_key="motor_speed",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer",
        value_fn=lambda d: _motordata(d, "speed"),
    ),
    I2DSensorDescription(
        key="motor_power",
        translation_key="motor_power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _motordata(d, "power"),
    ),
    I2DSensorDescription(
        key="motor_temperature",
        translation_key="motor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        # The controller already reports Celsius (confirmed against a live pump;
        # the API also uses a *setpointc* field name for freeze protection).
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: _motordata(d, "temperature"),
    ),
    I2DSensorDescription(
        key="rpm_target",
        translation_key="rpm_target",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:target",
        value_fn=lambda d: _to_int(d.get("rpmtarget")),
    ),
    I2DSensorDescription(
        key="custom_speed_rpm",
        translation_key="custom_speed_rpm",
        native_unit_of_measurement=REVOLUTIONS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:speedometer-medium",
        value_fn=lambda d: _to_int(d.get("customspeedrpm")),
    ),
    I2DSensorDescription(
        key="custom_speed_timer",
        translation_key="custom_speed_timer",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        icon="mdi:timer-sand",
        value_fn=lambda d: _to_int(d.get("customspeedtimer")),
    ),
    I2DSensorDescription(
        key="operating_mode",
        translation_key="operating_mode",
        icon="mdi:pump",
        value_fn=_opmode_label,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensors."""
    coordinator: IAqualinkI2DCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(I2DSensor(coordinator, desc) for desc in SENSORS)


class I2DSensor(IAqualinkI2DEntity, SensorEntity):
    """A single value read from the pump snapshot."""

    entity_description: I2DSensorDescription

    def __init__(
        self,
        coordinator: IAqualinkI2DCoordinator,
        description: I2DSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._client.serial}_{description.key}"

    @property
    def native_value(self) -> Any:
        return self.entity_description.value_fn(self._data)
