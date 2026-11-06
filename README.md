# Midea CCM18 Modbus Gateway for Home Assistant

Home Assistant integration for the Midea **CCM18 / CCM-18A** Modbus BMS gateway (also sold as Sinclair CCM18). The gateway connects a Midea VRF system with up to 64 indoor units to Modbus TCP. This integration exposes every indoor unit as a climate entity.

This is different from the Midea **CCM15** controller, which is already supported in Home Assistant by the built-in [`ccm15`](https://www.home-assistant.io/integrations/ccm15) integration over HTTP. The CCM18 is controlled over Modbus TCP instead.

## Features

- Indoor units that are online on the gateway are discovered automatically.
- One device and climate entity per indoor unit, with:
  - HVAC mode: off, heat, cool, dry, fan only, auto
  - target temperature (16–32 °C) and current room temperature
  - fan speed: auto, low, medium, high
  - swing on/off
  - error and protection codes as attributes
- Diagnostics download.

The gateway is polled every 30 seconds.

## Requirements

- Home Assistant 2026.11.0 or newer.
- A CCM18 gateway with Modbus TCP enabled and reachable from Home Assistant (port 502 by default).

## Installation

### HACS

[![Open your Home Assistant instance and open this repository in HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=kpucynski&repository=ha-midea-ccm18&category=integration)

1. In HACS, open the menu in the top right and select **Custom repositories**.
2. Add `https://github.com/kpucynski/ha-midea-ccm18` with type **Integration**.
3. Search for **Midea CCM18 Modbus Gateway**, download it, and restart Home Assistant.

### Manual

Copy `custom_components/ccm18` into the `custom_components` folder of your Home Assistant configuration directory and restart Home Assistant.

## Configuration

[![Open your Home Assistant instance and start setting up the integration.](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=ccm18)

Go to **Settings → Devices & services → Add integration**, search for **Midea CCM18 Modbus Gateway**, and enter:

| Field | Default | Description |
| --- | --- | --- |
| Host | | IP address or hostname of the gateway |
| Port | 502 | Modbus TCP port |
| Modbus device ID | 1 | Modbus slave address configured on the gateway |

## Known limitations

- Switched-off units do not report their mode. Turning a unit on restores the last mode Home Assistant saw, or auto if none was seen since startup.
- The gateway takes a few seconds to report changes, so the entity is updated optimistically after a command.
- Outdoor units and the whole-system on/off register are not exposed.

## Protocol

Based on the [CCM18 Modbus mapping table](https://www.sinclair-solutions.com/files/user-manual-en/accessories/um-ccm18-modbus-mapping-table-en-v01.pdf). The gateway returns corrupted data when more than 8 coils are read in one request, so coils are read one octet at a time.

## Removal

Remove the integration under **Settings → Devices & services**, then remove the repository in HACS.
