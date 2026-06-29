from __future__ import annotations

import platform
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ollama_check import get_ollama_models, load_models_config, missing_model_warnings


def run_doctor(repo_root: Path = REPO_ROOT) -> dict[str, object]:
    config = load_models_config(repo_root / "config" / "models.yaml")
    base_url = (config.get("ollama") or {}).get("base_url", "http://localhost:11434")
    reachable, models, error = get_ollama_models(base_url)
    required_paths = [
        "AGENTS.md",
        "config/models.yaml",
        "config/reviewer_defaults.yaml",
        "templates/story",
        "scripts/novel.py",
        "scripts/review.py",
        "scripts/build_context.py",
    ]
    missing_paths = [path for path in required_paths if not (repo_root / path).exists()]
    return {
        "python": platform.python_version(),
        "python_ok": sys.version_info >= (3, 10),
        "ollama_base_url": base_url,
        "ollama_reachable": reachable,
        "ollama_error": error,
        "ollama_models": models,
        "model_warnings": missing_model_warnings(config, models),
        "missing_paths": missing_paths,
    }


def print_report(result: dict[str, object]) -> None:
    print("Novel AI Workbench Doctor")
    print(f"Python: {result['python']} ({'OK' if result['python_ok'] else '需要 Python 3.10+'})")
    print(f"Ollama: {result['ollama_base_url']} ({'reachable' if result['ollama_reachable'] else 'not reachable'})")
    if result.get("ollama_error"):
        print(f"Ollama error: {result['ollama_error']}")
    print("Installed Ollama models:")
    models = result.get("ollama_models") or []
    if models:
        for model in models:
            print(f"- {model}")
    else:
        print("- none detected")
    for warning in result.get("model_warnings") or []:
        print(f"WARNING: {warning}")
    missing_paths = result.get("missing_paths") or []
    if missing_paths:
        print("Missing workbench paths:")
        for path in missing_paths:
            print(f"- {path}")
    else:
        print("Workbench paths: OK")


def main() -> int:
    print_report(run_doctor())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
