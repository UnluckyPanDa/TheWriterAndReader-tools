"""Run optional OpenAI-compatible online model providers."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


def run_online_api_model(
    provider_config: dict[str, Any],
    model_profile: dict[str, Any],
    prompt: str,
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run a prompt through an OpenAI-compatible chat completions endpoint."""
    options = options or {}
    if not provider_config.get("enabled", False):
        return {"ok": False, "text": "", "reason": "provider_disabled_or_missing_api_key"}

    api_key_env = provider_config.get("api_key_env")
    api_key = os.environ.get(api_key_env, "") if isinstance(api_key_env, str) else ""
    if not api_key:
        return {"ok": False, "text": "", "reason": "provider_disabled_or_missing_api_key"}

    base_url = provider_config.get("base_url")
    model = model_profile.get("model")
    if not isinstance(base_url, str) or not base_url.strip():
        return {"ok": False, "text": "", "reason": "missing_base_url"}
    if not isinstance(model, str) or not model.strip():
        return {"ok": False, "text": "", "reason": "missing_model"}

    endpoint = f"{base_url.rstrip('/')}/chat/completions"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": options.get("temperature", 0.7),
    }
    if "max_tokens" in options:
        payload["max_tokens"] = options["max_tokens"]

    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=float(options.get("timeout_seconds", 120))) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        return {"ok": False, "text": "", "reason": f"http_error_{exc.code}: {detail[:300]}"}
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "text": "", "reason": f"request_failed: {exc}"}

    try:
        text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"ok": False, "text": "", "reason": "invalid_response_shape"}

    return {"ok": True, "text": str(text).strip(), "reason": None}
