#!/usr/bin/env python3
"""adapters/agent-hook.py: every client's payload shape reaches the project's .claude/hooks."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ADAPTER = ROOT / "adapters/agent-hook.py"
INDEX = "planning/ROADMAP.md"  # registry-guard: indexes change only through registry.sh


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


class AgentHookTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        base = Path(cls.tmp.name)
        cls.project, cls.plain = base / "project", base / "plain"
        for repo in (cls.project, cls.plain):
            repo.mkdir()
            git(repo, "init", "-q", "-b", "main")
            git(repo, "-c", "user.email=t@example.invalid", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        subprocess.run(["bash", str(ROOT / "install.sh"), "--project", str(cls.project), "--profile", "planning",
                        "--clients", "none", "--skills", "none", "--no-verify"],
                       check=True, capture_output=True, env=dict(os.environ, HOME=str(base / "home")))
        git(cls.project, "switch", "-q", "-c", "hotfix/agent-hook")  # off main: E2 passes, registry-guard decides

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def hook(self, client, payload, project=None, env=None):
        payload = dict(payload, cwd=str(project or self.project))
        clean = {k: v for k, v in os.environ.items() if not k.startswith(("ZCODE_", "CLAUDE_"))}
        return subprocess.run(["python3", str(ADAPTER), client, "PreToolUse"], input=json.dumps(payload),
                              text=True, capture_output=True, env=dict(clean, **(env or {})))

    def assertBlocked(self, result, reason="registry.sh"):
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn(reason, result.stderr)

    def test_each_client_payload_shape_is_blocked(self):
        cases = {
            "kimi": ("kimi", {"tool_name": "Edit", "tool_input": {"path": INDEX}}, None),
            "zcode": ("plugin", {"tool_name": "Write", "tool_input": {"file_path": INDEX, "content": "x"}},
                      {"ZCODE_PLUGIN_ROOT": "/z"}),
            "opencode": ("opencode", {"tool_name": "edit", "tool_input": {"filePath": INDEX}}, None),
            "dsh": ("dsh", {"tool_name": "write", "tool_input": {"file_path": INDEX}}, None),
            "codex-plugin": ("plugin", {"turn_id": "t1", "tool_name": "apply_patch",
                                        "tool_input": {"command": f"*** Begin Patch\n*** Update File: {INDEX}\n"}}, None),
            "zcode-applypatch": ("plugin", {"tool_name": "ApplyPatch",
                                            "tool_input": {"patch": f"*** Begin Patch\n*** Add File: {INDEX}\n"}},
                                 {"ZCODE_PLUGIN_ROOT": "/z"}),
        }
        for name, (client, payload, env) in cases.items():
            with self.subTest(name):
                self.assertBlocked(self.hook(client, payload, env=env))

    def test_bash_goes_through_commit_gate(self):
        self.assertBlocked(self.hook("kimi", {"tool_name": "Bash", "tool_input": {"command": "git commit --no-verify -m x"}}), "E16")

    def test_allowed_calls_pass(self):
        for payload in ({"tool_name": "read", "tool_input": {"filePath": "README.md"}},
                        {"tool_name": "edit", "tool_input": {"filePath": "src/app.py"}}):
            with self.subTest(payload["tool_name"]):
                result = self.hook("opencode", payload)
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_project_without_harness_is_noop(self):
        result = self.hook("kimi", {"tool_name": "Edit", "tool_input": {"path": INDEX}}, project=self.plain)
        self.assertEqual(result.returncode, 0)

    def test_plugin_skips_where_project_hooks_already_run(self):
        claude = self.hook("plugin", {"tool_name": "Edit", "tool_input": {"file_path": INDEX}},
                           env={"CLAUDE_PROJECT_DIR": str(self.project)})
        self.assertEqual(claude.returncode, 0, "Claude Code runs .claude/settings.json natively")
        codex_hooks = self.project / ".codex/hooks.json"
        codex_hooks.parent.mkdir(exist_ok=True)
        codex_hooks.write_text("{}")
        try:
            codex = self.hook("plugin", {"turn_id": "t1", "tool_name": "Edit", "tool_input": {"file_path": INDEX}})
            self.assertEqual(codex.returncode, 0, "project .codex/hooks.json already wired")
        finally:
            codex_hooks.unlink()

    def test_session_start_returns_context(self):
        result = subprocess.run(["python3", str(ADAPTER), "kimi", "SessionStart"],
                                input=json.dumps({"cwd": str(self.project)}), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        if result.stdout.strip():
            self.assertEqual(json.loads(result.stdout)["hookSpecificOutput"]["hookEventName"], "SessionStart")


class InstallerClientsTest(unittest.TestCase):
    def test_kimi_roles_and_zcode_mcp(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "project"
            project.mkdir()
            git(project, "init", "-q", "-b", "main")
            subprocess.run(["bash", str(ROOT / "install.sh"), "--project", str(project), "--clients", "kimi,zcode",
                            "--skills", "none", "--no-verify"],
                           check=True, capture_output=True, env=dict(os.environ, HOME=str(Path(tmp) / "home")))
            claude = sorted(p.name for p in (project / ".claude/agents").glob("*.md"))
            kimi = sorted(p.name for p in (project / ".agents/agents").glob("*.md"))
            self.assertEqual(claude, kimi, "every role gets a Kimi pointer")
            for name in kimi:
                text = (project / ".agents/agents" / name).read_text()
                self.assertIn(f".claude/agents/{name}", text)
                self.assertRegex(text, r"(?m)^description: \S")
            self.assertEqual(os.readlink(project / ".agents/mcp.json"), "../.mcp.json")


class ManifestTest(unittest.TestCase):
    def test_plugin_manifests_point_at_existing_files(self):
        for manifest in (".claude-plugin/plugin.json", ".codex-plugin/plugin.json", ".kimi-plugin/plugin.json"):
            json.loads((ROOT / manifest).read_text())
        self.assertTrue((ROOT / "skills/x-harness/SKILL.md").is_file())
        self.assertTrue((ROOT / "skills/x-harness-planning/SKILL.md").is_file())
        hooks = json.loads((ROOT / "hooks/hooks.json").read_text())["hooks"]
        kimi = json.loads((ROOT / ".kimi-plugin/plugin.json").read_text())["hooks"]
        self.assertEqual({e for e in hooks}, {h["event"] for h in kimi})
        for text in [json.dumps(hooks), json.dumps(kimi)]:
            self.assertIn("adapters/agent-hook.py", text)

    def test_dsh_bundle_mounts_global_hooks(self):
        """DSH: package.json declares a bundle whose patch mounts the bridge on hooks/dsh-hooks.json (client dsh)."""
        patch = json.loads((ROOT / "package.json").read_text())["dsh"]["bundle"]["patch"]
        text = (ROOT / patch).read_text()
        self.assertIn("@deepseek-ai/dsh-hooks-claude-code", text)
        self.assertIn("node_modules/x-harness/hooks/dsh-hooks.json", text)
        dsh = json.loads((ROOT / "hooks/dsh-hooks.json").read_text())["hooks"]
        self.assertEqual(set(dsh), {"SessionStart", "PreToolUse"})
        commands = [h["command"] for ev in dsh.values() for g in ev for h in g["hooks"]]
        self.assertTrue(any(c.endswith('agent-hook.py" dsh PreToolUse') for c in commands), commands)


if __name__ == "__main__":
    unittest.main()
