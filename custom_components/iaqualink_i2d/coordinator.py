"""Data update coordinator for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import IAqualinkAuthError, IAqualinkError, IAqualinkI2DClient
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


class IAqualinkI2DCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Poll the pump, with a temporary fast interval after a control write."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: IAqualinkI2DClient,
        normal_interval: int,
        fast_interval: int,
        fast_duration: int,
        default_duration_seconds: int,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=normal_interval),
        )
        self.client = client
        self._normal_interval = normal_interval
        self._fast_interval = fast_interval
        self._fast_duration = fast_duration
        self._fast_until: float | None = None
        # Runtime preference shared between the duration select and the RPM
        # number entity; not persisted to the device.
        self.selected_duration_seconds = default_duration_seconds

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            data = await self.client.async_get_all_data()
        except IAqualinkAuthError as err:
            # Trigger Home Assistant's reauth flow instead of failing silently
            # forever when credentials/session are no longer valid.
            raise ConfigEntryAuthFailed(str(err)) from err
        except IAqualinkError as err:
            raise UpdateFailed(str(err)) from err

        # Drop back to the normal interval once the fast window elapses.
        if (
            self._fast_until is not None
            and self.hass.loop.time() > self._fast_until
        ):
            self._fast_until = None
            self.update_interval = timedelta(seconds=self._normal_interval)

        return data

    @callback
    def enable_fast_refresh(self) -> None:
        """Poll quickly for a while so RPM ramp-up is reflected promptly."""
        self._fast_until = self.hass.loop.time() + self._fast_duration
        self.update_interval = timedelta(seconds=self._fast_interval)
