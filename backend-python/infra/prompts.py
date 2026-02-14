# backend-python/infra/prompts.py
from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, TypedDict

import yaml
from config import PROJECT_ROOT
from jinja2 import Template

_override_dir = os.getenv("MANGAYAKU_PROMPTS_DIR")
if _override_dir:
    PROMPTS_DIR = Path(_override_dir).expanduser().resolve()
else:
    PROMPTS_DIR = PROJECT_ROOT / "prompts"
    if not PROMPTS_DIR.exists():
        PROMPTS_DIR = Path(__file__).resolve().parent


class PromptBundle(TypedDict):
    system: str
    user_template: str


def load_prompt_bundle(name: str) -> PromptBundle:
    """
    Load a YAML prompt bundle from PROMPTS_DIR.

    Expected YAML structure:

      system: |
        ...
      user_template: |
        ...
    """
    path = PROMPTS_DIR / name

    if not path.exists():
        raise FileNotFoundError(f"Prompt bundle not found: {path}")

    try:
        raw = path.read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
    except Exception as exc:
        raise RuntimeError(f"Failed to parse YAML prompt bundle '{name}': {exc}") from exc

    if not isinstance(data, dict):
        raise RuntimeError(f"YAML prompt bundle '{name}' must contain a mapping/object.")

    system_raw = data.get("system")
    user_raw = data.get("user_template")

    if not isinstance(system_raw, str | None):
        raise RuntimeError(f"'system' in '{name}' must be a string.")
    if not isinstance(user_raw, str | None):
        raise RuntimeError(f"'user_template' in '{name}' must be a string.")

    system = (system_raw or "").strip()
    user_template = (user_raw or "{{TEXT}}").strip()

    return {
        "system": system,
        "user_template": user_template,
    }


def render_template(template_str: str, context: Mapping[str, Any]) -> str:
    """
    Render a single Jinja2 template string with the given context.
    Trims leading/trailing whitespace in the final result.
    """
    try:
        tmpl = Template(template_str)
        rendered = tmpl.render(**context)
    except Exception as exc:
        raise RuntimeError(f"Failed to render prompt template: {exc}") from exc

    return rendered.strip()


def render_prompt_bundle(
    bundle: PromptBundle,
    *,
    system_context: Mapping[str, Any],
    user_context: Mapping[str, Any],
) -> PromptBundle:
    """
    Render both system and user_template of a PromptBundle with Jinja2.
    """
    system_rendered = render_template(bundle["system"], system_context)
    user_rendered = render_template(bundle["user_template"], user_context)

    return {
        "system": system_rendered,
        "user_template": user_rendered,
    }

