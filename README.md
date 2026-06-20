# DeyeCloud Home Assistant Integration

Monitor DeyeCloud stations and devices in Home Assistant using the official DeyeCloud OpenAPI.

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![homeassistant](https://img.shields.io/badge/Home%20Assistant-2026.3.2+-blue.svg)](https://www.home-assistant.io/)
[![quality scale](https://img.shields.io/badge/quality%20scale-platinum-99d0ff.svg)](https://www.home-assistant.io/docs/quality_scale/)

Requires [My Home Assistant](https://my.home-assistant.io/) linked to your instance.

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=oraad&repository=ha-deyecloud&category=integration)
[![Install](https://my.home-assistant.io/badges/hacs_integration.svg)](https://my.home-assistant.io/redirect/hacs_integration/?domain=deyecloud)
[![Set up](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=deyecloud)

## Features

- One config sub-entry per station
- All devices belonging to each station are grouped under that sub-entry
- Dynamic sensors from the union of cached `/device/measurePoints` catalogs and `/device/latest` telemetry
- Station-level sensors from station latest data
- Connectivity binary sensors per device
- Re-authentication and reconfiguration flows
- Diagnostics with credential redaction
- Platinum-targeting integration quality scale

## Requirements

- Docker (recommended for development and CI parity)
- Home Assistant 2026.3.2 or newer (config sub-entries, local brand images)
- DeyeCloud account
- DeyeCloud developer application ([developer.deyecloud.com](https://developer.deyecloud.com/app))

## Installation

### HACS (recommended)

1. Make sure [HACS](https://hacs.xyz/) is installed.
2. **Add repository** — [![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=oraad&repository=ha-deyecloud&category=integration) and confirm category **Integration**.
3. **Install** — [![Install](https://my.home-assistant.io/badges/hacs_integration.svg)](https://my.home-assistant.io/redirect/hacs_integration/?domain=deyecloud), then click **Download** in HACS.
4. Restart Home Assistant.
5. **Set up** — [![Set up](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=deyecloud) or **Settings → Devices & services → Add integration** and search for **DeyeCloud**.

#### Manual HACS setup

If the buttons above do not work:

1. Open **HACS → Integrations →** ⋮ **→ Custom repositories**.
2. Add repository URL `https://github.com/oraad/ha-deyecloud` with category **Integration**.
3. Install **DeyeCloud**, restart Home Assistant, then add the integration.

### Manual zip install

1. Download the latest `deyecloud-x.y.z.zip` release asset.
2. Extract it into your Home Assistant `config` directory so the path becomes `config/custom_components/deyecloud/`.
3. Restart Home Assistant.

### Development install

1. Clone this repository.
2. Build the dev image: `scripts/docker setup`.
3. Start Home Assistant: `scripts/docker develop` (or `docker compose up homeassistant`).

## Configuration

Start setup with the [![Set up](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=deyecloud) button above, or:

1. Go to **Settings → Devices & services → Add integration**.
2. Search for **DeyeCloud**.
3. Enter:
   - DeyeCloud username or email
   - Password
   - App ID and App Secret from the developer portal
   - API region (Europe/Asia-Pacific or Americas)
   - Optional company ID for installer/business accounts
4. The integration validates credentials and creates one station sub-entry per selected station.
5. During setup, choose which stations to load. Change this later via **Configure → Select stations**.

## Entity naming

Entities use `has_entity_name = true` and stable unique IDs:

- Device telemetry: `station_{station_id}_dev_{serial}_{measure_key}`
- Station metrics: `station_{station_id}_station_{metric}`
- Child device names show the device type only (e.g. `Inverter`); when multiple devices share a type in one station, the serial is appended (e.g. `Battery 05403000CA180191`)
- Friendly names use translation keys where available, with API catalog names as fallback
- Device sensors expose a `collection_time` attribute when the API provides it

## Supported device types

`INVERTER`, `MICRO_INVERTER`, `COLLECTOR`, `BATTERY`, `MECD`, `METER`, `RELAY_BOX`, `OPTIMIZER`, `PV_MODULE`

Telemetry sources:

- **Inverters** — full sensor catalogs from `/device/measurePoints` plus live values from `/device/latest`
- **Station metrics** — `/station/latest` fields such as `generationPower`, `consumptionPower`, `batterySOC`
- **Batteries, collectors, optimizers, meters** — typically expose an **Online** binary sensor only; DeyeCloud often returns `device not supported` for `/device/measurePoints` on these types

## Known limitations

- DeyeCloud typically updates telemetry every 3–5 minutes; the integration polls every 180 seconds (3 minutes).
- `/device/latest` accepts up to 10 device serial numbers per request.
- Some diagnostic measure points are disabled by default to reduce entity noise.
- `/device/measurePoints` is not available for all device types; permanent API failures are cached and logged at debug level.

## Troubleshooting

- **Authentication failed**: verify username/password, app credentials, and region (Europe/Asia-Pacific vs Americas).
- **No stations found**: confirm the account has stations and company ID is set for business accounts.
- **Stations appear but no devices or entities**: reload the integration after upgrading; check **Diagnostics** for `device_counts`. On first install, station subentries must finish syncing before entities are created.
- **Measure point catalog warnings**: expected for batteries, collectors, and optimizers (`device not supported` or `no upload records found`). Inverter telemetry should still appear.
- **Missing station-level sensors**: confirm `/station/latest` returns fields like `generationPower` and `batterySOC` for the station in the DeyeCloud app.
- **Entities unavailable**: check diagnostics and repair issues in Settings → Repairs.

## Removal

1. Delete the DeyeCloud integration from **Settings → Devices & services**.
2. Remove `custom_components/deyecloud` if installed manually.
3. Restart Home Assistant.

## Development

Requires **Docker** (recommended), **Python 3.14** inside the container (see [`.python-version`](.python-version)), and **Home Assistant 2026.3.2+**.

### Docker (recommended)

Works the same on Windows (Git Bash or WSL), Linux, and macOS.

```bash
scripts/docker setup      # build dev image
scripts/docker develop    # Home Assistant on http://localhost:8123
scripts/docker lint
scripts/docker test
scripts/docker mypy
scripts/build_zip 1.0.0   # release zip artifact
python3 scripts/generate_brand_assets.py   # requires cairosvg; outputs integration brand PNGs
```

Equivalent compose commands:

```bash
docker compose build dev
docker compose up homeassistant
docker compose run --rm dev python3 -m pytest
```

### VS Code dev container

Reopen the repository in a container (uses `docker-compose.yml`). Then run `scripts/develop` inside the container, or `docker compose up homeassistant` from the host.

### Local Python (fallback)

Only if Docker is unavailable:

```bash
scripts/setup && scripts/develop   # inside a dev container shell
scripts/test                       # via Docker when available
python3 -m pytest                  # direct host Python
```

## License

MIT
