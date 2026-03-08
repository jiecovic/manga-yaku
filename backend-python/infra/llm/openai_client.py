# backend-python/infra/llm/openai_client.py
"""OpenAI API client wrappers for OCR and translation calls."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from config import OPENAI_API_KEY
from infra.llm.model_capabilities import model_applies_temperature

# Optional OpenAI import (shared by all modules)
try:
    from openai import OpenAI  # type: ignore

    _openai_import_error: Exception | None = None
except Exception as e:  # pragma: no cover
    OpenAI = None  # type: ignore
    _openai_import_error = e


def has_openai_sdk() -> bool:
    """
    Return True if the OpenAI Python SDK is importable.
    Does NOT check API keys or endpoints, only the library itself.
    """
    return OpenAI is not None and _openai_import_error is None


def create_openai_client(profile_config: dict[str, Any]):
    """
    Construct an OpenAI client based on a profile's config dict.

    Behaviour:
    - If config["base_url"] is set → treat as local/self-hosted
      OpenAI-compatible endpoint (TextGen WebUI, LM Studio, etc.).
    - Otherwise → use real OpenAI with OPENAI_API_KEY.

    Raises:
    - RuntimeError if SDK is missing or required config is not present.
    """
    if not has_openai_sdk():
        raise RuntimeError(f"OpenAI SDK is not available: {_openai_import_error!r}")

    cfg = profile_config or {}
    base_url = cfg.get("base_url")

    # Local / self-hosted endpoint
    if base_url:
        # Many local servers ignore the API key, but we pass something anyway.
        api_key = OPENAI_API_KEY or "none"
        return OpenAI(api_key=api_key, base_url=base_url)

    # Real OpenAI
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY is not set for OpenAI profile")

    return OpenAI(api_key=OPENAI_API_KEY)


def build_chat_params(
    cfg: dict[str, Any],
    messages: list[dict[str, Any]],
    *,
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": cfg["model"],
        "messages": messages,
    }

    excluded = {"model", "prompt_file", "base_url"}
    excluded.update(exclude)

    for key, value in cfg.items():
        if key in excluded:
            continue
        if key == "temperature" and not model_applies_temperature(cfg.get("model")):
            continue
        params[key] = value

    return params


def build_response_params(
    cfg: dict[str, Any],
    input_payload: list[dict[str, Any]],
    *,
    exclude: Iterable[str] = (),
) -> dict[str, Any]:
    model = cfg["model"]
    params: dict[str, Any] = {
        "model": model,
        "input": input_payload,
    }

    excluded = {"model", "prompt_file", "base_url"}
    excluded.update(exclude)

    max_output = cfg.get("max_output_tokens")
    if max_output is None:
        if "max_completion_tokens" in cfg:
            max_output = cfg.get("max_completion_tokens")
        elif "max_tokens" in cfg:
            max_output = cfg.get("max_tokens")
    if max_output is not None:
        params["max_output_tokens"] = max_output

    for key, value in cfg.items():
        if key in excluded:
            continue
        if key in {"max_tokens", "max_completion_tokens", "max_output_tokens"}:
            continue
        if key == "temperature" and not model_applies_temperature(model):
            continue
        params[key] = value

    return params


def is_openai_base_url_reachable(base_url: str, *, timeout: float = 0.6) -> bool:
    if not base_url:
        return False

    url = urljoin(base_url.rstrip("/") + "/", "models")
    req = Request(url, headers={"Accept": "application/json"})

    try:
        with urlopen(req, timeout=timeout) as resp:
            status = getattr(resp, "status", 200)
            return 200 <= status < 300
    except HTTPError:
        return False
    except URLError:
        return False
    except Exception:
        return False


def extract_response_text(
    response: Any,
    *,
    raise_on_refusal: bool = False,
) -> str:
    raw = getattr(response, "output_text", None)
    if raw:
        return str(raw)

    output = getattr(response, "output", None)
    if output:
        parts: list[str] = []
        refusal: str | None = None
        for item in output:
            content = getattr(item, "content", None)
            if content is None and isinstance(item, dict):
                content = item.get("content")
            if not content:
                continue
            if isinstance(content, str):
                parts.append(content)
                continue
            if isinstance(content, dict):
                content = [content]
            for chunk in content:
                chunk_type = None
                text_value = None
                if isinstance(chunk, dict):
                    chunk_type = chunk.get("type")
                    text_value = chunk.get("text")
                    if chunk_type == "refusal":
                        refusal = str(chunk.get("refusal") or "")
                else:
                    chunk_type = getattr(chunk, "type", None)
                    text_value = getattr(chunk, "text", None)
                    if chunk_type == "refusal":
                        refusal = str(getattr(chunk, "refusal", "") or "")
                if isinstance(text_value, dict):
                    text_value = text_value.get("value") or text_value.get("text")
                if text_value and (chunk_type in (None, "output_text", "text", "summary_text")):
                    parts.append(str(text_value))
        if parts:
            return "\n".join(parts)
        if refusal and raise_on_refusal:
            raise ValueError(f"Model refusal: {refusal}")

    return ""
