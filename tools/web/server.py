"""Serve a token-protected local web GUI for invoking TWR tools."""

from __future__ import annotations

import html
import json
import os
import secrets
import subprocess
import sys
import threading
import webbrowser
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

import requests

from shared.lib.workspace_loader import list_series, list_stories, resolve_story_path, validate_workspace_path


STATIC_ROOT = Path(__file__).resolve().parent / "static"
MAX_REQUEST_BYTES = 1_000_000


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _auth_settings(
    auth_url: str | None,
    auth_anon_key: str | None,
    auth_required: bool | None,
) -> tuple[str, str, bool]:
    provider_url = (auth_url or os.environ.get("TWR_AUTH_URL", "")).strip().rstrip("/")
    anon_key = (auth_anon_key or os.environ.get("TWR_AUTH_ANON_KEY", "")).strip()
    required = _env_flag("TWR_AUTH_REQUIRED") if auth_required is None else auth_required
    if required and (not provider_url or not anon_key):
        raise ValueError("TWR_AUTH_URL and TWR_AUTH_ANON_KEY are required when TWR_AUTH_REQUIRED is enabled")
    return provider_url, anon_key, required


def _allowed_origin(origin: str | None) -> str:
    return (origin or os.environ.get("TWR_ALLOWED_ORIGIN", "")).strip().rstrip("/")


def _supabase_user(provider_url: str, anon_key: str, access_token: str) -> dict[str, Any] | None:
    """Validate a Supabase access token without storing provider secrets locally."""
    try:
        response = requests.get(
            f"{provider_url}/auth/v1/user",
            headers={"apikey": anon_key, "Authorization": f"Bearer {access_token}"},
            timeout=3,
        )
    except requests.RequestException:
        return None
    if not response.ok:
        return None
    try:
        user = response.json()
    except ValueError:
        return None
    return user if isinstance(user, dict) else None


class FolderPickerCancelled(Exception):
    """Raised when the native folder picker is dismissed."""


def choose_workspace_folder() -> str:
    """Open the local platform folder picker and return a selected path."""
    if sys.platform != "darwin":
        raise RuntimeError("The native workspace folder picker is available on macOS only")
    result = subprocess.run(
        [
            "/usr/bin/osascript",
            "-e",
            'POSIX path of (choose folder with prompt "Choose a TWR story workspace")',
        ],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode != 0:
        raise FolderPickerCancelled()
    path = result.stdout.strip()
    if not path:
        raise FolderPickerCancelled()
    return path


class ToolDispatcher:
    """Expose a fixed set of tool operations to the local HTTP layer."""

    def workspace_summary(self, workspace: str) -> dict[str, Any]:
        root = Path(workspace).expanduser().resolve(strict=False)
        issues = validate_workspace_path(root)
        if issues:
            raise ValueError("Invalid workspace:\n" + "\n".join(issues))

        stories = []
        for story_id in list_stories(root):
            from shared.lib.story_loader import load_story_yaml

            story_path = resolve_story_path(root, story_id)
            story_yaml = load_story_yaml(story_path)
            stories.append(
                {
                    "id": story_id,
                    "title": str(story_yaml.get("title") or story_id),
                    "has_relation_graph": (story_path / "canon" / "relationship_graph.yaml").exists(),
                    "has_relation_plot": (story_path / "build" / "relation-plot" / "index.html").exists(),
                }
            )
        return {
            "path": str(root),
            "stories": stories,
            "series": [{"id": series_id} for series_id in list_series(root)],
        }

    def run(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        handlers = {
            "doctor": self._doctor,
            "config_path": self._config_path,
            "config_validate": self._config_validate,
            "config_export": self._config_export,
            "config_import": self._config_import,
            "workspace_init": self._workspace_init,
            "story_add": self._story_add,
            "series_add": self._series_add,
            "write_pack": self._write_pack,
            "write_draft": self._write_draft,
            "review_pack": self._review_pack,
            "review_run": self._review_run,
            "publish_pack": self._publish_pack,
            "relation_plot_init": self._relation_plot_init,
            "relation_plot_build": self._relation_plot_build,
            "storyline_save": self._storyline_save,
            "relationship_graph_save": self._relationship_graph_save,
            "review_comment_add": self._review_comment_add,
        }
        handler = handlers.get(action)
        if handler is None:
            raise ValueError(f"Unsupported web action: {action}")
        result = handler(payload)
        workspace = self._optional_text(payload, "workspace")
        if workspace and not validate_workspace_path(workspace):
            result["workspace"] = self.workspace_summary(workspace)
        return result

    def _doctor(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.config_loader import load_config, validate_config
        from shared.lib.path_rules import assert_workspace_has_no_tool_code

        issues = validate_config(load_config(self._optional_text(payload, "config")))
        workspace = self._optional_text(payload, "workspace")
        if workspace:
            issues.extend(validate_workspace_path(workspace))
            issues.extend(assert_workspace_has_no_tool_code(workspace))
        return {"ok": not issues, "output": "doctor ok" if not issues else "\n".join(issues)}

    def _config_validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.config_loader import load_config, validate_config

        issues = validate_config(load_config(self._optional_text(payload, "config")))
        return {"ok": not issues, "output": "config ok" if not issues else "\n".join(issues)}

    def _config_path(self, _payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.config_loader import get_default_config_path

        return {"ok": True, "output": str(get_default_config_path())}

    def _config_export(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.config_loader import export_config, load_config

        mode = self._optional_text(payload, "mode") or "no-secrets"
        if mode not in {"no-secrets", "full-with-secrets"}:
            raise ValueError("Unsupported config export mode")
        path = export_config(
            load_config(self._optional_text(payload, "config")),
            self._required_text(payload, "output"),
            mode,
        )
        return {"ok": True, "output": str(path)}

    def _config_import(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.config_loader import import_config

        path = import_config(
            self._required_text(payload, "input"),
            self._optional_text(payload, "target"),
        )
        return {"ok": True, "output": str(path)}

    def _workspace_init(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.wizard.scaffold import init_workspace

        path = init_workspace(self._required_text(payload, "workspace"), self._required_text(payload, "workspace_id"))
        return {"ok": True, "output": str(path)}

    def _story_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.wizard.scaffold import add_story

        path = add_story(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_text(payload, "title"),
            self._required_text(payload, "language"),
        )
        return {"ok": True, "output": str(path)}

    def _series_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.wizard.scaffold import add_series

        path = add_series(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "series"),
            self._required_text(payload, "title"),
        )
        return {"ok": True, "output": str(path)}

    def _write_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.writing.build_write_pack import build_write_pack

        path = build_write_pack(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_int(payload, "chapter"),
        )
        return {"ok": True, "output": str(path)}

    def _write_draft(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.writing.generate_draft import generate_draft

        path = generate_draft(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_int(payload, "chapter"),
            self._optional_text(payload, "config"),
        )
        return {"ok": True, "output": str(path)}

    def _review_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.review.build_review_pack import build_review_pack

        path = build_review_pack(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_int(payload, "chapter"),
        )
        return {"ok": True, "output": str(path)}

    def _review_run(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.review.run_review import run_review

        outputs = run_review(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_int(payload, "chapter"),
            self._optional_text(payload, "config"),
        )
        return {"ok": True, "output": {key: str(value) for key, value in outputs.items()}}

    def _publish_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.publish.build_publish_pack import build_publish_pack

        path = build_publish_pack(
            self._required_text(payload, "workspace"),
            self._required_text(payload, "story"),
            self._required_int(payload, "chapter"),
        )
        return {"ok": True, "output": str(path)}

    def _relation_plot_init(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.wizard.relation_plot import init_relation_plot

        path = init_relation_plot(
            self._required_text(payload, "workspace"), self._required_text(payload, "story")
        )
        return {"ok": True, "output": str(path)}

    def _relation_plot_build(self, payload: dict[str, Any]) -> dict[str, Any]:
        from tools.wizard.relation_plot import build_relation_plot

        workspace = self._required_text(payload, "workspace")
        story = self._required_text(payload, "story")
        path = build_relation_plot(workspace, story)
        preview = f"/relation-plot?workspace={quote(workspace)}&story={quote(story)}"
        return {"ok": True, "output": str(path), "preview": preview}

    def _storyline_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.safe_write import safe_write_file

        story_path = resolve_story_path(self._required_text(payload, "workspace"), self._required_text(payload, "story"))
        filename = self._required_text(payload, "file")
        allowed = {"master_outline.md", "part_outline.md", "chapter_plan.md", "reveal_lock.md"}
        if filename not in allowed:
            raise ValueError(f"Unsupported storyline file: {filename}")
        content = self._required_text(payload, "content")
        target = story_path / "storyline" / filename
        path = safe_write_file(target, content.rstrip() + "\n", story_path)
        return {"ok": True, "output": str(path)}

    def _relationship_graph_save(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.relationship_graph import validate_relationship_graph
        from shared.lib.safe_write import safe_write_file
        from shared.lib.yaml_utils import load_yaml_text

        story_path = resolve_story_path(self._required_text(payload, "workspace"), self._required_text(payload, "story"))
        content = self._required_text(payload, "content")
        data = load_yaml_text(content) or {}
        if not isinstance(data, dict):
            raise ValueError("Relationship graph must contain a YAML mapping")
        validate_relationship_graph(data)
        target = story_path / "canon" / "relationship_graph.yaml"
        path = safe_write_file(target, content.rstrip() + "\n", story_path)
        return {"ok": True, "output": str(path)}

    def _review_comment_add(self, payload: dict[str, Any]) -> dict[str, Any]:
        from shared.lib.safe_write import safe_write_file

        story_path = resolve_story_path(self._required_text(payload, "workspace"), self._required_text(payload, "story"))
        chapter = self._required_int(payload, "chapter")
        comment = self._required_text(payload, "comment")
        author = self._optional_text(payload, "author") or "User"
        location = self._optional_text(payload, "location") or "General"
        target = story_path / "reviews" / f"chapter_{chapter:03d}" / "user_comments.md"
        previous = target.read_text(encoding="utf-8") if target.exists() else "# User Review Comments\n"
        entry = (
            f"\n## {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')} — {author}\n"
            f"- Location: {location}\n\n{comment}\n"
        )
        path = safe_write_file(target, previous.rstrip() + "\n" + entry, story_path)
        return {"ok": True, "output": str(path)}

    def reader(self, workspace: str, story: str, chapter: int = 1, wiki: str | None = None) -> dict[str, Any]:
        """Load a story chapter and allowlisted wiki pages for the reader view."""
        story_path = resolve_story_path(workspace, story)
        from shared.lib.story_loader import load_story_yaml

        story_yaml = load_story_yaml(story_path)
        wiki_entries = self._wiki_entries(story_path)
        selected_wiki = next((item for item in wiki_entries if item["key"] == wiki), None) if wiki else None
        chapters = self._reader_chapters(story_path)
        selected = next((item for item in chapters if item["number"] == chapter), None)
        return {
            "ok": True,
            "story": {"id": story, "title": str(story_yaml.get("title") or story)},
            "chapters": chapters,
            "chapter": selected or {"number": chapter, "source": "missing", "content": ""},
            "wiki": wiki_entries,
            "wiki_page": selected_wiki,
        }

    @staticmethod
    def _reader_chapters(story_path: Path) -> list[dict[str, Any]]:
        chapters: dict[int, dict[str, Any]] = {}
        for directory, source in (("chapters", "accepted"), ("drafts", "draft")):
            for path in sorted((story_path / directory).glob("chapter_*.md")):
                try:
                    number = int(path.stem.split("_")[-1])
                except ValueError:
                    continue
                if source == "accepted" or number not in chapters:
                    chapters[number] = {"number": number, "source": source, "content": path.read_text(encoding="utf-8")}
        return [chapters[number] for number in sorted(chapters)]

    @staticmethod
    def _wiki_entries(story_path: Path) -> list[dict[str, str]]:
        candidates = [
            ("canon", "Canon", "canon/canon.md"),
            ("characters", "Characters", "canon/characters.md"),
            ("relationships", "Relationships and names", "canon/relationships_and_names.md"),
            ("relationship_graph", "Relationship graph", "canon/relationship_graph.yaml"),
            ("locations", "Locations and objects", "canon/locations_objects.md"),
            ("hidden_truth", "Hidden truth", "canon/hidden_truth.md"),
            ("visual_bible", "Visual bible", "canon/visual_bible.md"),
            ("master_outline", "Master outline", "storyline/master_outline.md"),
            ("part_outline", "Part outline", "storyline/part_outline.md"),
            ("chapter_plan", "Chapter plan", "storyline/chapter_plan.md"),
            ("reveal_lock", "Reveal lock", "storyline/reveal_lock.md"),
            ("writer", "Writer profile", "writer/writer.md"),
        ]
        entries = []
        for key, title, relative in candidates:
            path = story_path / relative
            if path.exists():
                entries.append({"key": key, "title": title, "path": relative, "content": path.read_text(encoding="utf-8")})
        return entries

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str) -> str:
        value = payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Required field is missing: {key}")
        return value.strip()

    @staticmethod
    def _optional_text(payload: dict[str, Any], key: str) -> str | None:
        value = payload.get(key)
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _required_int(payload: dict[str, Any], key: str) -> int:
        value = payload.get(key)
        try:
            number = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Required integer field is invalid: {key}") from exc
        if number < 1:
            raise ValueError(f"Required integer field must be positive: {key}")
        return number


def create_server(
    port: int = 8765,
    workspace: str | None = None,
    token: str | None = None,
    auth_url: str | None = None,
    auth_anon_key: str | None = None,
    auth_required: bool | None = None,
    allowed_origin: str | None = None,
) -> ThreadingHTTPServer:
    """Create a loopback-only server suitable for the CLI and focused tests."""
    provider_url, anon_key, require_auth = _auth_settings(auth_url, auth_anon_key, auth_required)
    cors_origin = _allowed_origin(allowed_origin)
    app_token = token or secrets.token_urlsafe(24)
    dispatcher = ToolDispatcher()
    handler = _handler_factory(dispatcher, app_token, workspace or "", provider_url, anon_key, require_auth, cors_origin)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    server.twr_token = app_token  # type: ignore[attr-defined]
    server.twr_auth_required = require_auth  # type: ignore[attr-defined]
    server.twr_allowed_origin = cors_origin  # type: ignore[attr-defined]
    return server


def serve(
    port: int = 8765,
    workspace: str | None = None,
    open_browser: bool = True,
    auth_url: str | None = None,
    auth_anon_key: str | None = None,
    auth_required: bool | None = None,
    allowed_origin: str | None = None,
) -> None:
    """Run the local web GUI until interrupted."""
    server = create_server(
        port=port,
        workspace=workspace,
        auth_url=auth_url,
        auth_anon_key=auth_anon_key,
        auth_required=auth_required,
        allowed_origin=allowed_origin,
    )
    actual_port = server.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"
    print(f"TWR web GUI: {url}")
    if open_browser:
        threading.Timer(0.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nTWR web GUI stopped")
    finally:
        server.server_close()


def _handler_factory(
    dispatcher: ToolDispatcher,
    token: str,
    default_workspace: str,
    auth_url: str,
    auth_anon_key: str,
    auth_required: bool,
    allowed_origin: str,
) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "TWRWeb/1"

        def do_OPTIONS(self) -> None:  # noqa: N802
            if not self._cors_allowed():
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Origin is not allowed"})
                return
            self.send_response(HTTPStatus.NO_CONTENT)
            self._cors_headers()
            self.end_headers()

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/health":
                self._json(HTTPStatus.OK, {"ok": True})
                return
            if parsed.path == "/api/settings":
                if not self._authorized(parsed):
                    return
                from shared.lib.user_settings import load_user_settings

                self._run_json(load_user_settings)
                return
            if parsed.path == "/api/auth/me":
                if not self._authorized(parsed):
                    return
                self._json(HTTPStatus.OK, {"ok": True, "user": getattr(self, "auth_user", None)})
                return
            if parsed.path == "/":
                source = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")
                source = source.replace("__TWR_TOKEN__", "" if auth_required else html.escape(token, quote=True))
                source = source.replace("__TWR_WORKSPACE__", html.escape(default_workspace, quote=True))
                source = source.replace("__TWR_AUTH_URL__", html.escape(auth_url, quote=True))
                source = source.replace("__TWR_AUTH_ANON_KEY__", html.escape(auth_anon_key, quote=True))
                source = source.replace("__TWR_AUTH_REQUIRED__", "true" if auth_required else "false")
                self._text(HTTPStatus.OK, source, "text/html; charset=utf-8")
                return
            if parsed.path in {"/app.js", "/styles.css"}:
                content_type = "text/javascript; charset=utf-8" if parsed.path.endswith(".js") else "text/css; charset=utf-8"
                self._text(HTTPStatus.OK, (STATIC_ROOT / parsed.path[1:]).read_text(encoding="utf-8"), content_type)
                return
            if parsed.path == "/api/workspace":
                if not self._authorized(parsed):
                    return
                path = parse_qs(parsed.query).get("path", [""])[0]
                self._run_json(lambda: dispatcher.workspace_summary(path))
                return
            if parsed.path == "/api/reader":
                if not self._authorized(parsed):
                    return
                query = parse_qs(parsed.query)
                workspace = query.get("workspace", [""])[0]
                story = query.get("story", [""])[0]
                try:
                    chapter = int(query.get("chapter", ["1"])[0])
                except ValueError:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": "Chapter must be an integer"})
                    return
                wiki = query.get("wiki", [None])[0]
                self._run_json(lambda: dispatcher.reader(workspace, story, chapter, wiki))
                return
            if parsed.path == "/relation-plot":
                if not self._authorized(parsed):
                    return
                query = parse_qs(parsed.query)
                self._serve_relation_plot(query.get("workspace", [""])[0], query.get("story", [""])[0])
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/api/pick-folder":
                if not self._authorized(parsed):
                    return
                try:
                    self._json(HTTPStatus.OK, {"ok": True, "path": choose_workspace_folder()})
                except FolderPickerCancelled:
                    self._json(HTTPStatus.OK, {"ok": True, "cancelled": True})
                except Exception as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if parsed.path == "/api/settings":
                if not self._authorized(parsed):
                    return
                try:
                    from shared.lib.user_settings import save_user_settings

                    settings = save_user_settings(self._read_payload())
                    self._json(HTTPStatus.OK, {"ok": True, **settings})
                except Exception as exc:
                    self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})
                return
            if parsed.path != "/api/action":
                self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "Not found"})
                return
            if not self._authorized(parsed):
                return
            try:
                payload = self._read_payload()
                action = payload.pop("action", None)
                if not isinstance(action, str):
                    raise ValueError("Action is required")
                self._json(HTTPStatus.OK, dispatcher.run(action, payload))
            except Exception as exc:  # local UI must surface actionable tool failures
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def _authorized(self, parsed: Any) -> bool:
            query_token = parse_qs(parsed.query).get("token", [None])[0]
            if auth_required:
                authorization = self.headers.get("Authorization", "")
                supplied = authorization.removeprefix("Bearer ").strip() if authorization.startswith("Bearer ") else ""
                user = _supabase_user(auth_url, auth_anon_key, supplied) if supplied else None
                if user is None:
                    self._json(HTTPStatus.UNAUTHORIZED, {"ok": False, "error": "Login required"})
                    return False
                self.auth_user = user
                return True
            supplied = self.headers.get("X-TWR-Token") or query_token
            if not supplied or not secrets.compare_digest(supplied, token):
                self._json(HTTPStatus.FORBIDDEN, {"ok": False, "error": "Invalid local session token"})
                return False
            return True

        def _cors_allowed(self) -> bool:
            origin = self.headers.get("Origin", "").rstrip("/")
            return not origin or (bool(allowed_origin) and secrets.compare_digest(origin, allowed_origin))

        def _read_payload(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > MAX_REQUEST_BYTES:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be an object")
            return payload

        def _serve_relation_plot(self, workspace: str, story: str) -> None:
            try:
                story_path = resolve_story_path(workspace, story)
                plot_path = story_path / "build" / "relation-plot" / "index.html"
                if not plot_path.exists():
                    raise FileNotFoundError("Build the relationship plot before opening it")
                self._text(HTTPStatus.OK, plot_path.read_text(encoding="utf-8"), "text/html; charset=utf-8", viewer=True)
            except Exception as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def _run_json(self, operation: Any) -> None:
            try:
                self._json(HTTPStatus.OK, operation())
            except Exception as exc:
                self._json(HTTPStatus.BAD_REQUEST, {"ok": False, "error": str(exc)})

        def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors_headers()
            self.end_headers()
            self.wfile.write(body)

        def _text(
            self,
            status: HTTPStatus,
            source: str,
            content_type: str,
            viewer: bool = False,
        ) -> None:
            body = source.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self._cors_headers()
            policy = "default-src 'self'; style-src 'self'; script-src 'self'; frame-src 'self'"
            if viewer:
                policy = "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; font-src 'none'"
            self.send_header("Content-Security-Policy", policy)
            self.end_headers()
            self.wfile.write(body)

        def _cors_headers(self) -> None:
            origin = self.headers.get("Origin", "").rstrip("/")
            if origin and allowed_origin and secrets.compare_digest(origin, allowed_origin):
                self.send_header("Access-Control-Allow-Origin", allowed_origin)
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, X-TWR-Token")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Max-Age", "600")
                self.send_header("Vary", "Origin")

        def log_message(self, format: str, *args: Any) -> None:
            return

    return Handler
