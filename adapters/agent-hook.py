#!/usr/bin/env python3
"""Run a project's x-harness Claude hooks from any agent client.

Usage: agent-hook.py <client> <Event>   (payload JSON on stdin)

Clients (Kimi Code, ZCode, OpenCode, ...) send their own hook payloads. This script finds the
project from payload.cwd, reads its .claude/settings.json, normalizes the tool name and input to
the Claude shape and runs the matching hooks. Policies live only in the project's .claude/hooks.
Exit 2 + stderr = block, as in Claude Code. A project without x-harness is a no-op (exit 0).
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

MARKER = ".claude/hooks/plans-drift.sh"  # present in the full and the planning profile

TOOL_ALIASES = {
    "Bash": {"bash", "shell", "exec_command", "shell_command", "run_shell_command", "local_bash", "terminal",
             "functions.exec_command"},
    "Edit": {"edit", "multiedit", "str_replace", "strreplacefile", "notebookedit", "applypatch", "apply_patch",
             "patch", "functions.apply_patch"},
    "Write": {"write", "writefile", "create"},
    "Read": {"read", "readfile", "view"},
}
PATCH_PATH = re.compile(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", re.M)


def claude_tool(name):
    low = (name or "").lower()
    for claude, aliases in TOOL_ALIASES.items():
        if low == claude.lower() or low in aliases:
            return claude
    return name or ""


def project_root(cwd):
    found = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    root = Path(found.stdout.strip()) if found.returncode == 0 else None
    return root if root and (root / MARKER).is_file() else None


def tool_inputs(raw, cwd):
    """One or more Claude-shaped tool_input dicts (a patch touching N files gives N inputs)."""
    if isinstance(raw, str):
        raw = {"command": raw}
    item = dict(raw or {})
    command = item.get("command", item.get("cmd"))
    if command is not None:
        item["command"] = command
    path = item.get("file_path") or item.get("filePath") or item.get("path")
    if path:
        item["file_path"] = str((cwd / path).resolve())
        return [item]
    patch = next((v for v in item.values() if isinstance(v, str) and PATCH_PATH.search(v)), None)
    if patch:
        return [dict(item, file_path=str((cwd / p.strip()).resolve())) for p in PATCH_PATH.findall(patch)]
    return [item]


def matching_hooks(settings, event, tool):
    for group in settings.get("hooks", {}).get(event, []):
        matcher = group.get("matcher") or ""
        if event == "PreToolUse" and matcher and not re.fullmatch(matcher, tool):
            continue
        for hook in group.get("hooks", []):
            if hook.get("type", "command") == "command" and hook.get("command"):
                yield hook["command"], hook.get("timeout", 60)


def run(command, payload, root, cwd, timeout):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    try:
        return subprocess.run(["bash", "-c", command], input=json.dumps(payload), text=True, cwd=cwd, env=env,
                              capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(command, 1, "", f"x-harness hook timed out: {command}")


def plugin_client():
    """hooks/hooks.json is loaded by ZCode, Codex and Claude Code plugins alike; tell them apart."""
    if os.environ.get("ZCODE_PLUGIN_ROOT"):
        return "zcode"  # ZCode also sets CLAUDE_PROJECT_DIR, so check it first
    if os.environ.get("CLAUDE_PROJECT_DIR"):
        return "claude"  # Claude Code always sets it for hooks; Codex never does
    return "codex"  # Codex (payload has turn_id) or an unknown host: enforce rather than skip


def already_native(client, root):
    """Clients whose project-level wiring already runs the same hooks: skip to avoid a double run."""
    return client == "claude" or (client == "codex" and (root / ".codex/hooks.json").is_file())


def main():
    client, event = sys.argv[1], sys.argv[2]
    raw = sys.stdin.read()
    payload = json.loads(raw) if raw.strip() else {}
    cwd = Path(payload.get("cwd") or payload.get("directory") or os.getcwd()).resolve()
    root = project_root(cwd)
    if client == "plugin":
        client = plugin_client()
    if root is None or already_native(client, root):
        return 0
    settings = json.loads((root / ".claude/settings.json").read_text(encoding="utf-8"))

    if event == "SessionStart":
        parts = [run(c, dict(payload, hook_event_name=event), root, cwd, t).stdout
                 for c, t in matching_hooks(settings, event, "")]
        parts += [p.read_text(encoding="utf-8") for p in sorted((root / ".claude/rules").glob("*.md"))]
        context = "\n\n".join(p.strip() for p in parts if p.strip())
        if context:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": context}}))
        return 0

    tool = claude_tool(payload.get("tool_name") or payload.get("tool"))
    for item in tool_inputs(payload.get("tool_input", payload.get("args")), cwd):
        hook_payload = dict(payload, hook_event_name=event, cwd=str(cwd), tool_name=tool, tool_input=item)
        for command, timeout in matching_hooks(settings, event, tool):
            result = run(command, hook_payload, root, cwd, timeout)
            if result.returncode == 2:
                sys.stderr.write(result.stderr or result.stdout or f"Blocked by x-harness: {command}\n")
                return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
