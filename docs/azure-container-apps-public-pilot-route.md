# Azure Container Apps Public Pilot Route

## Status

This document records the deployment route selected on 2026-08-09 and the implementation status after the
first bootstrap session. It is not evidence of a completed Container App deployment.

**The identity bootstrap is deployed, but no Budget Atlas Container App or image is deployed.** The bootstrap
created the two pilot-owned managed identities, the repository/environment-bound GitHub federated credential,
and the `AcrPull` and `AcrPush` assignments scoped to `saccitydaoregistry`. Azure validation and what-if showed
no modifications or deletions to shared resources. Post-deployment inventory still listed only the pre-existing
`saccityapps` and `next311` Container Apps in `DBA`.

The public-pilot Bicep, workflow, scripts, tests, and runbook now implement the route below. The remaining first
deployment requires the protected GitHub environment, a workflow-built and scanned immutable image, app
deployment preview, and the post-deployment acceptance checks.

## Branch strategy

- `feat/azure-container-apps-demo` preserves the hardened implementation. It uses dedicated demo resources
  and requires Microsoft Entra employee authentication.
- `feat/azure-container-apps-public-pilot` is the starting branch for the simpler temporary route described
  here. The next session must adapt the implementation before attempting deployment.

Keep the hardened branch available as the reference design if Budget Atlas becomes a longer-lived internal
application. Do not simplify that branch in place.

## Selected temporary architecture

Budget Atlas will be a time-limited, anonymously accessible pilot that displays data already published by
the City of Sacramento Open Data site.

```text
Public visitor
      |
      | HTTPS, no employee login
      v
Budget Atlas Container App
      |
      | runtime managed identity
      v
Shared private container registry

Developer starts deployment
      |
      v
GitHub tests, builds, inventories, and scans one Docker image
      |
      | temporary OIDC token
      v
GitHub pushes the image and updates Budget Atlas in Azure
```

The pilot will:

- Reuse the existing `saccity-shared-env` Container Apps environment in the DBA resource group.
- Run on the environment's **Consumption** workload profile, not its Flex profile.
- Reuse the existing Basic `saccitydaoregistry` registry and the shared environment logging.
- Create a Budget Atlas Container App rather than changing the Measure U Container App.
- Use the repository's existing Docker image as the portable deployment artifact.
- Allow anonymous public HTTPS access during the pilot.
- Request that cooperative search engines not index the application.
- Scale from zero to one replica.
- Keep GitHub Actions OIDC for automated deployment.
- Use a separate runtime managed identity to pull the private container image.
- Retain immutable image digests, tests, software inventory, vulnerability scanning, health probes, and
  single-revision traffic protection.

The pilot will not create a dedicated Container Apps environment, registry, Log Analytics workspace, or
employee sign-in application.

## Why this route was selected

- The source data is already publicly available through the City Open Data site.
- The application is experimental and is expected to receive little traffic during its first month.
- Reusing the DBA platform avoids unnecessary fixed infrastructure and duplicates.
- Anonymous access avoids Entra application registration, employee-group assignment, login testing, and
  authentication-secret rotation for a short-lived experiment.
- GitHub deployment keeps packaging work with the repository instead of asking the DBA platform owner to
  build and release the application manually.
- OIDC avoids storing a reusable Azure deployment password in GitHub.

Search exclusion is not access control. The URL remains publicly reachable by anyone who obtains or
discovers it. This route is appropriate only while the application contains public data, has no write or
administrative operations, and remains explicitly time limited.

## Authentication boundaries

Three separate questions must not be confused:

| Boundary | Pilot decision | Purpose |
|---|---|---|
| Visitor to Budget Atlas | Anonymous HTTPS | Allows the public to view already-public data |
| GitHub Actions to Azure | OIDC and scoped Azure RBAC | Allows the approved workflow to deploy without an Azure password |
| Container App to registry | Runtime managed identity | Allows the running app to pull its private image |

### Plain explanation of OIDC

OIDC is a temporary deployment badge. GitHub presents a signed statement identifying the approved Budget
Atlas repository and deployment environment. Azure verifies that statement and issues a short-lived token.
Azure RBAC limits that token to the approved deployment operations. The token expires after the workflow.

OIDC does not control public access to Budget Atlas, does not add code to the Docker image, does not run
while visitors use the app, and does not grant GitHub unrestricted Azure administration.

## Deployment pipeline

The intended routine deployment is:

1. A maintainer starts the protected GitHub deployment workflow.
2. GitHub checks out the selected commit.
3. Frozen Python dependencies, Ruff checks, and unit tests run.
4. Docker builds one image identified by the source commit.
5. GitHub generates the SPDX software bill of materials.
6. Trivy scans that exact image for high and critical vulnerabilities.
7. GitHub presents its OIDC proof and receives a temporary Azure token.
8. GitHub pushes the scanned image to `saccitydaoregistry` and resolves its immutable digest.
9. GitHub updates only the Budget Atlas Container App image and revision suffix.
10. Azure starts the revision and evaluates startup, liveness, and readiness probes.
11. The new revision receives traffic only after it is healthy. A failed or timed-out revision leaves the
    prior single revision serving traffic.

Niva or another DBA platform owner should not need to package the application. If the deployment is
blocked, request only the exact missing permission or role assignment.

## Cost position

The read-only Azure CLI review confirmed:

- `saccity-shared-env` already exists and offers Consumption and Flex workload profiles.
- `saccitydaoregistry` already exists on the Basic tier.
- The public pilot will use Consumption so it can scale to zero.

As of this decision, Azure Container Apps provides the following free monthly grants per subscription:

- 180,000 vCPU-seconds
- 360,000 GiB-seconds
- 2 million external HTTP requests

The grants are shared across the DBA subscription. Measure U and other workloads may consume some or all of
them, so the pilot must not be described as guaranteed free.

At the proposed 0.5 vCPU and 1 GiB allocation, current West US 2 retail consumption rates are approximately
USD 0.0756 per active hour before free grants. That is approximately USD 0.76 for 10 active hours, USD 3.02
for 40 active hours, or USD 7.56 for 100 active hours. A revision at zero replicas incurs no Container Apps
resource-consumption charge.

OIDC and Azure managed identities have no additional licensing charge. The existing Basic registry includes
10 GiB of storage in its current tier charge, so Budget Atlas has no expected marginal registry charge while
the shared registry remains within that allowance. Log ingestion, network egress, storage overage, or usage
beyond the subscription grants can still produce small charges.

## Public-pilot safeguards

The implementation must retain these controls:

- HTTPS only.
- Exact allowed host configuration.
- `minReplicas=0` and `maxReplicas=1`.
- Consumption workload profile.
- Single revision mode and sticky sessions.
- `/health/live` startup and liveness probes.
- `/health/ready` traffic-readiness probe.
- Immutable image digest deployment.
- Private registry pull through managed identity.
- `BUDGET_MANUAL_REFRESH_ENABLED=0`.
- No administrative or write operations exposed to visitors.
- A `robots.txt` exclusion and `X-Robots-Tag: noindex` response header, understood as indexing guidance rather
  than security.
- A clear expiration or review tag and post-pilot removal decision.

Do not publish the pilot URL in repository documentation. Operational staff may share it directly with the
small evaluation group.

## Next-session implementation scope

Before any Azure write, the next session must:

1. Confirm it is working on `feat/azure-container-apps-public-pilot`.
2. Preserve the hardened branch without rewriting its history.
3. Update the Bicep deployment to reference the existing DBA environment, registry, and logging instead of
   creating dedicated platform resources.
4. Remove the Container Apps employee Entra authentication resource and its client ID, client secret, access
   group, and redirect requirements from the public-pilot branch.
5. Keep a repository-specific GitHub OIDC identity and federated credential.
6. Keep a separate runtime managed identity and grant only the private-registry pull permission it needs.
7. Update the GitHub workflow's registry, resource group, Container App, and deployment-environment values.
8. Add the no-indexing controls.
9. Update or replace tests and runbooks that still assert the dedicated authenticated topology.
10. Run formatting, tests, Docker build, image scanning, Bicep validation, and Azure deployment preview.
11. Inspect the preview to ensure it creates only Budget Atlas-specific resources and does not modify Measure
    U, the shared environment, the shared registry configuration, or the shared logging workspace.
12. Attempt the bootstrap using the current user's Azure permissions.

If Azure denies an operation, stop expanding scope and capture the exact operation, resource scope, and role
required. Send that narrow request to Niva or the identified DBA RBAC owner. Do not ask them to package or
deploy the application.

## Likely approval request if blocked

> Budget Atlas is ready to deploy through GitHub Actions into the existing DBA Container Apps platform.
> Azure denied the attached operation at the listed resource scope. Could you grant the specified role or
> perform this one role assignment? The repository workflow will build, scan, and deploy the Docker image;
> no application packaging is required from you.

## Deployment completion criteria

The pilot is complete only when:

- GitHub authenticates through OIDC without a reusable Azure credential.
- The exact tested and scanned image digest is running.
- Anonymous HTTPS access succeeds.
- Indexing-exclusion responses are present.
- The app is limited to one replica and returns to zero after inactivity.
- Health probes and a real Shiny WebSocket session succeed.
- Measure U and shared platform settings remain unchanged.
- Azure cost monitoring shows no unexpected resource or workload-profile charges.
