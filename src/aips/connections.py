"""Secret-safe HTTP adapters for user-selected AI providers."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
from urllib.request import Request, urlopen

from .dawproject import DawprojectError
from .providers import create_provider_envelope, validate_producer_response


@dataclass(frozen=True)
class ConnectionConfig:
    provider: str
    model: str
    api_key_env: str
    endpoint: str | None = None


def load_connection_config(path: str) -> ConnectionConfig:
    try:
        data = json.loads(open(path, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        raise DawprojectError(f"invalid AI connection config: {path}") from exc
    provider = str(data.get("provider", ""))
    if provider not in {"anthropic", "gemini"}:
        raise DawprojectError(f"unsupported AI provider: {provider}")
    model = str(data.get("model", "")).strip()
    api_key_env = str(data.get("api_key_env", "")).strip()
    if not model or not api_key_env:
        raise DawprojectError("AI connection needs model and api_key_env")
    if "api_key" in data:
        raise DawprojectError("do not store an API key in the config; use api_key_env")
    endpoint = data.get("endpoint")
    return ConnectionConfig(provider, model, api_key_env,
                            str(endpoint).rstrip("/") if endpoint else None)


def _prompt(envelope: dict[str, Any]) -> str:
    return "Return only the JSON response contract.\n" + json.dumps(
        envelope, ensure_ascii=False, separators=(",", ":")
    )


def build_http_request(config: ConnectionConfig, envelope: dict[str, Any],
                       environment: dict[str, str] | None = None) -> Request:
    env = os.environ if environment is None else environment
    api_key = env.get(config.api_key_env)
    if not api_key:
        raise DawprojectError(f"API key environment variable is not set: {config.api_key_env}")
    prompt = _prompt(envelope)
    if config.provider == "anthropic":
        url = config.endpoint or "https://api.anthropic.com/v1/messages"
        headers = {"content-type": "application/json", "x-api-key": api_key,
                   "anthropic-version": "2023-06-01"}
        body = {"model": config.model, "max_tokens": 4096,
                "system": "You are an AI Producer and Engineer. Obey every authority boundary.",
                "messages": [{"role": "user", "content": prompt}]}
    elif config.provider == "gemini":
        base = config.endpoint or "https://generativelanguage.googleapis.com/v1beta"
        url = f"{base}/models/{config.model}:generateContent"
        headers = {"content-type": "application/json", "x-goog-api-key": api_key}
        body = {
            "systemInstruction": {"parts": [{"text": "You are an AI Producer and Engineer. Obey every authority boundary."}]},
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        }
    else:  # Protected by configuration validation and useful for direct construction tests.
        raise DawprojectError(f"unsupported AI provider: {config.provider}")
    return Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")


def _json_text(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        stripped = "\n".join(lines[1:-1]).strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise DawprojectError("AI provider did not return valid JSON") from exc
    if not isinstance(value, dict):
        raise DawprojectError("AI provider response JSON must be an object")
    return value


def extract_provider_response(provider: str, response: dict[str, Any]) -> dict[str, Any]:
    try:
        if provider == "anthropic":
            text = next(block["text"] for block in response["content"] if block.get("type") == "text")
        elif provider == "gemini":
            text = response["candidates"][0]["content"]["parts"][0]["text"]
        else:
            raise DawprojectError(f"unsupported AI provider: {provider}")
    except (KeyError, IndexError, StopIteration, TypeError) as exc:
        raise DawprojectError(f"unexpected {provider} response shape") from exc
    return _json_text(text)


def call_producer(config: ConnectionConfig, producer_request: dict[str, Any], *,
                  opener: Callable[..., Any] = urlopen, timeout: float = 60.0) -> dict[str, Any]:
    """Call one provider, then enforce the Artist boundary before returning output."""
    request = build_http_request(config, create_provider_envelope(producer_request))
    try:
        with opener(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except DawprojectError:
        raise
    except Exception as exc:
        raise DawprojectError(f"AI provider request failed: {exc}") from exc
    return validate_producer_response(
        producer_request, extract_provider_response(config.provider, raw)
    )
