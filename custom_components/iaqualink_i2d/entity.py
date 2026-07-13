"""Base entity for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from typing import Any

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, OPMODE_SERVICE
from .coordinator import IAqualinkI2DCoordinator


class IAqualinkI2DEntity(CoordinatorEntity[IAqualinkI2DCoordinator]):
    """Common base wiring device info and the service-mode guard."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: IAqualinkI2DCoordinator) -> None:
        super().__init__(coordinator)
        self._client = coordinator.client
        serial = self._client.serial or "unknown"

        data = coordinator.data or {}
        motordata = data.get("motordata") or {}
        productid = motordata.get("productid")
        firmware = data.get("fwversion")

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, serial)},
            manufacturer="Jandy",
            model="iQPump01",
            # Raw product code (e.g. "17") kept as a secondary identifier
            # rather than shown as the model name.
            model_id=str(productid) if productid else None,
            sw_version=str(firmware) if firmware else None,
            name="Pool Pump",
            serial_number=serial,
        )

    @property
    def _data(self) -> dict[str, Any]:
        return self.coordinator.data or {}

    def _guard_writable(self, action: str) -> None:
        """Block writes when the pump is offline or in service mode.

        Without live data the pump's mode is unknown, so a write could act on a
        wrong assumption; opmode=7 is service mode where remote control is not
        authorized.
        """
        if not self._data or "opmode" not in self._data:
            raise HomeAssistantError(
                f"{action} unavailable: pump data has not loaded yet."
            )
        if str(self._data.get("opmode")) == str(OPMODE_SERVICE):
            raise HomeAssistantError(
                f"{action} unavailable: pump is in service mode and remote "
                "control is not authorized."
            )
