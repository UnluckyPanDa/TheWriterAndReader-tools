"""Local web GUI command."""

from __future__ import annotations

import argparse


def _run(args: argparse.Namespace) -> int:
    from tools.web.server import serve

    serve(
        port=args.port,
        workspace=args.workspace,
        open_browser=not args.no_open,
        auth_url=args.auth_url,
        auth_anon_key=args.auth_anon_key,
        auth_required=True if args.auth_required else None,
        allowed_origin=args.allowed_origin,
    )
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the local web GUI command."""
    parser = subparsers.add_parser("web", help="Open the local TWR tools web GUI.")
    parser.add_argument("--workspace", help="Optional external workspace to load initially.")
    parser.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765).")
    parser.add_argument("--no-open", action="store_true", help="Do not open the browser automatically.")
    parser.add_argument("--auth-url", help="Supabase project URL (or set TWR_AUTH_URL).")
    parser.add_argument("--auth-anon-key", help="Supabase publishable/anon key (or set TWR_AUTH_ANON_KEY).")
    parser.add_argument("--auth-required", action="store_true", help="Require Supabase login before using tools.")
    parser.add_argument("--allowed-origin", help="Allowed hosted-site origin for browser API calls (or set TWR_ALLOWED_ORIGIN).")
    parser.set_defaults(handler=_run)


def main(argv: list[str] | None = None) -> int:
    """Run the web GUI command directly."""
    parser = argparse.ArgumentParser(description="Local TWR web GUI.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["web", *(argv or [])])
    return int(args.handler(args) or 0)
