import importlib.util
import pathlib
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SOURCE = pathlib.Path(__file__).resolve().parents[1] / 'profiles/planning/.claude/scripts'

class GateConfigurationTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        subprocess.run(['git', 'init', '-q', '-b', 'hotfix/example', str(self.root)], check=True)
        scripts = self.root / '.claude/scripts'
        scripts.mkdir(parents=True)
        for name in ('quality-gate.sh', 'planning-lib.sh'):
            shutil.copy2(SOURCE / name, scripts / name)
        (self.root / 'tracked').write_text('fixture\n')
        subprocess.run(['git', '-C', str(self.root), 'add', 'tracked'], check=True)
        subprocess.run(['git', '-C', str(self.root), '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)

    def run_gate(self):
        return subprocess.run(['bash', str(self.root / '.claude/scripts/quality-gate.sh'), '--merge'], cwd=self.root, text=True, capture_output=True)

    def test_unconfigured_fast_fails_in_strict_mode(self):
        result = subprocess.run(['bash', str(self.root / '.claude/scripts/quality-gate.sh'), '--fast'], cwd=self.root, text=True, capture_output=True)
        self.assertNotEqual(result.returncode, 0, result.stdout)

    def test_unconfigured_fast_skips_when_strict_off(self):
        (self.root / '.claude/planning.conf').write_text("STRICT=off\n")
        result = subprocess.run(['bash', str(self.root / '.claude/scripts/quality-gate.sh'), '--fast'], cwd=self.root, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_unconfigured_merge_fails_without_stamp(self):
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / '.claude/state/gates/hotfix_example.merge-passed').exists())

    def test_whitespace_only_merge_fails_without_stamp(self):
        (self.root / '.claude/planning.conf').write_text("GATE_MERGE='   '\n")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertFalse((self.root / '.claude/state/gates/hotfix_example.merge-passed').exists())

    def test_configured_success_creates_stamp(self):
        (self.root / '.claude/planning.conf').write_text("GATE_MERGE='true'\n")
        result = self.run_gate()
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = subprocess.check_output(['git', '-C', str(self.root), 'rev-parse', 'HEAD'], text=True).strip()
        self.assertEqual((self.root / '.claude/state/gates/hotfix_example.merge-passed').read_text().splitlines()[0], expected)

    def test_failed_repeat_removes_previous_stamp(self):
        (self.root / '.claude/planning.conf').write_text("GATE_MERGE='test ! -f fail-gate'\n")
        self.assertEqual(self.run_gate().returncode, 0)
        stamp = self.root / '.claude/state/gates/hotfix_example.merge-passed'
        self.assertTrue(stamp.exists())
        (self.root / 'fail-gate').touch()
        self.assertNotEqual(self.run_gate().returncode, 0)
        self.assertFalse(stamp.exists())

    def test_stamp_write_error_fails_gate(self):
        # Команда создаёт каталог вместо файла отметки уже после её удаления.
        (self.root / '.claude/planning.conf').write_text(
            "GATE_MERGE='mkdir -p .claude/state/gates/hotfix_example.merge-passed'\n")
        result = self.run_gate()
        self.assertNotEqual(result.returncode, 0, result.stdout)

class MergeRegistryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = pathlib.Path(self.temp.name)
        scripts = self.root / '.claude/scripts'
        scripts.mkdir(parents=True)
        (scripts / 'registry.sh').write_text('#!/bin/sh\nexit 0\n')
        spec = importlib.util.spec_from_file_location('strict_checks', SOURCE.parent / 'hooks/strict-checks.py')
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)

    def test_merge_tree_error_blocks_even_with_valid_registry(self):
        failed = subprocess.CompletedProcess([], 2, stdout=b'', stderr=b'error')
        with patch.object(self.module, 'git_in', return_value=failed):
            self.assertTrue(self.module.merge_registry_errors(self.root, 'a' * 40, 'main'))

    def test_archive_error_blocks_existing_planning(self):
        tree = subprocess.CompletedProcess([], 0, stdout=b'a' * 40 + b'\n', stderr=b'')
        failed = subprocess.CompletedProcess([], 2, stdout=b'', stderr=b'error')
        (self.root / 'planning').mkdir()
        with patch.object(self.module, 'git_in', side_effect=[tree, failed]):
            self.assertTrue(self.module.merge_registry_errors(self.root, 'a' * 40, 'main'))

if __name__ == '__main__':
    unittest.main()
