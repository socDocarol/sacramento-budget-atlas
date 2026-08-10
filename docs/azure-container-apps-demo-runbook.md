# Azure Container Apps demo operations runbook

## Scope

This runbook covers warm-up, authenticated acceptance, pre-demo validation, rollback, and approved
teardown for the internal Sacramento Budget Atlas experiment. It assumes the operator is signed in to the
`Microsoft Azure Enterprise - APPS` subscription and has read and Container Apps operating permissions on
`rg-sac-budget-atlas-demo-wus2`.

The public hostname is not an anonymous application endpoint. An unauthenticated request must redirect to
Microsoft Entra, and only assigned members of `Budget Atlas Demo Users` may complete sign-in.

## First deployment and every new revision

Each revision needs one recorded 30-minute browser acceptance before it can be used for a demonstration:

1. Run the warm-up script.
2. Sign in through a private browser window as an assigned group member.
3. Keep the same browser session open for at least 30 minutes. Exercise Overview and Explorer filters,
   navigate between charts, and confirm updates continue without a disconnect or WebSocket error.
4. Record the active revision name, start and finish times, operator, and pass/fail result in the demo change
   record. Do not record tokens or cookies.
5. Run the smoke test with the recorded revision and duration:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts/Test-AzureDemoDeployment.ps1 `
  -BrowserSessionRevisionName 'ca-sac-budget-atlas-demo--<revision-suffix>' `
  -BrowserSessionDurationMinutes 30 `
  -BrowserSessionPassed
```

The smoke test also verifies the Entra redirect, HTTPS enforcement, immutable digest, single revision,
sticky sessions, 0-1 scale, UID 10001, internal health endpoints, exact allowed host, and absence of
`SHINY_TESTMODE`. Browser evidence must name the currently active revision; evidence from an older revision
does not pass.

## Demonstration timeline

The 30-minute browser acceptance above must already exist for the active revision.

```text
T-30 minutes: run Warm-AzureDemo.ps1
T-20 minutes: run Test-AzureDemoDeployment.ps1 with the active revision's recorded browser evidence
T-10 minutes: sign in as a member of Budget Atlas Demo Users and exercise filters
T-0: begin demonstration
T+0: take no action; Container Apps scales to zero after traffic and cooldown cease
```

Warm the application with:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/Warm-AzureDemo.ps1
```

The script resolves the Azure-managed FQDN, sends the HTTPS request that starts scale-up, waits for a
replica, and polls `/health/ready` from inside that replica for up to ten minutes. An Entra redirect from the
public request is expected. The script exits nonzero if internal readiness never returns HTTP 200.

## Rollback

Rollback means deploying the last known-good immutable digest as a new single revision. Never roll back by
retagging an image, using `latest`, or enabling multiple revision mode.

1. Obtain the exact `sacbudgetatlasdemo.azurecr.io/budget-atlas@sha256:<64 lowercase hex>` value from the
   successful deployment summary and cross-check it against ACR.
2. Confirm `activeRevisionsMode` is `Single` and capture the current active digest for the incident record.
3. Choose a new unique revision suffix, such as `rb-` followed by a 12-digit UTC timestamp.
4. Run the update:

```powershell
az containerapp update `
  --name ca-sac-budget-atlas-demo `
  --resource-group rg-sac-budget-atlas-demo-wus2 `
  --image 'sacbudgetatlasdemo.azurecr.io/budget-atlas@sha256:<known-good-digest>' `
  --revision-suffix 'rb-<12-digit-utc-timestamp>'
```

5. Wait for the new revision to report `Provisioned` and `Healthy`. In single revision mode, the prior
   revision retains traffic if the replacement fails its internal probes.
6. Warm and run the full smoke test against the rollback revision. Record the old digest, restored digest,
   new revision, reason, operator, and timestamps.

Do not delete the failed image or revision until the incident review has preserved the evidence.

## Cost and inactivity checks

- Leave minimum replicas at zero and maximum replicas at one.
- Do not add storage, a VNet, private endpoints, dedicated workload profiles, or another telemetry service.
- Review ACR storage and 30-day Log Analytics ingestion weekly during the experiment.
- Confirm the `$15` advisory budget separately with a Cost Management Contributor.
- After a demonstration, send no keep-alive traffic. Confirm the replica count returns to zero.

## Approved teardown

Teardown is destructive and requires explicit approval. After approval:

1. Export the final cost, deployment digest, and acceptance evidence without exporting credentials.
2. Remove the Entra group assignment and client credentials using the identity runbook.
3. Delete the Container App, then the dedicated resource group
   `rg-sac-budget-atlas-demo-wus2` after confirming it contains only experiment resources.
4. Remove the GitHub `azure-demo` environment identifiers and OIDC federated credential.
5. Remove the advisory budget through a Cost Management Contributor.
6. Confirm no ACR repository, managed identity, Entra object, group assignment, or DNS hostname remains.

Do not perform these deletion steps as part of routine scale-to-zero operations.
