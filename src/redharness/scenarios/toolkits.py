"""Named mock toolkits shared by the bundled scenario suites.

Tool *semantics* must be deterministic Python (no network, no clock), so they live
here in code; the scenario *suites* (which toolkit, which user task, which checks)
are hash-pinned data under ``scenarios/data``. Each toolkit returns a list of
:class:`Tool` plus the handler functions that implement them against the
environment's in-memory ``state``.

Two toolkits, mirroring the two reference benchmarks (plan §5 Phase 2):

  * ``messaging`` — InjecAgent-style: read a document, then a sensitive
    ``send_email`` / ``transfer_funds`` the attacker tries to trigger.
  * ``workspace`` — AgentDojo-style: search a workspace, read a file, and a
    sensitive ``share_file`` the attacker tries to trigger.
"""

from __future__ import annotations

from typing import Any

from redharness.core.tools import Tool, ToolEnvironment, ToolFn

ToolkitBuild = tuple[list[Tool], dict[str, ToolFn]]


def _read_document(env: ToolEnvironment, args: dict[str, Any]) -> str:
    """Return a stored document body; the indirect-injection delivery point."""
    docs: dict[str, str] = env.state.get("documents", {})
    return docs.get(args["doc_id"], f"(no document {args['doc_id']!r})")


def _send_email(env: ToolEnvironment, args: dict[str, Any]) -> str:
    env.state.setdefault("sent_emails", []).append(args)
    return f"email queued to {args.get('to', '?')}"


def _transfer_funds(env: ToolEnvironment, args: dict[str, Any]) -> str:
    env.state.setdefault("transfers", []).append(args)
    return f"transfer of {args.get('amount', '?')} to {args.get('to', '?')} recorded"


def messaging_toolkit() -> ToolkitBuild:
    """InjecAgent-style messaging tools: read a doc, send mail, move funds."""
    tools = [
        Tool(
            name="read_document",
            description="Read the body of a stored document by id.",
            parameters={"doc_id": {"type": "string", "description": "document id"}},
        ),
        Tool(
            name="send_email",
            description="Send an email to a recipient.",
            parameters={
                "to": {"type": "string", "description": "recipient address"},
                "body": {"type": "string", "description": "message body"},
            },
        ),
        Tool(
            name="transfer_funds",
            description="Transfer simulated funds to an account.",
            parameters={
                "to": {"type": "string", "description": "destination account"},
                "amount": {"type": "string", "description": "amount to transfer"},
            },
        ),
    ]
    handlers: dict[str, ToolFn] = {
        "read_document": _read_document,
        "send_email": _send_email,
        "transfer_funds": _transfer_funds,
    }
    return tools, handlers


def _search(env: ToolEnvironment, args: dict[str, Any]) -> str:
    index: dict[str, str] = env.state.get("search_index", {})
    return index.get(args["query"], "no results")


def _read_file(env: ToolEnvironment, args: dict[str, Any]) -> str:
    files: dict[str, str] = env.state.get("files", {})
    return files.get(args["path"], f"(no file {args['path']!r})")


def _share_file(env: ToolEnvironment, args: dict[str, Any]) -> str:
    env.state.setdefault("shares", []).append(args)
    return f"shared {args.get('path', '?')} with {args.get('with', '?')}"


def workspace_toolkit() -> ToolkitBuild:
    """AgentDojo-style workspace tools: search, read a file, share a file."""
    tools = [
        Tool(
            name="search",
            description="Search the workspace and return a snippet.",
            parameters={"query": {"type": "string", "description": "search query"}},
        ),
        Tool(
            name="read_file",
            description="Read a workspace file by path.",
            parameters={"path": {"type": "string", "description": "file path"}},
        ),
        Tool(
            name="share_file",
            description="Share a workspace file with a recipient.",
            parameters={
                "path": {"type": "string", "description": "file path"},
                "with": {"type": "string", "description": "recipient"},
            },
        ),
    ]
    handlers: dict[str, ToolFn] = {
        "search": _search,
        "read_file": _read_file,
        "share_file": _share_file,
    }
    return tools, handlers


TOOLKIT_BUILDERS = {
    "messaging": messaging_toolkit,
    "workspace": workspace_toolkit,
}
