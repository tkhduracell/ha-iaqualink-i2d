"""Self-contained async iAquaLink client for i2d (Jandy iQPump01) pumps.

This bundles the full protocol so the integration has no external PyPI
dependency beyond aiohttp (which Home Assistant already ships).

Endpoints and commands were reverse-engineered by the community; see the
project README for references. All control traffic is a POST to
``.../v2/devices/{serial}/control.json`` with a small JSON body.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import aiohttp

from .const import OPMODE_AUTO, OPMODE_CUSTOM, RPM_STEP

_LOGGER = logging.getLogger(__name__)

API_KEY = "EOOEMOW4YR6QNB07"
LOGIN_URL = "https://prod.zodiac-io.com/users/v1/login"
DEVICES_URL = "https://r-api.iaqualink.net/devices.json"
CONTROL_URL_TMPL = "https://r-api.iaqualink.net/v2/devices/{serial}/control.json"
USER_AGENT = "iAqualink/934 CFNetwork/3826.500.111.2.2 Darwin/24.4.0"
REQUEST_TIMEOUT = 30

DEVICE_TYPE_I2D = "i2d"


class IAqualinkError(Exception):
    """Base iAquaLink API error."""


class IAqualinkAuthError(IAqualinkError):
    """Authentication or authorization failed."""


class IAqualinkConnectionError(IAqualinkError):
    """Unable to communicate with iAquaLink."""


class IAqualinkNoDeviceError(IAqualinkError):
    """No supported i2d pump was found in the account."""


class IAqualinkCommandError(IAqualinkError):
    """iAquaLink rejected or ignored a command."""


class IAqualinkI2DClient:
    """Minimal async client for a single i2d pump."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        email: str,
        password: str,
        serial: str | None = None,
    ) -> None:
        self._session = session
        self._email = email
        self._password = password
        self.serial = str(serial) if serial else None

        self.api_key = API_KEY
        self.auth_token: str | None = None
        self.session_id: str | None = None
        self.user_id: str | None = None
        self.id_token: str | None = None
        self.devices: list[dict[str, Any]] = []

        # Serialize logins (avoid two tasks racing to refresh the token) and
        # control-write sequences (avoid interleaving opmode/rpm/timer writes).
        self._login_lock = asyncio.Lock()
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------ auth

    async def login(self) -> None:
        """Log in and (re)discover the configured pump.

        Guarded by a lock so concurrent callers (e.g. a poll and a user action
        both hitting an expired token) don't race to overwrite the session.
        """
        token_before = self.id_token
        async with self._login_lock:
            # Another task may have refreshed the session while we waited.
            if self.id_token is not None and self.id_token != token_before:
                return
            await self._login_locked()

    async def _login_locked(self) -> None:
        payload = {
            "email": self._email,
            "password": self._password,
            "apikey": self.api_key,
        }
        data = await self._request(
            "post",
            LOGIN_URL,
            json=payload,
            headers={"Content-Type": "application/json"},
            context="login",
        )
        try:
            self.auth_token = data["authentication_token"]
            self.session_id = data["session_id"]
            self.user_id = str(data["id"])
            self.id_token = data["userPoolOAuth"]["IdToken"]
        except (KeyError, TypeError) as err:
            raise IAqualinkAuthError("Login response missing auth fields") from err

        await self._discover_devices()

    async def _discover_devices(self) -> None:
        params = {
            "authentication_token": self.auth_token,
            "user_id": self.user_id,
            "api_key": self.api_key,
        }
        data = await self._request(
            "get", DEVICES_URL, params=params, context="devices"
        )
        if isinstance(data, dict):
            data = data.get("devices", [])
        self.devices = [
            d
            for d in data
            if isinstance(d, dict)
            and d.get("device_type") == DEVICE_TYPE_I2D
            and d.get("serial_number")
        ]
        if not self.devices:
            raise IAqualinkNoDeviceError(
                "No iQPump01 controller (device_type=i2d) in this account"
            )

        if self.serial:
            match = next(
                (d for d in self.devices if d.get("serial_number") == self.serial),
                None,
            )
            if match is None:
                raise IAqualinkNoDeviceError(
                    f"Configured pump {self.serial[-4:]!r} not found in account"
                )
        else:
            self.serial = self.devices[0]["serial_number"]

    # --------------------------------------------------------------- reading

    async def async_get_all_data(self) -> dict[str, Any]:
        """Return the flattened ``alldata`` snapshot for the pump."""
        payload = {"user_id": str(self.user_id), "command": "/alldata/read"}
        data = await self._post_control(payload, context="alldata")
        if not isinstance(data, dict):
            raise IAqualinkConnectionError("Unexpected /alldata/read response shape")
        alldata = data.get("alldata")
        return alldata if isinstance(alldata, dict) else {}

    # --------------------------------------------------------------- control

    async def async_set_opmode(self, value: int) -> dict[str, Any]:
        async with self._write_lock:
            return await self._send_command("/opmode/write", value)

    async def async_set_custom_speed(
        self,
        rpm: int,
        duration_seconds: int,
        rpm_min: int | None = None,
        rpm_max: int | None = None,
    ) -> None:
        """Run the reliable custom-speed sequence: opmode=1 -> rpm -> timer.

        RPM writes are ignored while the pump is in scheduled mode, so the
        opmode write must come first. RPM is clamped to the device limits
        (when provided) and rounded to the nearest step. The whole sequence is
        serialized; if the RPM/timer write fails after the mode switch, the
        pump is best-effort returned to Auto so it isn't left half-configured.
        """
        if rpm_min is not None:
            rpm = max(rpm, rpm_min)
        if rpm_max is not None:
            rpm = min(rpm, rpm_max)
        rpm = int(round(rpm / RPM_STEP) * RPM_STEP)

        async with self._write_lock:
            await self._send_command("/opmode/write", OPMODE_CUSTOM)
            try:
                await self._send_command("/customspeedrpm/write", rpm)
                await self._send_command("/customspeedtimer/write", int(duration_seconds))
            except IAqualinkError:
                # Roll back to the schedule rather than leaving the pump in
                # custom mode at a stale/unintended speed.
                try:
                    await self._send_command("/opmode/write", OPMODE_AUTO)
                except IAqualinkError:
                    _LOGGER.warning("[iaqualink_i2d] rollback to auto also failed")
                raise

    async def async_return_to_auto(self) -> None:
        """Return the pump to its normal schedule (opmode=0)."""
        async with self._write_lock:
            await self._send_command("/opmode/write", OPMODE_AUTO)

    async def _send_command(self, command: str, value: int) -> dict[str, Any]:
        payload = {
            "user_id": str(self.user_id),
            "command": command,
            "params": f"value={value}",
        }
        _LOGGER.debug("[iaqualink_i2d] command %s value=%s", command, value)
        data = await self._post_control(payload, context=command)

        # Every write echoes {"<key>": {"operation": "write", "value": "<n>"}}
        # (verified live for opmode/customspeedrpm/customspeedtimer). A missing
        # key or mismatched value means the controller rejected/ignored the
        # command (e.g. service mode), so treat that as a failure, not success.
        key = command.strip("/").split("/")[0]
        section = data.get(key) if isinstance(data, dict) else None
        returned = section.get("value") if isinstance(section, dict) else None
        if returned is None or str(returned) != str(value):
            raise IAqualinkCommandError(
                f"iAquaLink did not confirm {key}={value} (response={data!r})"
            )
        return data

    # ---------------------------------------------------------------- plumbing

    def _control_headers(self) -> dict[str, str]:
        return {
            "accept": "*/*",
            "content-type": "application/json",
            "cookie": (
                f"session_id={self.session_id}; "
                f"authentication_token={self.auth_token}"
            ),
            "authorization": self.id_token or "",
            "api_key": self.api_key,
            "user-agent": USER_AGENT,
        }

    async def _post_control(
        self, payload: dict[str, Any], *, context: str
    ) -> dict[str, Any]:
        if not self.id_token or not self.serial:
            await self.login()

        url = CONTROL_URL_TMPL.format(serial=self.serial)
        for attempt in range(2):
            try:
                async with self._session.post(
                    url,
                    json=payload,
                    headers=self._control_headers(),
                    timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                ) as resp:
                    if resp.status == 401 and attempt == 0:
                        _LOGGER.debug(
                            "[iaqualink_i2d] token expired during %s, re-login",
                            context,
                        )
                        await self.login()
                        continue
                    if resp.status in (401, 403):
                        raise IAqualinkAuthError(
                            f"HTTP {resp.status} during {context}"
                        )
                    if resp.status >= 400:
                        raise IAqualinkConnectionError(
                            f"HTTP {resp.status} during {context}"
                        )
                    # The control endpoint returns JSON with a non-JSON
                    # mimetype, so parsing must not enforce the content type.
                    # ValueError covers a genuinely non-JSON body (proxy/CDN
                    # error page, truncated response).
                    return await resp.json(content_type=None)
            except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
                raise IAqualinkConnectionError(
                    f"Request failed during {context}: {err}"
                ) from err
        raise IAqualinkConnectionError(f"Request failed during {context}")

    async def _request(
        self, method: str, url: str, *, context: str, **kwargs: Any
    ) -> Any:
        try:
            async with self._session.request(
                method,
                url,
                timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
                **kwargs,
            ) as resp:
                if resp.status in (401, 403):
                    raise IAqualinkAuthError(f"HTTP {resp.status} during {context}")
                if resp.status >= 400:
                    raise IAqualinkConnectionError(
                        f"HTTP {resp.status} during {context}"
                    )
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise IAqualinkConnectionError(
                f"Request failed during {context}: {err}"
            ) from err
