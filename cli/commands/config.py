"""Config CLI commands."""

from __future__ import annotations

import argparse


def _path(_args: argparse.Namespace) -> int:
    from shared.lib.config_loader import get_default_config_path

    print(get_default_config_path())
    return 0


def _validate(args: argparse.Namespace) -> int:
    from shared.lib.config_loader import load_config, validate_config

    config = load_config(args.config)
    messages = validate_config(config)
    if messages:
        for message in messages:
            print(f"error: {message}")
        return 1
    print("config ok")
    return 0


def _export(args: argparse.Namespace) -> int:
    from shared.lib.config_loader import export_config, load_config

    config = load_config(args.config)
    print(export_config(config, args.output, args.mode))
    return 0


def _import(args: argparse.Namespace) -> int:
    from shared.lib.config_loader import import_config

    print(import_config(args.input, args.target))
    return 0


def register(subparsers: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register config subcommands."""
    parser = subparsers.add_parser("config", help="Inspect and manage tool config.")
    config_subparsers = parser.add_subparsers(dest="config_command", required=True)

    path_parser = config_subparsers.add_parser("path", help="Print the default config path.")
    path_parser.set_defaults(handler=_path)

    validate_parser = config_subparsers.add_parser("validate", help="Validate config shape.")
    validate_parser.add_argument("--config", help="Optional config path.")
    validate_parser.set_defaults(handler=_validate)

    export_parser = config_subparsers.add_parser("export", help="Export redacted config.")
    export_parser.add_argument("output")
    export_parser.add_argument("--config", help="Optional config path.")
    export_parser.add_argument("--mode", default="no-secrets", choices=["no-secrets", "full-with-secrets"])
    export_parser.set_defaults(handler=_export)

    import_parser = config_subparsers.add_parser("import", help="Import config into the external path.")
    import_parser.add_argument("input")
    import_parser.add_argument("--target")
    import_parser.set_defaults(handler=_import)


def main(argv: list[str] | None = None) -> int:
    """Run config commands directly."""
    parser = argparse.ArgumentParser(description="Config commands.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    register(subparsers)
    args = parser.parse_args(["config", *(argv or [])])
    return int(args.handler(args) or 0)
