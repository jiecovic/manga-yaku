# backend-python/mcp_server/README.md
## MCP in MangaYaku

MCP stands for Model Context Protocol.

In practice:
- an MCP server exposes tools/resources over the MCP protocol
- an MCP client connects to that server
- an agent/runtime uses the client to call tools

So MCP is a protocol, but it still needs concrete software on both sides.

## How We Use It Now

Current setup in this repo:
- the MCP server is implemented locally in [server.py](/home/thomas/projects/manga-yaku/backend-python/mcp_server/server.py) and [tools.py](/home/thomas/projects/manga-yaku/backend-python/mcp_server/tools.py)
- the FastAPI backend mounts that MCP server at `/api/mcp` in [app.py](/home/thomas/projects/manga-yaku/backend-python/app.py)
- the chat agent creates MCP client instances in [mcp_runtime.py](/home/thomas/projects/manga-yaku/backend-python/core/usecases/agent/runtime/mcp_runtime.py)
- those clients connect back to the same backend over Streamable HTTP

So today we have both:
- a local MCP server inside the backend process
- a local MCP client used by the chat agent

This is not a separate service by default. It is a mounted sub-app inside the main backend.

## Why MCP

The main reason we use MCP is to keep the tool surface provider-neutral.

That gives us a better chance to switch or compare agent runtimes later, for example:
- OpenAI Agents SDK
- Anthropic MCP-connected runtimes
- other MCP-capable agent stacks

MCP helps standardize the tool boundary.
It does not standardize the full agent runtime.

Still provider-specific:
- prompting
- turn orchestration
- streaming event behavior
- session semantics
- retry/tool-calling behavior

So the intended architecture is:
- our tool logic stays in our backend
- MCP exposes that tool surface in a portable way
- provider-specific agent runtimes sit on top

## Why MCP Clients Are Run-Scoped

Each chat run creates MCP clients with run-specific headers:
- volume id
- active filename
- agent run id

Because that context is run-specific, the MCP clients are currently created per run and cleaned up after the run. We do not keep them open globally.

Cleanup happens in [mcp_runtime.py](/home/thomas/projects/manga-yaku/backend-python/core/usecases/agent/runtime/mcp_runtime.py):
- close MCP client resources
- clear run-scoped active-page state

## What Providers Do

OpenAI and Anthropic support using MCP, but they do not automatically host this repo's MCP server for us.

What they provide is support for:
- connecting agent runtimes to MCP servers
- using MCP over transports like Streamable HTTP

Our business tools still need a server implementation somewhere. Right now that server is our local `backend-python/mcp_server` package.

## Open Decisions

The current design is valid, but these choices are still open:

1. Keep the same-process self-HTTP MCP hop, or call the tool adapter layer directly for local chat runs.
2. Keep MCP clients run-scoped, or add explicit session pooling/reuse later.
3. Keep MCP as both an internal runtime path and an external integration surface, or reserve it mainly for external integrations.

Current recommendation:
- keep the current run-scoped cleanup model
- keep MCP working as the stable tool surface
- revisit the internal self-HTTP hop later if latency/complexity becomes a bigger concern

## References

- MCP architecture overview: https://modelcontextprotocol.io/docs/learn/architecture
- MCP lifecycle specification: https://modelcontextprotocol.io/specification/2025-03-26/basic/lifecycle
- OpenAI Agents SDK MCP guide: https://openai.github.io/openai-agents-python/mcp/
- Anthropic MCP overview: https://docs.anthropic.com/en/docs/mcp
- Anthropic MCP connector: https://docs.anthropic.com/en/docs/agents-and-tools/mcp-connector
