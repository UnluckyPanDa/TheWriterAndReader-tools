from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from cli.twr import build_parser
from tools.web.server import ToolDispatcher, create_server
from shared.lib.yaml_utils import dump_yaml
from tools.wizard.scaffold import add_story, init_workspace


class WebGuiTests(unittest.TestCase):
    def test_dispatcher_creates_workspace_and_story(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = str(Path(temp_dir) / "workspace")
            dispatcher = ToolDispatcher()

            created = dispatcher.run("workspace_init", {"workspace": workspace, "workspace_id": "web"})
            story = dispatcher.run(
                "story_add",
                {"workspace": workspace, "story": "story-1", "title": "Web Story", "language": "en"},
            )

            self.assertTrue(created["ok"])
            self.assertEqual(created["workspace"]["path"], str(Path(workspace).resolve()))
            self.assertTrue(story["ok"])
            self.assertEqual(story["workspace"]["stories"][0]["title"], "Web Story")
            self.assertTrue(story["workspace"]["stories"][0]["has_relation_graph"])

    def test_dispatcher_rejects_arbitrary_actions(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported web action"):
            ToolDispatcher().run("shell", {"command": "whoami"})

    def test_dispatcher_exposes_config_path(self) -> None:
        result = ToolDispatcher().run("config_path", {})
        self.assertTrue(result["ok"])
        self.assertTrue(str(result["output"]).endswith("config.yaml"))

    def test_auth_required_needs_supabase_configuration(self) -> None:
        with self.assertRaisesRegex(ValueError, "TWR_AUTH_URL and TWR_AUTH_ANON_KEY"):
            create_server(port=0, auth_required=True)

    def test_auth_required_server_is_configured(self) -> None:
        server = create_server(
            port=0,
            token="local-only-token",
            auth_url="https://auth.example.test",
            auth_anon_key="public-key",
            auth_required=True,
        )
        self.assertTrue(server.twr_auth_required)
        server.server_close()

    def test_reader_returns_chapter_and_allowlisted_wiki_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            init_workspace(workspace, "reader")
            story = add_story(workspace, "story-1", "Reader Story", "en")
            (story / "chapters").mkdir()
            (story / "chapters" / "chapter_001.md").write_text(
                "# Chapter 1\n\nSee [[characters]] before the choice.", encoding="utf-8"
            )

            result = ToolDispatcher().reader(str(workspace), "story-1", 1)

            self.assertEqual(result["chapter"]["source"], "accepted")
            self.assertIn("[[characters]]", result["chapter"]["content"])
            self.assertTrue(any(page["key"] == "characters" for page in result["wiki"]))

    def test_reader_actions_save_storyline_graph_and_review_comment(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir) / "workspace"
            init_workspace(workspace, "reader-actions")
            story = add_story(workspace, "story-1", "Reader Actions", "en")
            dispatcher = ToolDispatcher()

            storyline = dispatcher.run(
                "storyline_save",
                {"workspace": str(workspace), "story": "story-1", "file": "chapter_plan.md", "content": "# Plan\n"},
            )
            graph = dispatcher.run(
                "relationship_graph_save",
                {
                    "workspace": str(workspace),
                    "story": "story-1",
                    "content": dump_yaml(
                        {
                            "version": 1,
                            "characters": [{"id": "a", "label": "A"}],
                            "relationships": [],
                        },
                        sort_keys=False,
                    ),
                },
            )
            comment = dispatcher.run(
                "review_comment_add",
                {
                    "workspace": str(workspace),
                    "story": "story-1",
                    "chapter": "1",
                    "author": "Reader",
                    "location": "Opening",
                    "comment": "The hook is clear.",
                },
            )

            self.assertTrue(storyline["ok"] and graph["ok"] and comment["ok"])
            self.assertIn("# Plan", (story / "storyline" / "chapter_plan.md").read_text(encoding="utf-8"))
            self.assertIn("version: 1", (story / "canon" / "relationship_graph.yaml").read_text(encoding="utf-8"))
            self.assertIn("The hook is clear.", (story / "reviews" / "chapter_001" / "user_comments.md").read_text(encoding="utf-8"))

    def test_web_command_is_registered(self) -> None:
        args = build_parser().parse_args(
            ["web", "--port", "9876", "--no-open", "--auth-url", "https://auth.example.test", "--auth-anon-key", "public-key", "--auth-required", "--allowed-origin", "https://twr.example.test"]
        )
        self.assertEqual(args.port, 9876)
        self.assertTrue(args.no_open)
        self.assertEqual(args.auth_url, "https://auth.example.test")
        self.assertEqual(args.auth_anon_key, "public-key")
        self.assertTrue(args.auth_required)
        self.assertEqual(args.allowed_origin, "https://twr.example.test")

    def test_dashboard_has_separate_tools_reader_links_and_theme_toggle(self) -> None:
        static_root = Path(__file__).parents[1] / "tools" / "web" / "static"
        html = (static_root / "index.html").read_text(encoding="utf-8")
        app = (static_root / "app.js").read_text(encoding="utf-8")
        self.assertIn('class="tool-tabs"', html)
        self.assertIn('role="tablist"', html)
        self.assertIn('id="chooseWorkspace"', html)
        self.assertIn('id="workspaceHistory"', html)
        self.assertIn('id="languageSelect"', html)
        self.assertIn('value="zh-Hant"', html)
        self.assertIn('id="reader"', html)
        for section in ("writing", "review", "storyline", "relations", "publishing", "system"):
            self.assertIn(f'id="{section}"', html)
            self.assertIn(f'data-section="{section}"', html)
        self.assertIn('role="tabpanel"', html)
        self.assertIn('data-section-link="storyline"', html)
        self.assertIn('id="themeToggle"', html)
        self.assertIn("localStorage.getItem('twr.theme')", app)
        self.assertIn("data-wiki", app)
        self.assertIn("function activateSection", app)
        self.assertIn("item.hidden = item !== section", app)
        self.assertIn("/api/pick-folder", app)
        self.assertIn("/api/settings", app)
        self.assertIn("UI_STRINGS", app)
        self.assertIn("zh-Hant", app)

    def test_user_settings_round_trip_and_normalise_history(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"TWR_UI_SETTINGS": str(Path(temp_dir) / "ui-settings.yaml")}
        ):
            from shared.lib.user_settings import load_user_settings, save_user_settings

            saved = save_user_settings(
                {"theme": "light", "language": "zh-Hant", "workspace_history": ["/one", "/one", "", "/two"]}
            )
            self.assertEqual(saved["theme"], "light")
            self.assertEqual(saved["language"], "zh-Hant")
            self.assertEqual(saved["workspace_history"], ["/one", "/two"])
            self.assertEqual(load_user_settings(), saved)

    def test_http_folder_picker_is_token_protected(self) -> None:
        with patch("tools.web.server.choose_workspace_folder", return_value="/tmp/workspace"):
            server = create_server(port=0, token="picker-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(
                    base + "/api/pick-folder",
                    data=b"",
                    headers={"X-TWR-Token": "picker-token"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    result = json.loads(response.read())
                self.assertEqual(result["path"], "/tmp/workspace")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_http_settings_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ, {"TWR_UI_SETTINGS": str(Path(temp_dir) / "ui-settings.yaml")}
        ):
            server = create_server(port=0, token="settings-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                body = json.dumps({"theme": "light", "workspace_history": ["/workspace"]}).encode()
                request = Request(
                    base + "/api/settings",
                    data=body,
                    headers={"Content-Type": "application/json", "X-TWR-Token": "settings-token"},
                    method="POST",
                )
                with urlopen(request, timeout=3) as response:
                    saved = json.loads(response.read())
                self.assertEqual(saved["theme"], "light")

                request = Request(base + "/api/settings", headers={"X-TWR-Token": "settings-token"})
                with urlopen(request, timeout=3) as response:
                    loaded = json.loads(response.read())
                self.assertEqual(loaded["workspace_history"], ["/workspace"])
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_http_gui_and_token_protected_workspace_api(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = str(Path(temp_dir) / "workspace")
            ToolDispatcher().run("workspace_init", {"workspace": workspace, "workspace_id": "http"})
            server = create_server(port=0, workspace=workspace, token="test-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                with urlopen(base + "/", timeout=3) as response:
                    page = response.read().decode("utf-8")
                self.assertIn("TWR Control Room", page)
                self.assertIn('content="test-token"', page)
                self.assertNotIn("__TWR_WORKSPACE__", page)

                with self.assertRaises(HTTPError) as context:
                    urlopen(base + f"/api/workspace?path={workspace}", timeout=3)
                self.assertEqual(context.exception.code, 403)

                request = Request(
                    base + f"/api/workspace?path={workspace}", headers={"X-TWR-Token": "test-token"}
                )
                with urlopen(request, timeout=3) as response:
                    summary = json.loads(response.read())
                self.assertEqual(summary["path"], str(Path(workspace).resolve()))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_http_auth_required_accepts_valid_supabase_bearer(self) -> None:
        with patch(
            "tools.web.server._supabase_user",
            return_value={"id": "user-1", "email": "writer@example.com"},
        ):
            server = create_server(
                port=0,
                auth_url="https://auth.example.test",
                auth_anon_key="public-key",
                auth_required=True,
            )
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                request = Request(base + "/api/auth/me", headers={"Authorization": "Bearer valid-token"})
                with urlopen(request, timeout=3) as response:
                    result = json.loads(response.read())
                self.assertEqual(result["user"]["id"], "user-1")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)

    def test_http_auth_required_page_injects_provider_without_local_token(self) -> None:
        server = create_server(
            port=0,
            token="local-only-token",
            auth_url="https://auth.example.test",
            auth_anon_key="public-key",
            auth_required=True,
        )
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base + "/", timeout=3) as response:
                page = response.read().decode("utf-8")
            self.assertIn('content="https://auth.example.test"', page)
            self.assertIn('content="public-key"', page)
            self.assertIn('content="true"', page)
            self.assertNotIn("local-only-token", page)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_http_cors_allows_configured_site_origin(self) -> None:
        server = create_server(port=0, token="cors-token", allowed_origin="https://twr.example.test")
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            request = Request(base + "/api/health", headers={"Origin": "https://twr.example.test"})
            with urlopen(request, timeout=3) as response:
                self.assertEqual(response.headers["Access-Control-Allow-Origin"], "https://twr.example.test")

            request = Request(base + "/api/health", headers={"Origin": "https://other.example.test"})
            with urlopen(request, timeout=3) as response:
                self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

    def test_http_action_returns_json_and_refreshes_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = str(Path(temp_dir) / "workspace")
            ToolDispatcher().run("workspace_init", {"workspace": workspace, "workspace_id": "actions"})
            server = create_server(port=0, token="action-token")
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            body = json.dumps(
                {
                    "action": "story_add",
                    "workspace": workspace,
                    "story": "story-web",
                    "title": "Story Web",
                    "language": "en",
                }
            ).encode("utf-8")
            request = Request(
                base + "/api/action",
                data=body,
                headers={"Content-Type": "application/json", "X-TWR-Token": "action-token"},
                method="POST",
            )
            try:
                with urlopen(request, timeout=3) as response:
                    result = json.loads(response.read())
                self.assertTrue(result["ok"])
                self.assertEqual(result["workspace"]["stories"][0]["id"], "story-web")
                reader_request = Request(
                    base + f"/api/reader?workspace={workspace}&story=story-web&chapter=1",
                    headers={"X-TWR-Token": "action-token"},
                )
                with urlopen(reader_request, timeout=3) as response:
                    reader = json.loads(response.read())
                self.assertEqual(reader["story"]["title"], "Story Web")
                self.assertTrue(any(page["key"] == "chapter_plan" for page in reader["wiki"]))
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
