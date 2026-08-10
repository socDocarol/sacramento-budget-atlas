# Azure App Service deployment hardening

This is the initial production operating contract for Sacramento Budget Atlas.
It documents settings and release gates only. It does not create or modify any
Azure resources.

## Initial topology

- Deploy the image directly as one Linux App Service custom container.
- Run exactly one App Service instance and one Uvicorn worker initially. Bundle
  promotion is protected by an OS file lock, but refresh scheduling and Shiny
  session state remain process-local.
- Keep the container target port at `8000`. For legacy custom-container
  configuration, set `WEBSITES_PORT=8000`; for sidecar-enabled configuration,
  set the container target port to `8000` in the container settings.
- Enable WebSockets and ARR affinity. Shiny sessions are stateful and must
  remain on the process that created them.
- Enable Always On and configure enough startup time for a cold source refresh.
  A starting value of 600 seconds for `WEBSITES_CONTAINER_START_TIME_LIMIT` is
  reasonable, then reduce it using observed startup telemetry.

Do not scale out until snapshot storage and refresh coordination move to a
multi-instance-safe design, such as immutable Blob objects promoted by a
separate ingestion job with a distributed lease.

## Health and traffic settings

- Configure App Service Health Check to request `/health/ready`.
- `/health/live` proves only that the process and event loop respond. Use it for
  container-level liveness checks, not Azure traffic admission.
- `/health/ready` returns success only when a validated snapshot is available
  and the cache is usable. Allow enough health-check grace time for the initial
  source refresh.
- Enable HTTPS Only and set the minimum TLS version to at least TLS 1.2. Prefer
  TLS 1.3 where the selected App Service environment supports it.
- Keep the application security-header middleware enabled. Verify HSTS,
  Content-Security-Policy, X-Content-Type-Options, Referrer-Policy,
  Permissions-Policy, and frame restrictions at the public endpoint after any
  Front Door or Application Gateway policy is applied.
- Restrict inbound traffic at the App Service, Front Door, or Application
  Gateway boundary appropriate to the release audience.
- Permit outbound HTTPS to the configured ArcGIS endpoint. Alert when refresh
  failures or snapshot age exceed the accepted service objective.

## Cache persistence

The image writes prepared snapshots only under the configured
`BUDGET_CACHE_DIR`. Its root filesystem is read-only in the local hardened
Compose configuration.

For the initial single-instance App Service deployment, choose one of these
explicitly:

1. Use ephemeral container storage at `/var/cache/sacramento-budget` and accept
   that a replacement or deployment requires a complete source refresh.
2. Enable App Service storage and set `BUDGET_CACHE_DIR` to a dedicated path
   under `/home`, such as `/home/data/sacramento-budget`, to preserve the cache
   across container replacements.

App Service `/home` storage is shared by scaled-out instances. Bundle promotion
uses an OS byte-range lock, but Azure Files lock behavior and multi-instance
refresh load must be validated before relying on it at scale. Prefer an
external refresh leader and immutable object storage before scaling out.
Monitor free space and apply the application's snapshot retention policy.

## Container and configuration controls

- Pull the image from a private registry by immutable digest. Use managed
  identity for registry access rather than registry passwords.
- Preserve the image's numeric non-root user, read-only application files,
  dropped Linux capabilities, and no-new-privileges policy where the hosting
  plan exposes those controls.
- Keep secrets in App Service settings backed by Key Vault references. Do not
  bake secrets or environment files into the image.
- Use separate staging and production settings. Treat cache directories,
  source URLs, log level, refresh interval, and schema version as slot-specific
  settings where slot swaps could otherwise mix environments.
- Keep `SHINY_TESTMODE` unset in every deployed slot.
- Set `APP_ALLOWED_HOSTS` to the exact public hostname and the App Service
  hostname. Do not deploy with a wildcard unless an upstream proxy validates
  the Host header.
- Leave `BUDGET_MANUAL_REFRESH_ENABLED=false` unless operators intentionally
  accept interactive users triggering source traffic. When enabled, configure
  an appropriate `BUDGET_MANUAL_REFRESH_COOLDOWN_SECONDS`.
- Send stdout and stderr logs to Azure Monitor or Log Analytics. Alert on 5xx
  responses, readiness failures, refresh failures, stale snapshot age, memory
  pressure, container restarts, and WebSocket disconnects.

## Release gates

The repository CI runs independent quality and container jobs. A release must
pass all of the following:

- Frozen dependency synchronization.
- Ruff lint and format checks.
- Unit tests, excluding tests explicitly marked live or end-to-end by the
  repository's default Pytest configuration.
- Container build from digest-pinned base images.
- SPDX JSON software bill of materials generation.
- Trivy image scan with no fixable high or critical operating-system or Python
  package vulnerabilities. Unfixed findings remain visible in the SBOM and
  should be reviewed as part of release risk acceptance.

The workflow builds and scans only. It does not authenticate to Azure, push an
image, alter infrastructure, or deploy the application.

## Experimental Azure Container Apps topology

The internal demo phase uses Azure Container Apps Consumption instead of the
always-on App Service topology above. This is a time-bounded cost optimization,
not a replacement for the production operating contract.

- Deploy in the `Microsoft Azure Enterprise - APPS` subscription and `westus2`
  region, in a resource group dedicated to this experiment.
- Allocate `0.5` vCPU and initially `1Gi` memory. Increase to `2Gi` before
  deployment if a clean ArcGIS refresh exceeds `768 MiB`, fails under the
  `1Gi` limit, or takes longer than five minutes to become ready.
- Configure `minReplicas=0` and `maxReplicas=1`. The app may scale to zero but
  must never scale beyond one replica while Shiny sessions and refresh state
  remain process-local.
- Use single revision mode, external HTTP ingress on target port `8000`, HTTPS
  only, and sticky sessions.
- Use `/health/live` for startup and liveness. Use `/health/ready` for traffic
  readiness after the prepared snapshot is valid.
- Keep `BUDGET_CACHE_DIR=/var/cache/sacramento-budget` on ephemeral container
  storage for the first month. Expect every cold replacement to refresh from
  ArcGIS and warm the app before scheduled demonstrations.
- Require Microsoft Entra authentication and explicit enterprise-application
  assignment to the `Budget Atlas Demo Users` group. Do not allow anonymous
  application content.
- Pull immutable image digests from a private Basic ACR using a user-assigned
  managed identity. Keep registry admin and anonymous pull disabled.
- Authenticate GitHub Actions to Azure with OIDC. Do not store a publish
  profile, Azure client secret, registry password, or personal access token.
- Retain Log Analytics data for 30 days. Do not add Application Insights,
  Azure Files, Key Vault, private networking, Front Door, Application Gateway,
  Dapr, or a dedicated workload profile during this experiment.
- Keep `BUDGET_MANUAL_REFRESH_ENABLED=0`, leave `SHINY_TESTMODE` unset, and set
  `APP_ALLOWED_HOSTS` to the exact Container Apps default hostname.
- Warm and smoke-test the app 30 minutes before a demonstration. Allow it to
  scale to zero after traffic stops.
- Tag every resource with `expiresOn=2026-09-30` and review removal, extension,
  or production redesign on that date.

The implementation plan and cost-control gates are documented in
[`docs/superpowers/plans/2026-08-09-azure-container-apps-demo.md`](superpowers/plans/2026-08-09-azure-container-apps-demo.md).
