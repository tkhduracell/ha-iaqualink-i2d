"""Config and options flow for the iAquaLink iQPump (i2d) integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    IAqualinkAuthError,
    IAqualinkError,
    IAqualinkI2DClient,
    IAqualinkNoDeviceError,
)
from .const import (
    CONF_DEFAULT_DURATION,
    CONF_FAST_DURATION,
    CONF_FAST_INTERVAL,
    CONF_NORMAL_INTERVAL,
    CONF_SERIAL,
    DEFAULT_DURATION_SECONDS,
    DEFAULT_FAST_DURATION,
    DEFAULT_FAST_INTERVAL,
    DEFAULT_NORMAL_INTERVAL,
    DOMAIN,
    DURATION_OPTIONS,
)

USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
    }
)


class IAqualinkI2DConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the iAquaLink iQPump (i2d) config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._username: str | None = None
        self._password: str | None = None
        self._devices: list[dict[str, Any]] = []
        self._reauth_entry: ConfigEntry | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = IAqualinkI2DClient(
                session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD]
            )
            try:
                await client.login()
            except IAqualinkAuthError:
                errors["base"] = "invalid_auth"
            except IAqualinkNoDeviceError:
                errors["base"] = "no_devices"
            except IAqualinkError:
                errors["base"] = "cannot_connect"
            else:
                self._username = user_input[CONF_USERNAME]
                self._password = user_input[CONF_PASSWORD]
                self._devices = client.devices
                if len(client.devices) == 1:
                    return await self._create_entry(
                        client.devices[0]["serial_number"]
                    )
                return await self.async_step_select()

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_select(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return await self._create_entry(user_input[CONF_SERIAL])

        options = {
            d["serial_number"]: f"{d.get('name', d['serial_number'])} "
            f"({d['serial_number'][-4:]})"
            for d in self._devices
        }
        return self.async_show_form(
            step_id="select",
            data_schema=vol.Schema({vol.Required(CONF_SERIAL): vol.In(options)}),
        )

    async def _create_entry(self, serial: str) -> ConfigFlowResult:
        await self.async_set_unique_id(serial)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title=f"iQPump {serial[-4:]}",
            data={
                CONF_USERNAME: self._username,
                CONF_PASSWORD: self._password,
                CONF_SERIAL: serial,
            },
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        self._username = entry_data.get(CONF_USERNAME)
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._reauth_entry is not None
        errors: dict[str, str] = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            client = IAqualinkI2DClient(
                session,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
                self._reauth_entry.data.get(CONF_SERIAL),
            )
            try:
                await client.login()
            except IAqualinkAuthError:
                errors["base"] = "invalid_auth"
            except IAqualinkError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data={
                        **self._reauth_entry.data,
                        CONF_USERNAME: user_input[CONF_USERNAME],
                        CONF_PASSWORD: user_input[CONF_PASSWORD],
                    },
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_USERNAME, default=self._username): str,
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return IAqualinkI2DOptionsFlow()


class IAqualinkI2DOptionsFlow(OptionsFlow):
    """Handle polling / duration options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        opts = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_DEFAULT_DURATION,
                    default=opts.get(
                        CONF_DEFAULT_DURATION, DEFAULT_DURATION_SECONDS
                    ),
                ): vol.In(sorted(DURATION_OPTIONS.values())),
                vol.Optional(
                    CONF_NORMAL_INTERVAL,
                    default=opts.get(
                        CONF_NORMAL_INTERVAL, DEFAULT_NORMAL_INTERVAL
                    ),
                ): vol.All(vol.Coerce(int), vol.Range(min=15, max=3600)),
                vol.Optional(
                    CONF_FAST_INTERVAL,
                    default=opts.get(CONF_FAST_INTERVAL, DEFAULT_FAST_INTERVAL),
                ): vol.All(vol.Coerce(int), vol.Range(min=5, max=120)),
                vol.Optional(
                    CONF_FAST_DURATION,
                    default=opts.get(CONF_FAST_DURATION, DEFAULT_FAST_DURATION),
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=900)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
