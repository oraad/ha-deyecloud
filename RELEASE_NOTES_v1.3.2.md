## DeyeCloud v1.3.2

The station **Last update** sensor now shows a real time instead of a raw
number. No other entity or unique-ID changes.

### Fixed

- **"Last update" showed a bare epoch** - the sensor reads `lastUpdateTime`
  from `/station/latest`, which is a Unix timestamp in seconds such as
  `1781963148`. It had no device class, so Home Assistant had no reason to
  treat the value as a date and the frontend rendered the raw number.

  The value is now converted to a timezone-aware `datetime` and the entity
  carries the `timestamp` device class, so the state is `2026-06-20T13:45:48+00:00`
  and the frontend displays it as a date and a relative time. Epochs outside
  2000-2100 are dropped rather than passed through, so a zero, a millisecond
  epoch, or a non-numeric string from the API cannot produce an unrenderable
  value on every poll.

### Technical notes

- The `timestamp` device class is non-numeric in Home Assistant, so the entity
  deliberately declares **no** unit of measurement and **no** state class.
  Supplying either is a hard error or a logged warning in Home Assistant, and
  the class is documented as having a unit of `None`. The value is therefore a
  `datetime` rather than a number.
- The device sensor shares the same measure-point mapping, so a measure point
  named `lastUpdateTime` on a device would hit the same non-numeric contract
  and is converted the same way.
- Entity metadata changed, but unique IDs did not. Existing entities pick this
  up on reload; none need to be removed and re-added.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.

Entity unique IDs are unchanged from v1.3.1.
