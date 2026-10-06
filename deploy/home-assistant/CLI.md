# Home Assistant diagnostic CLI

Stable and Main images include a read-only `nocturne-ha` command for use inside
the app container:

```sh
nocturne-ha doctor
nocturne-ha status
nocturne-ha api /api/v3/version
nocturne-ha api /api/v4/status
```

`doctor` checks configuration, DNS resolution, the configured certificate pair
and local API reachability. `status` is an alias. `api` sends GET requests only
to local `/api/...` paths, without credentials, redirects or writes. Responses
are limited to 2 MB and may contain private data; do not publish them unredacted.
The CLI does not provide a shell or expose host access.
