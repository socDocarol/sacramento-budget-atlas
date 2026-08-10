# Azure Deployment Explainer Design

## Purpose

Create a standalone HTML page that explains authentication, GitHub Actions, OIDC, container images, and
Azure Container Apps to a City staff member who does not work in backend development, CI/CD, identity, or
cloud engineering.

The page must answer four questions without requiring prior technical knowledge:

1. What happens after code is changed?
2. How does GitHub receive permission to deploy without a stored Azure password?
3. How is employee sign-in different from deployment authentication?
4. Who approves each one-time setup action and each routine release?

## Chosen approach

Use a visual-first, single-page explainer with optional technical details. This combines the accessibility
of a short infographic with enough evidence for someone who wants to understand the actual controls.

Alternatives considered:

- A static document would print well but make the two authentication paths harder to distinguish.
- A highly interactive tutorial would be engaging but would add unnecessary JavaScript and maintenance.
- A slide deck would be easy to present but less convenient as a durable repository reference.

The standalone HTML page is the best balance. It will have no external assets, libraries, fonts, analytics,
network requests, or build process.

## Page structure

### 1. Plain-language summary

Open with one sentence:

> People use Microsoft Entra to enter the app; GitHub uses OIDC to update the app; the running app uses a
> separate runtime identity to retrieve its container image.

Define the three identities as named characters:

- **Employee badge:** lets an approved City employee open Budget Atlas.
- **Deployment robot:** lets an approved GitHub workflow update Azure.
- **Runtime key:** lets the running Container App pull its image from the registry.

State clearly that none of these identities is interchangeable.

### 2. Two-lane visual

Show two horizontal lanes with arrows and numbered steps.

Employee access lane:

```text
Employee browser -> Microsoft Entra sign-in -> Budget Atlas access group check -> Budget Atlas
```

Deployment lane:

```text
Developer push -> GitHub tests -> GitHub OIDC proof -> Azure deployment identity
               -> Container registry -> Container App update
```

Use distinct colors and icons for people, GitHub, identity checks, stored images, and the running app.
Every arrow must have a short verb such as “signs in,” “tests,” “proves identity,” “pushes image,” or
“updates app.”

### 3. What OIDC means

Use a badge-check metaphor:

- GitHub presents a temporary signed badge.
- Azure checks the repository, branch or environment, audience, and issuer.
- Azure grants a short-lived token to the deployment robot.
- Azure RBAC limits what that robot can change.
- No reusable Azure password is saved in GitHub.

Include a “OIDC does not” box explaining that OIDC does not give employees access to Budget Atlas and does
not automatically grant GitHub administrator access.

### 4. One-time setup versus routine deployment

Use two columns.

One-time setup includes platform approval, managed identities, role assignments, the Entra application,
access group, and protected GitHub environment. This is where elevated resource or application ownership
may be required.

Routine deployment includes pushing code, tests, security scanning, creating one immutable container image,
OIDC login, pushing that image, and updating the existing Container App. It should not require a human Azure
administrator each time.

### 5. Measure U versus Budget Atlas

Present a side-by-side comparison based on the read-only CLI evidence:

- Measure U reuses the DBA shared Container Apps environment and registry.
- Its GitHub OIDC credential trusts `nivaplei/measureu_dashboard` on `main`.
- Its deployment identity already has Contributor permissions on the shared resources.
- Its registry admin account is enabled and the app uses a registry password secret.
- Its Container Apps authentication platform is disabled.

For Budget Atlas, show the recommended shared-platform variation:

- Reuse the environment, registry, and logging.
- Use a new repository-specific deployment identity.
- Use a separate runtime identity for registry pulls.
- Enable Entra authentication and require the approved access group.
- Scale from zero to one replica.

Mark inference separately from direct evidence. The exact Measure U workflow YAML is unavailable to the
current GitHub account, so the page must not imply that its individual workflow commands were inspected.

### 6. Approval map

Show who approves each boundary:

| Action | Likely approver |
|---|---|
| Reuse shared DBA platform | Niva or DAO/DBA platform owner |
| Create deployment identity and federated credential | DBA resource Contributor |
| Assign Azure roles | DBA resource Owner, RBAC Administrator, or User Access Administrator |
| Create/configure employee login application | Application owner or Entra application administrator |
| Assign employee access group | Enterprise application owner or Entra application administrator |
| Manage group membership | Group owner |
| Approve a routine release | GitHub environment reviewer |

Explain that these are scoped roles. A Global Administrator is not expected for routine deployments.

### 7. “What happens when I press deploy?” walkthrough

Use eight numbered cards:

1. GitHub checks out the selected commit.
2. Python tests and formatting checks run.
3. Docker builds one image.
4. The image receives a security scan and software inventory.
5. GitHub requests a temporary OIDC token.
6. Azure permits the deployment robot to push the image.
7. Azure starts a new Container App revision and runs health probes.
8. Traffic moves only after the revision becomes healthy.

Include failure outcomes beside relevant cards. A failed test stops before Azure login; a failed scan stops
before upload; a failed health check leaves the prior single revision serving traffic.

### 8. Current decision and next request

End with the recommended request to Niva:

> Can Budget Atlas reuse `saccity-shared-env` and `saccitydaoregistry` with a new repository-specific GitHub
> OIDC identity? If so, can you assign its ACR and Container Apps roles, or identify the DBA RBAC owner?

## Visual and interaction design

- Use a calm City-aligned palette, high contrast, and system fonts.
- Use cards, arrows, badges, and a small legend rather than dense paragraphs.
- Provide expandable “technical detail” sections using native `<details>` elements.
- Make the complete reading order logical without CSS or JavaScript.
- Support narrow mobile screens and printing.
- Avoid animation, external icons, and decorative effects that compete with comprehension.
- Do not reproduce or alter application navigation or footer assets; this is documentation, not app UI.

## File and implementation boundaries

Create `docs/azure-deployment-explainer.html` as one self-contained HTML file with embedded CSS and no
JavaScript. The page must not contain Azure subscription IDs, tenant IDs, application client IDs,
principal IDs, access tokens, registry credentials, client secrets, or employee-specific private data.

## Verification

Before delivery:

- Validate HTML structure and inspect it in a browser at desktop and mobile widths.
- Confirm keyboard navigation and visible focus for expandable controls.
- Confirm no horizontal overflow at 390 CSS pixels.
- Confirm print preview retains reading order and does not clip diagrams.
- Scan for secrets, unresolved template markers, external URLs loaded as assets, and em dash characters.
- Cross-check every Measure U statement against the captured CLI evidence and label all inference.
- Cross-check every Budget Atlas workflow step against the committed Bicep and GitHub Actions files.
