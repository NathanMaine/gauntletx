# Threat model

**gauntletx is a LAN tool.** It is designed to run on a network you control — a laptop, a
home server, a NAS behind your own router. It is **not** a hardened public-facing service
and is not intended to become one.

This page exists so that security decisions in the code are made against a stated posture
rather than re-argued each time.

---

## What is assumed

| Assumption | Consequence |
|---|---|
| Everyone who can reach the port is trusted | No authentication, no rate limiting, no CSRF tokens |
| The network is yours | Plain HTTP is fine; no TLS termination is built in |
| The model backend is also on that network | The server makes outbound requests to it on your behalf |
| A single operator, or a small trusted team | No multi-tenancy, no per-user state, no audit trail |

The default bind is `127.0.0.1`. Reaching it from another machine is a deliberate act
(`--host 0.0.0.0`, or the container's port mapping), and that act is what places the tool
on your LAN.

## What follows from that

**Per-request overrides are allowed to change the outbound endpoint.** The config page
(issue #10) lets the browser specify which model endpoint the server should call. On a
public service this would be a server-side request forgery hole: anyone who could reach
the port could make the server fetch arbitrary URLs and read the response.

Under the posture above it is not a hole, it is the feature — pointing gauntletx at a
different box on your LAN is exactly what a self-hosted tool should let you do without
editing a `.env` and restarting a container.

The scheme is still validated (`http`/`https` only), because a typo should fail cleanly
rather than interestingly.

**No secret is stored server-side.** The container runs read-only; UI config lives in
browser localStorage. An API key entered in the UI travels per-request over LAN HTTP. The
env-var route is the recommended one for container deployment, and the config page says
so at the point of entry.

## What would have to change to expose this publicly

Not a recommendation — a list of what is deliberately absent, so nobody assumes it is
present:

- authentication and session management
- TLS
- rate limiting and request size caps beyond the input validators
- an allowlist for the outbound endpoint, replacing free-text URL entry
- CSRF protection on the POST doors
- audit logging

If you find yourself wanting these, the honest answer is that gauntletx is the wrong shape
for that deployment. Put it behind something that provides them, or keep it on the LAN.

## Practical guidance

- Keep the default `127.0.0.1` bind unless you need LAN access.
- If you expose it on the LAN, treat "who can reach this port" as the whole access control
  story, because it is.
- Do not put it on the public internet, on a shared or untrusted network, or behind a
  naive port-forward.
