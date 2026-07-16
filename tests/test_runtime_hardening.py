"""Runtime hardening tests for logs, state, and packaging metadata."""
import io
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 fallback
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


class PushLoggerTests(unittest.TestCase):
    def test_push_logger_uses_configured_log_dir(self):
        from market_monitor.core import push_logger

        class DummyConfig:
            log_dir = None

        with tempfile.TemporaryDirectory() as tmp:
            DummyConfig.log_dir = tmp
            with mock.patch("market_monitor.core.push_logger.get_config", return_value=DummyConfig()):
                push_logger.append("hello", push_type="test")
                records = push_logger.read_day()

            files = list(Path(tmp).glob("push_*.jsonl"))

        self.assertEqual(len(files), 1)
        self.assertEqual(records[0]["message"], "hello")
        self.assertEqual(records[0]["type"], "test")

    def test_cli_logs_reads_configured_log_dir(self):
        from market_monitor import cli

        class DummyConfig:
            log_dir = None

        with tempfile.TemporaryDirectory() as tmp:
            DummyConfig.log_dir = tmp
            Path(tmp, "demo.log").write_text("configured log\n", encoding="utf-8")
            args = type("Args", (), {"name": "demo", "tail": None})()

            stdout = io.StringIO()
            with mock.patch("market_monitor.cli.get_config", return_value=DummyConfig()):
                with mock.patch("sys.stdout", stdout):
                    cli.cmd_logs(args)

        self.assertIn("configured log", stdout.getvalue())


class StateTests(unittest.TestCase):
    def test_state_save_reports_write_failures(self):
        from market_monitor.core.state import State

        class DummyConfig:
            state_dir = "/tmp"

        with mock.patch("market_monitor.core.state.get_config", return_value=DummyConfig()):
            state = State("unit")

        state.set("x", True)
        stderr = io.StringIO()
        with mock.patch("builtins.open", side_effect=OSError("disk full")):
            with mock.patch("sys.stderr", stderr):
                state.save()

        self.assertIn("保存状态失败", stderr.getvalue())
        self.assertIn("disk full", stderr.getvalue())


class DoctorTests(unittest.TestCase):
    def test_launchd_check_rejects_stale_project_paths(self):
        from market_monitor.core.doctor import check_launchd_templates

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            launchd = root / "launchd"
            launchd.mkdir()
            (launchd / "com.market-monitor.demo.plist").write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>WorkingDirectory</key>
  <string>/some/other/project</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>/some/other/project</string>
  </dict>
</dict>
</plist>
                """,
                encoding="utf-8",
            )

            result = check_launchd_templates(root)

        self.assertFalse(result.ok)
        self.assertIn("stale project path", result.message)

    def test_launchd_check_can_use_overridden_template_directory(self):
        from market_monitor.core.doctor import check_launchd_templates

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp, "project")
            root.mkdir()
            launchd = Path(tmp, "generated")
            launchd.mkdir()
            (launchd / "com.market-monitor.demo.plist").write_text(
                f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.market-monitor.demo</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>-m</string>
    <string>market_monitor.cli</string>
    <string>run</string>
    <string>demo</string>
  </array>
  <key>WorkingDirectory</key>
  <string>{root}</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PYTHONPATH</key>
    <string>{root}</string>
  </dict>
</dict>
</plist>
                """,
                encoding="utf-8",
            )

            with mock.patch("market_monitor.core.doctor.PROJECT_ROOT", root):
                with mock.patch.dict("os.environ", {"MARKET_MONITOR_LAUNCHD_DIR": str(launchd)}):
                    result = check_launchd_templates(root)

        self.assertTrue(result.ok, result.message)

    def test_config_check_rejects_invalid_yaml(self):
        from market_monitor.core import doctor

        class FakeYaml:
            @staticmethod
            def safe_load(_text):
                raise ValueError("bad yaml")

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.yaml")
            config.write_text("common: [broken\n", encoding="utf-8")

            with mock.patch.object(doctor, "yaml", FakeYaml):
                result = doctor.check_config_file(config, require_credentials=False)

        self.assertFalse(result.ok)
        self.assertIn("invalid yaml", result.message)

    def test_config_check_rejects_missing_required_sections(self):
        from market_monitor.core import doctor

        class FakeYaml:
            @staticmethod
            def safe_load(_text):
                return {
                    "common": {
                        "state_dir": "/tmp",
                        "log_dir": "/tmp",
                    },
                    "stabilize": {
                        "enabled": True,
                    },
                }

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.yaml")
            config.write_text(
                """
common:
  state_dir: /tmp
  log_dir: /tmp
stabilize:
  enabled: true
                """,
                encoding="utf-8",
            )

            with mock.patch.object(doctor, "yaml", FakeYaml):
                result = doctor.check_config_file(config, require_credentials=False)

        self.assertFalse(result.ok)
        self.assertIn("missing sections", result.message)

    def test_config_check_rejects_placeholder_credentials_when_required(self):
        from market_monitor.core import doctor

        class FakeYaml:
            @staticmethod
            def safe_load(_text):
                return {
                    "common": {
                        "feishu_user_id": "YOUR_OPEN_ID",
                        "state_dir": "/tmp",
                        "log_dir": "/tmp",
                    },
                    "feishu": {
                        "app_id": "YOUR_APP_ID",
                        "app_secret": "YOUR_APP_SECRET",
                    },
                    "stabilize": {"enabled": True},
                    "price_alert": {"enabled": True},
                    "us_market": {"enabled": True},
                    "hk_market": {"enabled": True},
                    "shock": {"enabled": True},
                    "morning_report": {"enabled": True},
                    "evening_report": {"enabled": True},
                    "ai": {"enabled": True},
                }

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.yaml")
            config.write_text(Path(ROOT, "config", "config.example.yaml").read_text(encoding="utf-8"), encoding="utf-8")

            with mock.patch.object(doctor, "yaml", FakeYaml):
                result = doctor.check_config_file(config, require_credentials=True)

        self.assertFalse(result.ok)
        self.assertIn("placeholder credentials", result.message)

    def test_config_check_requires_feishu_section(self):
        from market_monitor.core import doctor

        class FakeYaml:
            @staticmethod
            def safe_load(_text):
                return {
                    "common": {"state_dir": "/tmp", "log_dir": "/tmp"},
                    "stabilize": {"enabled": True},
                    "price_alert": {"enabled": True},
                    "us_market": {"enabled": True},
                    "hk_market": {"enabled": True},
                    "shock": {"enabled": True},
                    "morning_report": {"enabled": True},
                    "evening_report": {"enabled": True},
                    "ai": {"enabled": True},
                }

        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp, "config.yaml")
            config.write_text("{}", encoding="utf-8")

            with mock.patch.object(doctor, "yaml", FakeYaml):
                result = doctor.check_config_file(config, require_credentials=False)

        self.assertFalse(result.ok)
        self.assertIn("missing sections: feishu", result.message)

    def test_example_config_passes_schema_when_credentials_are_not_required(self):
        from market_monitor.core.doctor import check_config_file

        result = check_config_file(Path(ROOT, "config", "config.example.yaml"), require_credentials=False)

        self.assertTrue(result.ok, result.message)

    def test_doctor_reports_configured_sqlite_database_path(self):
        from market_monitor.core.doctor import check_database_url

        with mock.patch.dict("os.environ", {"MARKET_DB_URL": "sqlite:////tmp/doctor-market.db"}):
            result = check_database_url()

        self.assertTrue(result.ok, result.message)
        self.assertIn("/tmp/doctor-market.db", result.message)


class FeishuTransportTests(unittest.TestCase):
    def test_send_text_does_not_shell_out_with_credentials(self):
        from market_monitor.core import feishu

        class DummyConfig:
            feishu_app_id = "app"
            feishu_app_secret = "secret"
            feishu_user_id = "user"

        class DummyResponse:
            def __init__(self, body):
                self.body = body

            def read(self):
                return self.body

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

        responses = [
            DummyResponse(b'{"code":0,"tenant_access_token":"tenant"}'),
            DummyResponse(b'{"code":0}'),
        ]

        with mock.patch("market_monitor.core.feishu.get_config", return_value=DummyConfig()):
            with mock.patch("subprocess.run") as shell:
                shell.side_effect = AssertionError("credentials must not be sent via argv")
                with mock.patch("market_monitor.core.feishu.urllib.request.urlopen", side_effect=responses):
                    with mock.patch("market_monitor.core.feishu.push_logger.append") as append:
                        ok = feishu.send_text("hello", push_type="unit")

        self.assertTrue(ok)
        self.assertFalse(shell.called)
        append.assert_called_once()


class PackagingMetadataTests(unittest.TestCase):
    def test_runtime_dependencies_cover_import_time_modules(self):
        data = tomllib.loads(Path(ROOT, "pyproject.toml").read_text(encoding="utf-8"))
        dependencies = "\n".join(data["project"]["dependencies"]).lower()

        self.assertIn("requests", dependencies)
        self.assertIn("pandas", dependencies)


class DatabasePathTests(unittest.TestCase):
    def test_sqlite_db_path_follows_market_db_url(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from market_monitor.data.database import db_info;"
                    "print(db_info()['path'])"
                ),
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "MARKET_DB_URL": "sqlite:////tmp/market-monitor-custom.db",
            },
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "/tmp/market-monitor-custom.db")

    def test_direct_sqlite_cache_modules_share_market_db_url_path(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "from market_monitor.core import ah_premium, etf_premium, index_valuation, cigar_butt;"
                    "print(ah_premium._DB_PATH);"
                    "print(etf_premium._DB_PATH);"
                    "print(index_valuation._DB_PATH);"
                    "print(cigar_butt._DB_PATH)"
                ),
            ],
            cwd=ROOT,
            env={
                **os.environ,
                "MARKET_DB_URL": "sqlite:////tmp/market-monitor-cache.db",
            },
            text=True,
            capture_output=True,
            timeout=10,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        paths = result.stdout.strip().splitlines()
        self.assertEqual(paths, ["/tmp/market-monitor-cache.db"] * 4)

    def test_direct_sqlite_cache_modules_create_parent_for_custom_db_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "nested", "cache.db")
            result = subprocess.run(
                [
                    sys.executable,
                    "-c",
                    (
                        "from market_monitor.core import index_valuation, cigar_butt;"
                        "index_valuation._init_snapshot_table();"
                        "cigar_butt._init_table();"
                        "print(index_valuation._DB_PATH.exists());"
                        "print(cigar_butt._DB_PATH.exists())"
                    ),
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "MARKET_DB_URL": f"sqlite:///{db_path}",
                },
                text=True,
                capture_output=True,
                timeout=10,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().splitlines(), ["True", "True"])


class AlembicMigrationTests(unittest.TestCase):
    def test_alembic_upgrade_head_builds_schema_on_custom_database(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp, "migrated.db")
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "alembic",
                    "-c",
                    "alembic.ini",
                    "upgrade",
                    "head",
                ],
                cwd=ROOT,
                env={
                    **os.environ,
                    "MARKET_DB_URL": f"sqlite:///{db_path}",
                },
                text=True,
                capture_output=True,
                timeout=20,
            )

            self.assertEqual(result.returncode, 0, result.stderr)

            import sqlite3

            conn = sqlite3.connect(db_path)
            try:
                names = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            finally:
                conn.close()

        self.assertIn("alembic_version", names)
        self.assertIn("monitor_registry", names)
        self.assertIn("paper_trade", names)


class ContinuousIntegrationTests(unittest.TestCase):
    def test_ci_workflow_runs_core_verification_commands(self):
        workflow = Path(ROOT, ".github", "workflows", "ci.yml")
        self.assertTrue(workflow.exists(), "missing .github/workflows/ci.yml")

        body = workflow.read_text(encoding="utf-8")
        self.assertIn("bash scripts/verify.sh", body)

    def test_install_script_runs_doctor_before_loading_launchd(self):
        body = Path(ROOT, "scripts", "install.sh").read_text(encoding="utf-8")

        self.assertIn("market_monitor.cli doctor --ci", body)
        self.assertLess(
            body.index("market_monitor.cli doctor --ci"),
            body.index("launchctl load"),
        )

    def test_install_script_uses_same_python_for_generation_and_doctor(self):
        body = Path(ROOT, "scripts", "install.sh").read_text(encoding="utf-8")

        self.assertIn('PYTHON_BIN="${MARKET_MONITOR_PYTHON:-python3}"', body)
        self.assertIn('MARKET_MONITOR_PYTHON="$PYTHON_BIN" "$PYTHON_BIN" "$PROJECT_ROOT/scripts/gen_launchd.py"', body)

    def test_verify_script_runs_local_quality_gates(self):
        script = Path(ROOT, "scripts", "verify.sh")
        self.assertTrue(script.exists(), "missing scripts/verify.sh")

        body = script.read_text(encoding="utf-8")
        self.assertIn('PYTHON_BIN="${PYTHON_BIN:-python3}"', body)
        self.assertIn('"$PYTHON_BIN" -m unittest discover -s tests -v', body)
        self.assertIn('"$PYTHON_BIN" tests/test_data_source.py', body)
        self.assertIn('"$PYTHON_BIN" -m compileall -q market_monitor scripts tests', body)
        self.assertIn('"$PYTHON_BIN" -m market_monitor.cli list', body)
        self.assertIn('MARKET_MONITOR_LAUNCHD_DIR="$tmp_launchd"', body)
        self.assertIn('MARKET_MONITOR_LAUNCHD_DIR="$tmp_launchd" "$PYTHON_BIN" -m market_monitor.cli doctor --ci', body)
        self.assertIn('MARKET_DB_URL="sqlite:///$tmp_db/market.db" "$PYTHON_BIN" -m alembic -c alembic.ini upgrade head', body)


if __name__ == "__main__":
    unittest.main()
