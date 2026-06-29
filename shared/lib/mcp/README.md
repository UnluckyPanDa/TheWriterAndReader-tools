# MCP 伺服器（選用）

這個目錄提供一個本機 MCP server，讓 Codex App 或其他支援 MCP 的工具呼叫小說工作台功能。CLI 腳本仍是主要入口，MCP 只是包一層工具介面。

## 安全規則

- MCP 工具不會直接覆寫 `stories/<story_id>/canon/`。
- 任何 canon 變更都必須先寫入 `stories/<story_id>/proposed_canon_updates/`。
- `accept-canon-update` 仍需要明確命令，不會自動套用模型建議。
- `write_chapter_draft` 只寫入 `drafts/`，若檔案已存在會建立帶時間戳的新草稿。

## 安裝 MCP 依賴

`requirements.txt` 不強制安裝 MCP，避免因套件命名或版本變動讓基本安裝失敗。若你要啟用 MCP，可以在本機虛擬環境內另外安裝：

```bash
python -m pip install mcp
```

若安裝後仍無法啟動，請先使用 CLI：

```bash
python scripts/novel.py doctor
python scripts/novel.py review --story _example --chapter 1
```

## Codex App 設定範例

請手動把以下片段加入 Codex App 使用的設定檔。不要讓本專案自動修改你的全域 `~/.codex/config.toml`。

```toml
[mcp_servers.novel_ai_workbench]
command = "/Volumes/SN7100/Projects/TheWriterAndReader/.venv/bin/python"
args = ["/Volumes/SN7100/Projects/TheWriterAndReader/mcp/novel_mcp_server.py"]
```

若你不用 `.venv`，把 `command` 換成你要使用的 Python 路徑。

## 可用工具

- `list_stories()`
- `init_story(story_id)`
- `get_story_config(story_id)`
- `build_context(story_id, chapter_number)`
- `review_chapter(story_id, chapter_number, reviewers=None)`
- `write_chapter_draft(story_id, chapter_number, brief_file=None)`
- `propose_canon_update(story_id, chapter_number)`
- `list_reviewer_profiles(story_id)`
- `add_reviewer_profile(story_id, reviewer_id, profile_text)`
