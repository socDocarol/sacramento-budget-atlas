# Future City Gateway Contract

The pilot currently relies on network reachability and does not authenticate
users inside the application. The application ignores forwarded identity
headers.

## Required gateway behavior

- Terminate TLS before forwarding traffic to the container.
- Forward HTTP and WebSocket upgrades to the same application instance.
- Preserve the configured application base path.
- Apply sticky sessions before adding more than one application process or
  replica.
- Remove untrusted inbound identity headers before adding trusted identity
  attributes.
- Provide a documented health-check route or continue using the application
  root for container health checks.

## Future identity adapter

The Python application exposes an `AccessContextProvider` interface. A future
gateway adapter may translate verified City identity attributes into a subject,
display name, and group list. Header names, signing rules, trusted proxy ranges,
and authorization policies are intentionally not implemented until the City
gateway contract is approved.

## Cache and scaling

The pilot runs one Shiny process and uses a process-level in-memory snapshot
with a persistent Parquet fallback. Scale-out requires:

- A shared snapshot cache accessible to every replica.
- Sticky WebSocket sessions.
- Coordinated refresh behavior.
- Load validation at the intended concurrency.
