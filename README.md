# Nocturne for Home Assistant — upstream proposal

[![Add to Home Assistant](https://my.home-assistant.io/badges/supervisor_add_addon_repository.svg)](https://my.home-assistant.io/redirect/supervisor_add_addon_repository/?repository_url=https%3A%2F%2Fgithub.com%2Fsmokkelaar%2Fnocturne-home-assistant-upstream%23home-assistant)

[![Wrapper checks](https://github.com/smokkelaar/nocturne-home-assistant-upstream/actions/workflows/ha-validate.yml/badge.svg)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/actions/workflows/ha-validate.yml)
[![Publish Stable and Main](https://github.com/smokkelaar/nocturne-home-assistant-upstream/actions/workflows/ha-publish.yml/badge.svg)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/actions/workflows/ha-publish.yml)
[![Main branch checks](https://img.shields.io/github/checks-status/smokkelaar/nocturne-home-assistant-upstream/main?label=Main%20branch%20checks)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/commits/main/)

[![Stable HA package](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fsmokkelaar%2Fnocturne-home-assistant-upstream%2Fhome-assistant%2Fstable%2Fconfig.json&query=%24.version&label=Stable%20HA%20package&color=blue)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/stable/config.json)
[![Stable Nocturne](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fsmokkelaar%2Fnocturne-home-assistant-upstream%2Fhome-assistant%2Fstable%2Fprovenance.json&query=%24.upstream_tag&label=Stable%20Nocturne&color=blue)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/stable/provenance.json)
[![Main HA package](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fsmokkelaar%2Fnocturne-home-assistant-upstream%2Fhome-assistant%2Fmain%2Fconfig.json&query=%24.version&label=Main%20HA%20package&color=orange)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/main/config.json)
[![Main Nocturne snapshot](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Fraw.githubusercontent.com%2Fsmokkelaar%2Fnocturne-home-assistant-upstream%2Fhome-assistant%2Fmain%2Fprovenance.json&query=%24.upstream_tag&label=Main%20Nocturne&color=orange)](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/main/provenance.json)

Stable and Main, prebuilt in GitHub Actions, with a multilingual setup assistant.
This clean repository contains the complete existing HA runtime, redesigned help,
and a publication pipeline. Personal extensions and legacy test channels are excluded.
The runtime derives from smokkelaar/nocturne-home-assistant at
`8ad3595da10fd109411e3e1cb58a5d8fc8816ea8`, under AGPL-3.0-only.

**Pilot, not yet an accepted Nightscout distribution.** Images become installable only
after container tests and anonymous registry verification pass. A build failure keeps
the previously published store version. Real HAOS upgrades and passkey/browser checks
remain part of the user test plan.

Development experiments and smokkelaar's personal test builds live in
[nocturne-home-assistant](https://github.com/smokkelaar/nocturne-home-assistant).
Suitable changes are carried over here after testing; experimental Personal and
Test A/B/C builds are not automatically included in Stable or Main.

## At a glance

The version badges read the **published `home-assistant` branch**, so they update
after a successful publication without editing this README. HA package versions
and Nocturne versions are separate; Main identifies an exact source snapshot.
GitHub/Shields caching can briefly delay badge updates. The linked metadata is the
source of truth.

| Item | Stable | Main |
| --- | --- | --- |
| Nocturne source | Published Nocturne release | Tested snapshot of Nocturne `main` |
| Published version, source SHA and image digests | [Stable metadata](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/stable/provenance.json) | [Main metadata](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/main/provenance.json) |
| Installation | Prebuilt container | Prebuilt container |
| Supported architecture | [Published architectures](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/stable/config.json) (`amd64` currently) | [Published architectures](https://github.com/smokkelaar/nocturne-home-assistant-upstream/blob/home-assistant/main/config.json) (`amd64` currently) |
| Default HTTPS port | 8448 | 8449 |
| Update checks | Every six hours | Every six hours |
| Setup languages | Eleven; English by default | Eleven; English by default |

### Checks before publication

The workflow badges above show actual GitHub Actions results; **Main branch
checks** summarizes the check runs on the current maintained-source commit.
A green **Wrapper
checks** badge covers the automated wrapper regression suite. **Publish Stable
and Main** runs candidate validation and, for changed channels, container startup,
setup and previous-version recovery tests before publishing. Promotion verifies
anonymous image pulls, HA image labels and increasing package versions. An
unchanged-channel run can succeed without publishing a new version; a failed run
leaves the last published version available. Open the workflow for individual
check results.

### Home Assistant security and access

Both channels use the same [app configuration](deploy/home-assistant/shared/app-spec.json).

| Property | Configuration |
| --- | --- |
| HA security rating | **Expected 6/6** with the default configuration; verify the actual rating in your HA app information page |
| Ingress | Enabled for the HA setup/status interface; Nocturne opens separately over HTTPS |
| AppArmor | Home Assistant's default profile enabled; no custom profile is shipped |
| Protection mode | No unprotected-only permissions are requested; keep protection mode enabled |
| Host access | No host network/PID access, Docker API or privileged capabilities requested |
| Home Assistant APIs | No Supervisor API or Home Assistant Core API access requested |
| Certificates | `/ssl` is mounted read-only |
| Backups | Cold backups; restore behavior is tested before publication |

The expected rating follows [Home Assistant's documented rating rules](https://developers.home-assistant.io/docs/apps/presentation/#security):
the base score is 5, ingress adds 2, and the score is capped at 6. This is a
configuration-based expectation, not a measurement from a user's installation or
a security audit. The actual rating and protection/AppArmor state are shown by
Supervisor and can depend on local settings. Real HAOS and live-provider checks
remain in the [acceptance checklist](docs/ACCEPTANCE.md).

## Install

Use **Add to Home Assistant** above to add the tested pilot repository, or add:

```
https://github.com/smokkelaar/nocturne-home-assistant-upstream#home-assistant
```

The `home-assistant` branch contains only generated store metadata. `main` contains
the maintained source. This separation is deliberate: Supervisor discovers configs
recursively, including unrelated `config.json` files in a large application repository.

Choose **Nocturne Stable** or **Nocturne Main**, start the app, then open its HA web
interface. It guides you through the domain, DuckDNS / Let's Encrypt, certificate files,
local DNS and Nocturne sign-in. Certificate/setup errors keep the help interface running.
Configure the app in Home Assistant and restart after saving. Certificates in `/ssl`
are read-only; the assistant does not change your router or Home Assistant Core HTTPS.

- [English setup guide](docs/SETUP.en.md)
- [Nederlandse installatiehulp](docs/SETUP.nl.md)
- [Exact upstream integration plan](docs/UPSTREAM-INTEGRATION.md)
- [Architecture and automatic publication](docs/ARCHITECTURE.md)
- [Acceptance and migration checklist](docs/ACCEPTANCE.md)
- [Issue discussion and rationale](https://github.com/smokkelaar/nocturne-home-assistant/issues/41)

## Development

Python 3.12+, Node 24, OpenSSL; Docker Linux for runtime tests.

```sh
python -m pip install -r deploy/home-assistant/requirements-ci.txt
python -m unittest discover -s deploy/home-assistant/tests -v
python deploy/home-assistant/tools/check_locales.py --upstream
python deploy/home-assistant/tools/preview.py
```

Open `http://127.0.0.1:8765/?lang=en` for a synthetic setup preview. It has no access
to HA, credentials or medical data. Stop the preview with Ctrl+C.

Edit messages in `deploy/home-assistant/shared/rootfs/opt/nocturne-ha/locales/*.json`.
All eleven Nocturne languages have the same message keys. English is the default.
Choose `auto` explicitly to follow the browser language, or select another language
in HA configuration. Existing settings are retained when upgrading. Translations are initial
drafts and should receive native-speaker review before upstream acceptance.

AMD64 is the first published target. Change `deploy/home-assistant/platforms.json`
to `["amd64", "arm64"]` to run the complete native build/test pipeline for both.
No ARM64 app is advertised until all requested platform jobs pass. HA calls ARM64
`aarch64`; the generator maps that to Docker's `linux/arm64`.

The first GHCR packages may default to private. Make the two package visibilities public;
the promote job refuses to advertise images that cannot be pulled anonymously. A rerun
gets a fresh package version. Subsequent successful publications are automatic.

Original wrapper copyright and license notices are preserved in [LICENSE](LICENSE).
Upstream Nocturne and dependencies retain their own licenses. See
[distribution provenance](docs/ARCHITECTURE.md#source-and-licenses).
