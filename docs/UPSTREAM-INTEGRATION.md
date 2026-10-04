# Integration into nightscout/nocturne

## Target layout

Copy these source paths without importing this repository's `.git` history:

| This repository | nightscout/nocturne | Purpose |
| --- | --- | --- |
| `deploy/home-assistant/` | `deploy/home-assistant/` | Runtime, build template, resolvers, tests and generated message catalogs |
| `.github/workflows/ha-validate.yml` | `.github/workflows/ha-validate.yml` | Scoped wrapper validation |
| `.github/workflows/ha-publish.yml` | `.github/workflows/ha-publish.yml` | Native image tests and store publication |
| User setup documentation | `docs/home-assistant/` | Maintained installation guidance, with links from the docs portal |
| Root README installation paragraph | Section in upstream README | Official install link after maintainers accept the integration |
| Source-license attribution | `deploy/home-assistant/NOTICE.md` | Retain original wrapper attribution; resolve upstream license file |

Do not copy this project's root README, AGENTS, LICENSE or planning documents over
upstream's files. Upstream AGENTS explicitly prohibits committing plans/design documents;
keep this integration plan in issue #41 / the proposal conversation. Convert only stable,
user-facing setup and maintenance documentation into upstream docs.

Existing upstream deploy families (`docker-compose`, `helm`, `oracle-cloud`, `portainer`)
remain separate. No personal fork or healthcare feature changes are included.

## Store distribution branch

Recommended upstream link:

```
https://github.com/nightscout/nocturne#home-assistant
```

The generated branch has only:

```
repository.yaml
stable/{config.json,provenance.json,README.md,DOCS.md,CHANGELOG.md,translations/}
main/{config.json,provenance.json,README.md,DOCS.md,CHANGELOG.md,translations/}
```

It contains no workflows or source checkout. Publication updates this branch after tests
and anonymous pull validation. Supervisor accepts `#branch` repository selectors and
recursively discovers app configs. This avoids discovering unrelated SDK/config files
in upstream main, and avoids downloading the full source tree into HA's store.

Maintainers may prefer a dedicated official HA distribution repository instead; source
can stay under `deploy/home-assistant` in Nocturne. Changing the chosen repository/branch
link later changes HA's repository identity. Freeze the public link before broad use.

References: [repository selector implementation](https://github.com/home-assistant/supervisor/blob/main/supervisor/validate.py),
[config discovery](https://github.com/home-assistant/supervisor/blob/main/supervisor/store/data.py),
[repository root requirement](https://developers.home-assistant.io/docs/apps/repository/).
Real Supervisor discovery on the minimum supported version must still be tested.

## Workflows

The pilot polls every hour and follows upstream's paired publisher jobs. For upstream
acceptance, convert candidate selection into a reusable `workflow_call` with exact API/web
digests, source SHA, source ref and event type as inputs. Call it only after the
`dotnet-images`, `web-image` and `report` jobs succeed in `docker-publish.yml`.

- A regular published release promotes Stable; prereleases do not.
- A successful main image build promotes Main; a failed new head leaves the last good
  main build available. A source commit is fixed throughout the HA build.
- Keep a scheduled/dispatch path for wrapper fixes and dependency rebuilds.
- Retain per-platform runtime, previous-version upgrade and cold-restore checks.
- Keep source checkout pinned to the calling trusted workflow SHA. Pull requests have
  read-only validation and never publish images or store metadata.
- Do not rely on a bot Git push triggering a second workflow. Call the publication
  explicitly and account for `GITHUB_TOKEN` event suppression.
- Write to `home-assistant` only after all jobs pass. Never overwrite a published tag.
- If rules protect the distribution branch, use an approved narrowly scoped GitHub App
  or a metadata PR. Do not weaken branch rules to accommodate the publisher.

## Languages and frontend integration

The pilot keeps the installation helper independent of Nocturne's web service. A missing
certificate/database must not make the helper disappear. Its lightweight Python renderer
is served through HA ingress before any backend process starts.

In the upstream monorepo, `src/Web/supportedLocales.json` becomes the source of truth;
remove the copied list and read that file at build time. Nocturne currently uses Wuchale
with shared PO catalogs in `src/Web/locales/` and extraction globs in
`src/Web/wuchale.shared.js` for `app` and `portal`.

For long-term shared translation tooling, place the helper frontend in a small
`src/Web/packages/ha-setup` package, add its extraction globs to `wuchale.shared.js`, and
build a static helper asset bundle copied into the runtime. The helper must still start
without the Nocturne frontend/API. Use a translation export adapter to produce the
runtime catalog; preserve stable keys and translator context. Do not replace Wuchale
in the existing app or portal. Agree this adapter with maintainers before implementation.

HA store option descriptions are generated separately in `translations/{locale}.json`.
Runtime help, configuration labels, diagnostic actions, docs and store descriptions
need language coverage; a translated dropdown alone is insufficient. Native-language
review of all instructions remains a release acceptance task.

## Proposed PR sequence

1. Retain attribution; review the wrapper runtime, process isolation, permissions, backups
   and the missing-certificate help mode. Agree source layout, public install identity
   and minimum HA/Supervisor versions.
2. Add help, language-source integration, correct source/release/wrapper/build links,
   detailed setup docs and newcomer usability tests.
3. Retain prebuilt AMD64/ARM64 image publication and the distribution branch; demonstrate ten
   HAOS upgrades without new local buildcache.
4. Retain native ARM64 CI validation and complete real HAOS hardware acceptance.
   Validate backup portability separately before promising cross-architecture migration.
5. Connect successful upstream publisher jobs and enable automatic promotion according
   to upstream's policy. Publish the accepted install link in upstream docs.

Merge source changes through focused PRs/cherry-picks or a reviewed patch export, not a
blind merge of unrelated repository histories. Do not create a PR against upstream until
the pilot evidence is collected and the maintainers agree the placement.
