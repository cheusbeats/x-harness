#!/usr/bin/env python3
"""Verify complete Codex role installation and portable project configuration."""
from pathlib import Path
import subprocess
import tempfile
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CodexAgentInstallationTest(unittest.TestCase):
    def test_every_claude_agent_is_installed_as_valid_codex_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / 'project'
            project.mkdir()
            subprocess.run(['git', 'init', '-q', str(project)], check=True)
            subprocess.run(['bash', str(ROOT / 'install.sh'), '--project', str(project),
                            '--clients', 'none', '--skills', 'project', '--no-upstream-skills', '--no-verify'],
                           check=True, stdout=subprocess.DEVNULL)
            for client in ('.ai', '.claude', '.agents', '.dsh'):
                with self.subTest(skill_client=client):
                    installed = project / client / 'skills/laravel-clean-code/SKILL.md'
                    self.assertEqual(installed.read_bytes(),
                                     (ROOT / 'harness/.ai/skills/laravel-clean-code/SKILL.md').read_bytes())
            original = {p.stem for p in (project / '.claude/agents').glob('*.md')}
            roles = {p.stem: p for p in (project / '.codex/agents').glob('*.toml')}
            self.assertTrue(original)
            self.assertEqual(set(roles), original)
            for name, path in roles.items():
                with self.subTest(name=name):
                    role = tomllib.loads(path.read_text())
                    self.assertEqual(role['name'], name)
                    self.assertTrue(role['description'].strip())
                    self.assertTrue(role['developer_instructions'].strip())
            config = tomllib.loads((project / '.codex/config.toml').read_text())
            self.assertNotIn('cwd', config['mcp_servers']['laravel-boost'])


if __name__ == '__main__':
    unittest.main()
