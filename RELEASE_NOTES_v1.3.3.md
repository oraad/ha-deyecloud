## DeyeCloud v1.3.3

This release is mostly maintenance. The one thing that affects you is the
raised minimum Home Assistant version, and it is deliberate.

### Breaking

- **Minimum Home Assistant is now 2026.7.0** (was 2026.3.2). HACS will no
  longer offer DeyeCloud to installs older than 2026.7.0.

  Home Assistant 2026.7.0 is the first release that requires aiohttp 3.14,
  which the test tooling depended on could not support. Rather than cap the
  supported range, the API tests were moved onto Home Assistant's own
  maintained HTTP mocker, which allowed the floor to be raised cleanly. There
  is no runtime behaviour change and no entity or unique-ID change.

  Staying on 2026.3.2 through 2026.6.x? You can keep using v1.3.2, which
  supports it.

### Technical notes

- The API tests no longer use `aioresponses`, which was unmaintained and
  broken against aiohttp 3.14. They now use `aioclient_mock` from
  `pytest-homeassistant-custom-component`, so the HTTP mocking tracks whatever
  aiohttp version the pinned Home Assistant ships with. `aioresponses` is no
  longer a dependency.
- `pytest-cov` moved from 7.0.0 to 7.1.0. A previous note claimed 7.1.0 was
  uninstallable; that was wrong, and the newer `pytest-homeassistant-custom-component`
  now requires 7.1.0 exactly.
- `pytest-homeassistant-custom-component` 0.13.318 to 0.13.344, which is the
  release that pins Home Assistant 2026.7.0.
- The minimum is declared in `hacs.json` and pinned in `requirements.txt`.
  The manifest is deliberately left without a Home Assistant version: hassfest
  rejects `manifest.json` keys it does not define, so the floor lives in
  `hacs.json` alone.
- Ruff 0.15.7 to 0.15.21.
- Removed 8 ruff ignore rules that no longer matched any finding, so a future
  regression in those rules is no longer silently suppressed.
- Line endings are now normalized to LF repository-wide instead of only for
  `scripts/`.
- Added Renovate for dependency updates, with a three-day minimum release age,
  and Home Assistant plus the two packages pinned to it held back from
  automatic bumps.
- Added issue templates that ask for the Home Assistant and DeyeCloud versions
  up front, which is the first thing needed to reproduce most reports.

### Verification

181 tests pass on Home Assistant 2026.7.0 with 95.28% coverage. Ruff, ruff
format and mypy are clean.

### Upgrade

1. Update via HACS or replace `custom_components/deyecloud` with the release zip.
2. Restart Home Assistant.

Entity unique IDs are unchanged from v1.3.2.
