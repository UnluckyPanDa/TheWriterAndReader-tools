# External Web Access and Login

The TWR web control room stays local-first: the Python server owns access to
the external story workspace, and the browser is only a client. Supabase Auth
provides the account login. Tailscale provides the HTTPS path to the local
server.

## 1. Create the free login provider

Create a Supabase project, enable email/password authentication, and copy the
project URL and its publishable/anon key. The anon key is intended for browser
use; never place a Supabase service-role key in this repository or in a browser
request.

Set the values in the shell that starts TWR:

```bash
export TWR_AUTH_URL="https://YOUR_PROJECT.supabase.co"
export TWR_AUTH_ANON_KEY="YOUR_SUPABASE_PUBLISHABLE_KEY"
export TWR_AUTH_REQUIRED=1
export TWR_ALLOWED_ORIGIN="https://YOUR_SITE_HOSTNAME"
```

Then start the authenticated server:

```bash
twr web --workspace /path/to/story-workspace --auth-required --allowed-origin "$TWR_ALLOWED_ORIGIN" --no-open
```

The local server remains bound to `127.0.0.1`. Every tool request must carry a
valid Supabase bearer token. When auth is disabled, the existing per-process
local session token remains available for local-only use.

`TWR_ALLOWED_ORIGIN` must exactly match the hosted site's origin, including the
scheme and port when one is present. It enables browser CORS for the hosted
portal while keeping other origins out.

## 2. Share it privately across your tailnet

With Tailscale running on the same Mac, force the macOS app binary into CLI
mode, then share the loopback service only with devices in your tailnet:

```bash
export TAILSCALE_BE_CLI=1
tailscale serve --bg 8765
tailscale serve status
```

The `TAILSCALE_BE_CLI` setting is needed when the macOS app's bundled binary
would otherwise launch its windowed interface from a shell.

Open the HTTPS URL shown by Tailscale from another tailnet device, then sign in
to the TWR control room. Tailscale ACLs and the TWR Supabase login are both
required.

## 3. Share it publicly when explicitly needed

For internet access, use Tailscale Funnel instead of opening the router port:

```bash
export TAILSCALE_BE_CLI=1
tailscale funnel --bg 8765
tailscale funnel status
```

This creates a public HTTPS endpoint. Keep `TWR_AUTH_REQUIRED=1`, restrict
Supabase sign-ups if the project is private, and turn Funnel off when finished:

```bash
tailscale funnel reset
```

## 4. Connect the hosted gateway

The `site/` directory is the hosted portal. Configure these public browser
variables in the site's build environment:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://YOUR_PROJECT.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=YOUR_SUPABASE_PUBLISHABLE_KEY
```

After the site has a stable HTTPS hostname, set that exact origin as
`TWR_ALLOWED_ORIGIN` on the local server. The portal then signs users in with
Supabase and forwards only the allowlisted TWR actions to the HTTPS endpoint
you enter. The local server still owns the workspace files and tool process.

## Security boundaries

- Keep the TWR server loopback-only.
- Use a Supabase publishable/anon key only; never use a service-role key in the
  site or local server command line.
- Keep the fixed action allowlist. The web API must not become a shell endpoint.
- Use Tailscale Serve for private access. Treat Funnel as public internet
  exposure and require account login before tool access.
- Do not place story workspaces, canon, or secrets in the hosted site source.
