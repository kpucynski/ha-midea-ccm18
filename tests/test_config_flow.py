"""Tests for the CCM18 config flow."""

from unittest.mock import AsyncMock

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant.common import MockConfigEntry

from custom_components.ccm18.api import CCM18Error
from custom_components.ccm18.const import CONF_DEVICE_ID, DOMAIN

USER_INPUT = {CONF_HOST: "10.0.1.40", CONF_PORT: 502, CONF_DEVICE_ID: 1}


async def test_user_flow(hass: HomeAssistant, mock_ccm18: AsyncMock) -> None:
    """Test a successful user flow."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "CCM18 10.0.1.40"
    assert result["data"] == USER_INPUT
    mock_ccm18.close.assert_awaited()


@pytest.mark.parametrize(
    ("side_effect", "return_value", "error"),
    [
        (CCM18Error("timeout"), None, "cannot_connect"),
        (RuntimeError("boom"), None, "unknown"),
        (None, [], "no_units"),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant,
    mock_ccm18: AsyncMock,
    side_effect: Exception | None,
    return_value: list[int] | None,
    error: str,
) -> None:
    """Test errors shown by the user flow, and recovery afterwards."""
    mock_ccm18.async_get_online_units.side_effect = side_effect
    mock_ccm18.async_get_online_units.return_value = return_value
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_ccm18.async_get_online_units.side_effect = None
    mock_ccm18.async_get_online_units.return_value = [0]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_already_configured(
    hass: HomeAssistant, mock_ccm18: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the same host cannot be added twice."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
