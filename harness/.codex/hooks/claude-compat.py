#!/usr/bin/env python3
"""Run the project's Claude hooks with Codex payloads, without copying policies."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def rules():
    """SessionStart: Claude reads .claude/rules/*.md itself, Codex gets the same files as context."""
    root = Path(__file__).resolve().parents[2]
    text = "\n\n".join(path.read_text(encoding="utf-8") for path in sorted((root / ".claude/rules").glob("*.md")))
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    return 0


def main():
    name = sys.argv[1]
    if name == "rules":
        return rules()
    if name not in {"plans-drift", "branch-guard", "commit-gate", "merge-gate", "main-push-guard", "db-wipe-guard", "big-read-guard", "registry-guard", "owner-ok-guard"}:
        raise ValueError("Unknown project hook")
    payload = json.load(sys.stdin)
    cwd = Path(payload.get("cwd") or Path.cwd()).resolve()
    tool_input = payload.get("tool_input") or {}
    if isinstance(tool_input, str):
        tool_input = {"command": tool_input}
    tool_input = dict(tool_input)
    command = tool_input.get("command", tool_input.get("cmd", ""))
    tool_input["command"] = command
    tool = payload.get("tool_name", "")
    if tool in {"exec_command", "shell_command", "shell", "functions.exec_command"}:
        tool = "Bash"
    workdir = tool_input.get("workdir")
    if workdir:
        cwd = (cwd / workdir).resolve()
    root = Path(__file__).resolve().parents[2]
    found = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True,
    )
    if found.returncode == 0:
        candidate = Path(found.stdout.strip())
        if (candidate / ".claude/hooks").is_dir():
            root = candidate
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(root))
    inputs = [tool_input]
    if name in {"branch-guard", "registry-guard"} and tool in {"apply_patch", "functions.apply_patch"}:
        paths = re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$", command, re.M)
        inputs = []
        for path in paths:
            target = (cwd / path).resolve()
            parent = target.parent
            while not parent.is_dir():
                parent = parent.parent
            # registry-guard нужен настоящий путь (planning/ROADMAP.md); branch-guard — существующий каталог
            inputs.append({"file_path": str(target if name == "registry-guard" else parent / target.name)})
        if not inputs:
            inputs = [{"file_path": str(cwd / ".codex-hook-target")}]
    for item in inputs:
        result = subprocess.run(
            ["bash", str(root / ".claude/hooks" / (name + ".sh"))],
            input=json.dumps(dict(payload, cwd=str(cwd), tool_name=tool, tool_input=item)),
            text=True, cwd=cwd, env=env,
        )
        if result.returncode:
            if name == "big-read-guard":
                print("В Codex: читай нужный диапазон через rg/sed; для делегирования используй доступного worker или субагента Codex.", file=sys.stderr)
            return result.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
