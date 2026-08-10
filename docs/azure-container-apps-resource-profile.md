# Azure Container Apps resource profile

## Decision

Keep the public pilot's Container Apps allocation at **0.5 vCPU and 1 GiB**. The automated
clean-cache gate passed with substantial memory headroom. Deployment approval remains contingent on the
30-minute anonymous browser/WebSocket session in the post-deployment validation task.

## Evidence

| Field | Observation |
|---|---|
| Date | 2026-08-10 UTC |
| GitHub Actions job | [Azure resource profile (0.5 CPU / 1 GiB)](https://github.com/socDocarol/sacramento-budget-atlas/actions/runs/31350082038/job/93339104301) |
| Source commit | `3de2a2f452926a4aff24bf5dc75d9b2183e022c5` |
| Local image ID | `sha256:87c5acc8f6fa3d249e93be5d45724d935cfca28e1e304a8053cbd796c773acc6` |
| Limits | 0.5 CPU, 1 GiB memory, 1 GiB memory plus swap combined |
| Cache | New empty Docker volume mounted at `/var/cache/sacramento-budget` |
| Readiness | HTTP 200 at the 14-second sample; repository load completed in 9.48 seconds |
| Peak memory | 257.6 MiB (25.16% of 1 GiB) |
| OOM killed | No |
| Root response | HTTP 200 after readiness |

The resource-profile job itself completed successfully. Its parent workflow was later cancelled by the
branch concurrency rule when the follow-up formatting commit was pushed; that cancellation happened after
the profile job and artifact upload had completed.

## Gate evaluation

- No OOM event: pass.
- Peak below 768 MiB: pass, with 510.4 MiB of headroom to the gate.
- Ready within five minutes: pass, at 14 seconds by the five-second sampler.
- Thirty-minute anonymous browser/WebSocket session: pending until the public-pilot Container App exists;
  this is a post-deployment acceptance gate, not evidence from the short runner profile.

The retained workflow artifact contains the complete five-second memory samples, readiness response, and
container log. Generated cache data and runner logs are not committed to the repository.
