"""Поведение .claude/hooks/db-wipe-guard.sh на временном git-репозитории.

Запуск: python3 .claude/hooks/test_db_wipe_guard.py
Блокирует = exit 2, пропускает = exit 0.
"""

# Герметичность: переменные среды Claude Code/git-хука не должны течь в подпроцессы фикстур.
import os as _os
for _v in [k for k in _os.environ if k.startswith("GIT_") or k == "CLAUDE_PROJECT_DIR"]:
    _os.environ.pop(_v, None)

import json
import os
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent / "db-wipe-guard.sh"
GATE = Path(__file__).resolve().parents[1] / "scripts" / "quality-gate.sh"
WIPES = ["migrate:fresh", "migrate:refresh", "migrate:reset", "db:wipe", "db:seed", "migrate --seed", "migrate:fresh --seed --force"]
C = "app-horizon-1"


class DbWipeGuardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.repo = Path(cls.tmp.name) / "repo"
        cls.repo.mkdir()
        subprocess.run(["git", "-C", str(cls.repo), "init", "-q", "-b", "main"], check=True)
        cls.dusk_env = cls.repo / ".env.dusk.local"
        cls.dusk_env.write_text("APP_ENV=local\nDB_HOST=pgsql\nDB_DATABASE=app_dusk\n")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def run_hook(self, command):
        payload = json.dumps({"tool_input": {"command": command}})
        return subprocess.run(["bash", str(HOOK)], input=payload, text=True, capture_output=True, cwd=str(self.repo),
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))

    def assertBlocked(self, command):
        self.assertEqual(2, self.run_hook(command).returncode, "%s должна блокироваться" % command)

    def assertAllowed(self, command):
        result = self.run_hook(command)
        self.assertEqual(0, result.returncode, "%s должна проходить: %s" % (command, result.stderr))

    def test_every_wipe_is_blocked_in_every_launch_form(self):
        forms = [
            "php artisan %s", "./artisan %s", "vendor/bin/sail artisan %s", "vendor/bin/sail art %s", "vendor/bin/sail a %s",
            "./vendor/bin/sail php artisan %s", "vendor/bin/sail exec laravel.test php artisan %s",
            "docker exec " + C + " php artisan %s", "docker exec -w /var/www/html " + C + " php artisan %s",
            "docker exec -it " + C + " php artisan %s", "docker compose exec laravel.test php artisan %s",
            "docker exec " + C + " sh -c 'php artisan %s'", 'bash -c "php artisan %s"', "ssh prod 'cd app && php artisan %s'",
            "git status && php artisan %s", "php artisan %s 2>&1 | tail -3", "cd /x; php artisan %s", "echo $(php artisan %s)",
            "docker exec -i " + C + " bash <<'EOF'\nphp artisan %s\nEOF",
        ]
        for form in forms:
            self.assertBlocked(form % "db:wipe")
        for wipe in WIPES:
            self.assertBlocked("php artisan %s" % wipe)
            self.assertBlocked("docker exec " + C + " php artisan %s" % wipe)
        self.assertBlocked("docker exec " + C + " \\\n  php artisan \\\n  migrate:fresh --force")

    def test_wipe_is_allowed_on_every_test_database(self):
        for db in ["testing", "testing_test_1", "testing_test_12", "app_dusk"]:
            for wipe in WIPES:
                self.assertAllowed("DB_DATABASE=%s php artisan %s" % (db, wipe))
            for form in [
                "env DB_DATABASE=%s php artisan %s",
                "docker exec -e DB_DATABASE=%s " + C + " php artisan %s", "docker exec --env DB_DATABASE=%s " + C + " php artisan %s",
                "docker exec --env=DB_DATABASE=%s " + C + " php artisan %s", "docker exec " + C + " env DB_DATABASE=%s php artisan %s",
                "docker exec " + C + " sh -c 'DB_DATABASE=%s php artisan %s'", "vendor/bin/sail exec -e DB_DATABASE=%s laravel.test php artisan %s",
                "docker exec -e DB_DATABASE=%s " + C + " sh -c 'php artisan %s'",
            ]:
                self.assertAllowed(form % (db, "migrate:fresh --force"))

    def test_comment_or_line_continuation_does_not_hide_a_wipe(self):
        for command in [
            "# reset the db\ndocker exec " + C + " php artisan migrate:fresh --force",
            "# don't keep it\nphp artisan db:wipe",
            "# clear\ndocker exec app-pgsql-1 psql -U sail -d app_main -c 'TRUNCATE users'",
            "cd /tmp # go\nphp artisan db:wipe",
            "echo a#b\nphp artisan db:wipe",
            "php artisan \\\nmigrate:fresh --force",
            "# don't\necho $(php artisan db:wipe)",
        ]:
            self.assertBlocked(command)
        self.assertAllowed("# php artisan db:wipe\necho ok")
        self.assertAllowed("php artisan migrate # not migrate:fresh")

    def test_option_values_do_not_change_the_target(self):
        for command in [
            "dropdb app_main -h testing",
            "dropdb -U testing app_main",
            "psql -d testing --dbname=app_main -c 'TRUNCATE users'",
            "php artisan --env local tinker --execute=\"DB::table('users')->truncate()\"",
            "DB_DATABASE=app_main php artisan --env local dusk",
            "docker exec -e DB_DATABASE=testing c ssh prod php artisan db:wipe",
            "docker exec -e DB_DATABASE=testing c ssh prod 'php artisan db:wipe'",
        ]:
            self.assertBlocked(command)
        self.assertAllowed("dropdb -h pgsql -U sail --if-exists testing_test_3")
        self.assertAllowed("psql -d app_main --dbname=testing -c 'TRUNCATE users'")

    def test_array_command_from_codex_is_checked(self):
        payload = json.dumps({"tool_input": {"command": ["bash", "-lc", "php artisan db:wipe"]}})
        result = subprocess.run(["bash", str(HOOK)], input=payload, text=True, capture_output=True, cwd=str(self.repo),
                                env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(2, result.returncode, result.stderr)

    def test_things_that_only_look_like_a_test_database_are_blocked(self):
        for command in [
            "php artisan --env=testing migrate:fresh",  # .env.testing нет: бьёт по dev-базе
            "php artisan migrate:fresh --env=testing",
            "php artisan migrate:fresh --database=testing",
            "DB_DATABASE=testing docker exec " + C + " php artisan migrate:fresh",  # до контейнера не доходит
            "DB_DATABASE=testing vendor/bin/sail artisan migrate:fresh",
            "DB_DATABASE=testing docker exec " + C + " sh -c 'php artisan db:wipe'",
            "DB_DATABASE=app_main php artisan migrate:fresh",
            "DB_DATABASE=testing_prod php artisan db:wipe",
            "DB_DATABASE=testing_test_x php artisan db:wipe",
            "DB_DATABASE=$DB php artisan db:wipe",
            "docker exec -e DB_DATABASE " + C + " php artisan db:wipe",
            "export DB_DATABASE=testing; php artisan db:wipe",  # лишний блок принят
            "DB_DATABASE=testing php artisan test; php artisan db:wipe",
        ]:
            self.assertBlocked(command)

    def test_sql_through_psql(self):
        psqls = ["psql -U sail -d %s", "psql -U sail %s", "psql --dbname=%s", "psql --dbname %s", "psql -d%s", "psql postgresql://sail:p@pgsql:5432/%s?sslmode=off",
                 "psql 'host=pgsql dbname=%s'", "PGPASSWORD=x psql -h pgsql -U sail -d %s", "PGDATABASE=%s psql",
                 "docker exec app-pgsql-1 psql -U sail -d %s", "docker compose exec pgsql psql -U sail -d %s",
                 "vendor/bin/sail exec pgsql psql -U sail -d %s"]
        for psql in psqls:
            self.assertBlocked("%s -c 'TRUNCATE users'" % (psql % "app_main"))
            self.assertBlocked('%s --command="DROP TABLE users"' % (psql % "app_main"))
            self.assertAllowed("%s -c 'TRUNCATE users'" % (psql % "testing_test_3"))
            self.assertAllowed("%s -c 'SELECT count(*) FROM users'" % (psql % "app_main"))
        for sql in ["TRUNCATE users", "truncate table users", "DROP TABLE users", "drop schema public cascade", "ALTER TABLE u DROP COLUMN a"]:
            self.assertBlocked("psql -d app_main -c '%s'" % sql)
            for db in ["testing", "testing_test_3", "app_dusk"]:
                self.assertAllowed("psql -d %s -c '%s'" % (db, sql))
        for command in [
            "psql -c 'DROP TABLE users'",  # база по умолчанию
            "vendor/bin/sail psql -d testing -c 'DROP TABLE users'",  # sail отбрасывает аргументы
            "vendor/bin/sail psql <<SQL\nTRUNCATE users;\nSQL",
            "PGDATABASE=testing docker exec c psql -c 'DROP TABLE users'",  # до контейнера не доходит
            "echo 'DROP TABLE users' | psql -U sail -d app_main",
            "psql -U sail -d app_main <<'SQL'\nTRUNCATE users;\nSQL",
            "docker exec -i c psql -U sail -d app_main <<SQL\nDROP TABLE users;\nSQL",
            "docker exec c sh -c \"psql -U sail -d app_main -c 'TRUNCATE users'\"",
            "psql -d testing -c 'DROP DATABASE app_main'",  # подключение тестовое, цель рабочая
            "psql -d postgres -c 'DROP DATABASE IF EXISTS app_main'",
            "dropdb app_main",
            "docker exec c dropdb -U sail app_main",
        ]:
            self.assertBlocked(command)
        for command in [
            "psql -d postgres -c 'DROP DATABASE testing_test_3'",
            "psql -d postgres -c 'DROP DATABASE IF EXISTS \"testing_test_3\"'",
            "docker exec -i c psql -U sail -d testing <<SQL\nTRUNCATE users;\nSQL",
            "dropdb testing_test_3",
            "docker exec c dropdb -U sail testing_test_3",
            "psql -d app_main -c \"SELECT 'dropdown'\"",
        ]:
            self.assertAllowed(command)

    def test_sql_through_artisan(self):
        for command in [
            "php artisan tinker --execute=\"DB::statement('TRUNCATE users')\"",
            "php artisan tinker --execute=\"Schema::dropIfExists('users')\"",
            "php artisan tinker --execute=\"DB::table('users')->truncate()\"",
            "echo 'DROP TABLE users' | php artisan db",
            "vendor/bin/sail tinker <<'EOF'\nDB::table('users')->truncate();\nEOF",
            "docker exec " + C + " php artisan tinker --execute=\"Schema::drop('users')\"",
        ]:
            self.assertBlocked(command)
        self.assertAllowed("DB_DATABASE=testing php artisan tinker --execute=\"Schema::drop('users')\"")
        self.assertAllowed("php artisan tinker --execute=\"User::count()\"")

    def test_dusk_goes_only_to_app_dusk(self):
        forms = ["php artisan dusk", "docker exec " + C + " php artisan dusk", "docker exec -w /var/www/html " + C + " php artisan dusk --filter=X",
                 "vendor/bin/sail artisan dusk", "vendor/bin/sail dusk", "vendor/bin/sail dusk:fails", "php artisan dusk:fails"]
        for form in forms:
            self.assertAllowed(form)
        original = self.dusk_env.read_text()
        try:
            for bad in ["DB_DATABASE=app_main\n", "DB_DATABASE=testing\n", "DB_HOST=pgsql\n"]:
                self.dusk_env.write_text(bad)
                for form in forms:
                    self.assertBlocked(form)
            self.dusk_env.unlink()
            for form in forms:
                self.assertBlocked(form)
            self.assertAllowed("DB_DATABASE=app_dusk php artisan dusk")
            self.assertAllowed("docker exec -e DB_DATABASE=app_dusk " + C + " php artisan dusk")
        finally:
            self.dusk_env.write_text(original)
        self.assertBlocked("DB_DATABASE=app_main php artisan dusk")
        self.assertBlocked("docker exec -e DB_DATABASE=testing " + C + " php artisan dusk")
        self.assertAllowed('DB_DATABASE="app_dusk" php artisan dusk')

    def test_dusk_env_is_taken_from_main_checkout_in_a_worktree(self):
        worktree = self.repo / "wt"
        subprocess.run(["git", "-C", str(self.repo), "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "i"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q", str(worktree), "-b", "x"], check=True)
        try:
            payload = json.dumps({"tool_input": {"command": "vendor/bin/sail dusk"}})
            result = subprocess.run(["bash", str(HOOK)], input=payload, text=True, capture_output=True,
                                    env=dict(os.environ, CLAUDE_PROJECT_DIR=str(worktree)))
            self.assertEqual(0, result.returncode, result.stderr)
        finally:
            subprocess.run(["git", "-C", str(self.repo), "worktree", "remove", "-f", str(worktree)], check=True)

    def test_quality_gate_commands_pass(self):
        # Строки PHP-шагов гейта в том виде, как их запускает php_exec, и сам запуск гейта. Dusk идёт через dusk-shards.sh.
        gate = GATE.read_text()
        steps = re.findall(r'^\s*(?:long_)?step "[^"]+"\s+php_exec (.+)$', gate, re.M)
        self.assertTrue(any("artisan test" in s for s in steps), steps)
        self.assertRegex(gate, r'(?m)^\s*long_step "Dusk" .*/dusk-shards\.sh"$')
        # Шарды зовут phpunit напрямую, хук этого не видит: база Dusk закреплена здесь.
        shards = (GATE.parent / "dusk-shards.sh").read_text()
        self.assertIn('db="app_dusk_$1"', shards)
        self.assertIn('-e DB_DATABASE="$db"', shards)
        for step in steps:
            step = re.sub(r'"\$\{[^"]*\}"', "6", step)
            self.assertAllowed("docker exec -w /var/www/html %s %s" % (C, step))
            self.assertAllowed("vendor/bin/sail %s" % step)
        for command in [".claude/scripts/quality-gate.sh", ".claude/scripts/quality-gate.sh --fast", ".claude/scripts/quality-gate.sh --merge",
                        ".claude/scripts/dusk-shards.sh",
                        "vendor/bin/sail artisan test --compact --filter=DropTest", "docker exec " + C + " php artisan test --compact --filter=dusk"]:
            self.assertAllowed(command)

    def test_data_is_not_a_command(self):
        for command in [
            "grep -rn 'migrate:fresh' .claude",
            "grep -n 'DROP TABLE' database/migrations/x.php",
            "rg 'artisan db:wipe' docs",
            "echo php artisan migrate:fresh",
            "cat <<'EOF' > note.md\nphp artisan db:wipe\nEOF",
            "cat > run.sh <<'EOF'\nphp artisan db:wipe\nEOF",
            "git commit -m \"$(cat <<'EOF'\nfix: don't drop php artisan db:wipe\nEOF\n)\"",
            "python3 -c \"print(\\\"don't drop\\\")\"",
            "git commit -m 'block artisan migrate:fresh and db:wipe'",
            "git log --grep='psql -c TRUNCATE'",
            "gh pr create --title x --body 'php artisan db:wipe'",
            "sed -n 1,5p drop.txt",
            "npm run drop",
            "ls database/seeders/db:seed",
            "for f in a b; do grep -n 'php artisan db:wipe' $f; done",
            "if grep -q 'php artisan migrate:fresh' a; then echo y; fi",
        ]:
            self.assertAllowed(command)
        self.assertAllowed("echo ok")
        self.assertAllowed("docker exec " + C + " php artisan migrate --force")
        self.assertAllowed("php artisan migrate")

    def test_broken_command_with_wipe_words_is_blocked(self):
        self.assertBlocked("php artisan db:wipe 'oops")
        self.assertBlocked("docker exec c sh -c \"php artisan db:wipe 'oops\"")
        self.assertAllowed("echo 'oops drop")

    def test_bad_payload_passes(self):
        result = subprocess.run(["bash", str(HOOK)], input="{", text=True, capture_output=True, cwd=str(self.repo),
                                env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)))
        self.assertEqual(0, result.returncode)


if __name__ == "__main__":
    unittest.main()
