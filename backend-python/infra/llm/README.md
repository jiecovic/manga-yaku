# infra/llm

This package contains the low-level LLM transport helpers used by chat repair,
OCR, translation, and page-translation calls.

## Current structure

- `openai_client.py`
  - builds OpenAI / OpenAI-compatible request params
  - maps our stable config shape to `responses.create(...)` or
    `chat.completions.create(...)`
- `call_logger.py`
  - wraps the OpenAI calls and persists request/response telemetry
- `model_capabilities.py`
  - centralizes which runtime knobs are effective for a selected model

## Current policy

Prompt files and model selection are separate concerns:

- prompt text lives in `prompts/`
- model choice and runtime knobs come from code defaults plus DB-backed overrides

For model controls, the app currently exposes one stable internal shape:

- `model_id`
- `max_output_tokens`
- `reasoning_effort`
- `temperature`

But not every model uses every field.

Examples:

- GPT-5 / reasoning-style models:
  - use `reasoning_effort`
  - treat `temperature` as inactive in this app
- GPT-4.x / local OpenAI-compatible models:
  - use `temperature`
  - ignore `reasoning_effort`

The UI should disable controls that are inactive for the selected model, but we
still keep both values in storage so switching models does not destroy prior
preferences.

## Future providers

If we add Anthropic / Google / other providers later, the clean direction is:

1. Keep one provider-neutral internal runtime shape in core/settings.
2. Add one adapter per provider here that maps our internal fields to the
   provider API.
3. Keep provider-specific capability rules here too, so the backend and UI both
   consult one source of truth.

That keeps the rest of the app talking to stable internal settings instead of
hardcoding provider-specific parameter names everywhere.

## References

- OpenAI models docs: https://platform.openai.com/docs/models
- OpenAI GPT-5.2 docs: https://platform.openai.com/docs/models/gpt-5.2
- OpenAI GPT-5.4 docs: https://platform.openai.com/docs/models/gpt-5.4
