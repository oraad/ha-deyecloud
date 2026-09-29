## DeyeCloud v1.3.0

Adds panel optimizer support and stops spending API quota on devices that cannot report telemetry. Also fixes three OpenAPI parsing mismatches that broke the integration on some accounts.

### Added

- **Panel optimizer sensors** - each `OPTIMIZER` device now appears as its own device under the station subentry with three entities:
  - **Production today** (kWh) - local-day total.
  - **Production this month** (kWh) - local-month total.
  - **Average power** (W) - reconstructed from the production series, since optimizers expose no instantaneous value.
- **Optimizer Concentrator** - the `OPTIMIZER_CONCENTRATOR` device type is now recognised and labelled instead of being reported as an unknown type. It carries no telemetry of its own and gets no production sensors.
- **India data center** - `https://india-developer.deyecloud.com/v1.0` is now selectable in the config flow.
- **Arabic translations** for the new optimizer entities.

### Fixed

- **API quota** - `COLLECTOR`, `OPTIMIZER`, and `OPTIMIZER_CONCENTRATOR` devices always return an empty `deviceDataList` and reject `/device/measurePoints` with `"device not supported"`. They are now excluded from both calls, so a plant stops spending a full 10-serial batch per poll on guaranteed-empty responses. On a 1-inverter + 8-optimizer plant this removes one request per 3-minute poll. Unknown or missing device types are still polled, so unrecognised new models keep working.
- **Authorization header** - the spec documents `accessToken` with the `Bearer ` scheme already applied next to a separate `tokenType`, which produced a doubled `Bearer Bearer <token>` header. A redundant prefix is now stripped.
- **Token lifetime** - `expiresIn` is declared as a string but the documented example emits a number. Both are accepted, and an unparseable value no longer causes an immediate refresh loop.
- **Measure-point catalog** - `measurePoints` is documented as an array of key strings, but the live API returns objects. Both forms are now parsed instead of returning an empty catalog.
- **Removed optimizers** - optimizer entities are now cleaned up when the device disappears, instead of being orphaned in Home Assistant.

### Technical notes

- Optimizer history is polled every 15 minutes rather than every 3, because `/device/history` at daily granularity only moves at the rollup level.
- Day and month boundaries use the plant's `regionTimezone` from the station payload, so production resets at local midnight and not at UTC midnight.
- **Average power** is a running average since the start of the current day, computed from the kWh delta over elapsed time. A series that stops moving is held at its last value for one hour, then reported as `0 W`, so an idle inverter reads idle instead of decaying towards zero.
- The daily and monthly `granularity` values (`2` and `3`) are not documented in the OpenAPI schema and were confirmed against a live station.
- Each energy sensor is `TOTAL` with a `last_reset` at local midnight, so Home Assistant's energy dashboard handles it correctly rather than reporting a 24-hour drop.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.
3. Optimizer entities are discovered on the first poll after restart and may take up to 3 minutes to appear.

Existing entity unique IDs are unchanged, so no cleanup is required. The three new optimizer entities use their own device serial and are not affected by earlier naming changes.
