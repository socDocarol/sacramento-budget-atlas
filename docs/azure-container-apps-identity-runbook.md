# Azure Container Apps identity runbook

## Purpose and boundary

`scripts/Initialize-AzureDemoIdentity.ps1` prepares Microsoft Entra authentication for the internal Budget
Atlas demo. It configures one single-tenant application and enterprise application, requires explicit
assignment, assigns only the approved `Budget Atlas Demo Users` security group, and creates the short-lived
client secret required by Container Apps built-in authentication.

Do not grant access to all tenant users. Do not disable `appRoleAssignmentRequired`, and do not share the
Container App hostname until an assigned team member and an unassigned test user have both been tested.

## Required authority

An identity administrator must approve and execute the write operation. The signed-in Azure CLI identity
needs Microsoft Graph access sufficient to:

- read and update applications and service principals (`Application.ReadWrite.All`);
- read the approved security group (`Group.Read.All` or the tenant's approved equivalent); and
- create the group's enterprise-application assignment (`AppRoleAssignment.ReadWrite.All`).

These Graph permissions normally require tenant administrator consent and an appropriate Entra directory
role, such as Application Administrator or Cloud Application Administrator, under City policy. The owner of
`Budget Atlas Demo Users` must separately approve the team's membership before the assignment is created.

## Read-only preview

Use the `containerAppsDefaultDomain` foundation deployment output, not a hand-constructed production value:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts/Initialize-AzureDemoIdentity.ps1 `
  -ContainerAppsDefaultDomain '<foundation-default-domain>' `
  -WhatIf
```

The preview reads existing Entra objects, prints the exact callback URL and intended changes, and issues no
application, service-principal, assignment, PATCH, POST, or credential mutation. It stops if duplicate app
names exist or if the security group is absent or not security-enabled.

## Approved initialization

Run without `-WhatIf` only after the identity and group-owner approvals. Capture the returned object in
memory:

```powershell
$identityBootstrap = & powershell.exe -NoProfile -ExecutionPolicy Bypass `
  -File scripts/Initialize-AzureDemoIdentity.ps1 `
  -ContainerAppsDefaultDomain '<foundation-default-domain>'
```

`ClientSecret` is returned as a `SecureString`; the script never prints it or writes it to disk. Keep
PowerShell transcription and verbose command tracing disabled, pass the value directly to the approved
application deployment, and clear the calling variables immediately afterward. Do not paste it into chat,
email, a GitHub secret, source control, or a parameter file.

The credential is named `container-app-auth-2026-08` and expires on **2026-11-30 at 23:59:59 UTC**. The
script refuses to append another credential with the same name because Entra cannot return an existing
secret value.

## Rotation

At least two weeks before expiry:

1. Have the identity administrator append a newly named, short-lived credential with the next approved
   expiry date.
2. Update the Container App authentication secret through a secure, in-memory deployment and verify an
   assigned user's sign-in in a new private browser session.
3. Confirm an unassigned user remains denied.
4. Delete the old password credential by key ID with `az ad app credential delete`.
5. Record the new expiry in the experiment review notes without recording the secret.

Never use `az ad app credential reset` without `--append`; doing so can invalidate a currently working
deployment before the replacement is verified.

## Removal and experiment teardown

For access removal, first remove the person from `Budget Atlas Demo Users`. For full experiment teardown:

1. Remove the group app-role assignment through Microsoft Graph using its assignment object ID.
2. Delete every Budget Atlas client credential by key ID.
3. Delete the enterprise application and application registration after the Container App is removed.
4. Confirm no redirect URI, credential, group assignment, or duplicate `Sacramento Budget Atlas Demo`
   object remains.

Deletion is an explicitly approved teardown action and is not performed by the bootstrap script.
