# Pilot acceptance

- [ ] Both channels install from anonymous GHCR pulls; Supervisor performs no local build.
- [ ] Stable points to the last regular release; Main points to a complete successful
      source snapshot. Broken/newer upstream builds leave the last good publication.
- [ ] Missing, wrong-domain, mismatched and expired certificates keep help reachable.
- [ ] Every visible installation step has all Nocturne languages, browser/config language
      selection and native-language review. HA option descriptions cover the same list.
- [ ] A newcomer without command-line experience completes DuckDNS, trusted certificate,
      local DNS, passkey setup, second-device and restart checks using the guide alone.
- [ ] Certificate renewal is tested with the chosen manager. The separate Let's Encrypt
      app receives a scheduled start; two managers never overwrite the same files.
- [ ] Every Nocturne version/source link opens Nocturne code at the exact source SHA;
      release, wrapper and build links have distinct labels and destinations.
- [ ] Ten consecutive prebuilt HAOS upgrades show no new app BuildKit cache; appdata,
      runtime layers, logs and backups are measured separately.
- [ ] Cold backup/restore includes secrets and account/passkey state. Old image plus
      upgraded database is not presented as a valid downgrade strategy.
- [ ] AMD64 → ARM64 database migration is rehearsed before promising portability.
- [x] AMD64 and ARM64 pass native runtime/setup/recovery CI and anonymous image verification.
- [ ] Complete ARM64 installation and upgrade acceptance on real HAOS hardware.
- [ ] Registry visibility, unavailable downloads, partial publication and safe retries
      have been rehearsed. Dependency rebuilds create fresh package versions.
- [ ] Upstream maintainers accept placement, language tooling, public repository identity,
      licensing/source provision, update policy and ongoing ownership.

## Existing installation migration

This new repository and its `#home-assistant` branch have a different HA repository
identity from the existing `smokkelaar/nocturne-home-assistant` installation. Preserve
the old app until a cold export/restore has been tested. The retained slugs do not make
that identity change disappear. Stable and Main must not share a database directory.
Keep the existing domain for passkeys when moving an account. Document logical dump/
restore when binary PostgreSQL files cannot be reused on another platform.
