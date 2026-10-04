# Runtime and delivery

## One shared runtime, two isolated channels

`deploy/home-assistant/shared/rootfs` contains the complete PostgreSQL 17 + .NET API +
Node web + nginx TLS gateway runtime. API and web bind to loopback. The HA help listener
uses port 8099 and accepts only the Supervisor ingress peer; it is never host-published.
Host port 8448 is the stable default and 8449 the main default (container TLS port 8448).
PostgreSQL is stopped after clients. Persistent `/data` is never automatically reset.
Separate channels use separate data, roles/secrets and cookie namespaces.

The helper starts before option/TLS/backend validation. On start failure, backend
processes shut down and the helper remains accessible until the app is restarted.
No token is passed to the child applications; `/ssl` remains read-only. The helper never
requests a certificate, accepts certificate terms, stores a DuckDNS token or changes
HA Core networking. Configuration stays in Home Assistant. The extra gateway code is
shown only to an authenticated HA ingress client after successful startup.

With the gateway disabled, native-auth checks normally run before web startup.
Unconfirmed checks retain the outer gateway and show the reason without stopping
healthy services. Explicit `skip_gateway_check: true` with `gateway_auth: false`
skips only this wrapper preflight; Nocturne still controls read/write permissions.
TLS, host/tenant validation and forwarded-header protections remain active. The
helper visibly reports the bypass. Examples use a fixed generic domain.

Self-signed certificates are restricted to disposable CI containers through
`NOCTURNE_CI_TEST_CERTIFICATE=1`. Normal installations require a trusted certificate
pair; a missing pair opens the help path rather than a fake successful setup.

Server checks do not prove your phone's DNS route, browser trust or passkey ceremony.
The guide explicitly asks users to verify these on their devices.

## Publication

Selection chooses the published stable release and resolves the current main source SHA
before checking its successful paired publisher. If that publisher is incomplete or fails,
the existing store remains available and the next scheduled run retries. This avoids
promoting an older result from a paginated workflow list. It uses `main-<sha7>` instead
of confusing `latest` with main. Each API digest
is verified against the full source revision. Web correspondence relies on the successful
paired upstream publisher; it does not claim an embedded revision label where absent.

Per-platform child digests are fixed before building. The pnpm version is read from the
matching upstream workflow, not guessed from the current branch. Node is pinned by
its existing image digest; apt/PGDG package versions are not hermetic. Candidate context
artifacts are carried unchanged from selection into native build jobs.

Each native job builds once, runs smoke/start/restart/gateway/TLS checks, verifies that
missing certificates keep the helper available, and performs cold restore plus an upgrade
from the previous published image. On the first publication, same-version restore is
tested; that is not evidence of a historical upgrade. The tested image is pushed as-is.
Promotion verifies anonymous pulls and HA version/architecture labels before writing
store config. Stable and Main publish both AMD64 and ARM64 using native runners.
Upstream update checks run hourly; unchanged candidates do not trigger a rebuild.

Images use `ghcr.io/<owner>/<repository>/nocturne-<channel>-<ha-arch>:<version>`.
HA uses `{arch}` in the image path. Main and Stable share the runtime source but not data.
Package versions are plain MAJOR.MINOR.PATCH. The patch includes the publication
run/attempt counter and is greater than the highest stored patch even after a counter
reset. Both selection and promotion reject versions that are not strictly newer using
Home Assistant's AwesomeVersion comparator. Hyphenated counters and build metadata
are prohibited; Nocturne's version remains separate metadata.
Unchanged source/recipe/platforms skip a build. Dispatch `force=true` for dependency
maintenance. Neither action updates an installed HA app unless its owner enables updates.

Concurrent publishers are serialized. Source is snapshotted; a later upstream commit is
picked up in the next run. Published tags must not be overwritten. Retain old tags needed
for backups and previous-version upgrade tests. A failure can leave unused images but
must not advertise an absent candidate. Caches, downloaded layers and appdata still need
bounded retention; prebuilt delivery only removes this app's new local buildcache.

## Source and licenses

Original code copied from `smokkelaar/nocturne-home-assistant` at
`8ad3595da10fd109411e3e1cb58a5d8fc8816ea8` remains AGPL-3.0-only. Original copyright
notices are in LICENSE. Personal code is excluded. Each build records wrapper/source
SHA, pinned API/web digests, workflow identity, recipe fingerprint and final runtime
digests. The Docker recipe and frontend compatibility patches are public.

Upstream Nocturne declares AGPL-3.0; its missing root license file and the complete
corresponding-source/third-party notice requirements remain an upstream acceptance item.
Do not describe that review as completed. Container packages retain upstream and dependency
licenses. SBOM/provenance attestation and a scheduled vulnerability policy are follow-up
hardening tasks; the pilot currently records provenance JSON and immutable source links.

## Known evidence limits

Local unit tests are not HAOS tests. Container CI tests have disposable synthetic data
and no real vendor connection, account migration or medical-data validation. Real
DuckDNS renewal, browser trust, cross-architecture database portability, actual HAOS
storage growth and native-speaker translation reviews must be completed in the pilot.
