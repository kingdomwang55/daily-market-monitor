"""Local environment and project invariant checks."""
from __future__ import annotations

import os
import plistlib
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import yaml
except ImportError:  # pragma: no cover - covered by runtime doctor message
    yaml = None

from .db_path import ensure_sqlite_parent, sqlite_db_path, sqlite_path_from_url
from .config import CONFIG_PATH, PROJECT_ROOT
from ..monitors.registry import REGISTRY, list_monitors


EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "config" / "config.example.yaml"
REQUIRED_CONFIG_SECTIONS = (
    "common",
    "feishu",
    "stabilize",
    "price_alert",
    "us_market",
    "hk_market",
    "shock",
    "morning_report",
    "evening_report",
    "ai",
)
PLACEHOLDER_VALUES = {
    "",
    "YOUR_OPEN_ID",
    "YOUR_APP_ID",
    "YOUR_APP_SECRET",
    "YOUR_API_KEY",
}


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    ok: bool
    message: str


def _ok(name: str, message: str) -> DoctorCheck:
    return DoctorCheck(name, True, message)


def _fail(name: str, message: str) -> DoctorCheck:
    return DoctorCheck(name, False, message)


def check_python() -> DoctorCheck:
    required = (3, 9)
    current = sys.version_info[:3]
    if current >= required:
        return _ok("python", f"{sys.executable} ({current[0]}.{current[1]}.{current[2]})")
    return _fail("python", "Python 3.9+ is required")


def check_registry() -> DoctorCheck:
    monitors = list_monitors()
    if len(monitors) != len(REGISTRY):
        return _fail("registry", "registry/list_monitors count mismatch")
    names = [m["name"] for m in monitors]
    if not names:
        return _fail("registry", "no monitors registered")
    return _ok("registry", f"{len(names)} monitors: {', '.join(names)}")


def check_launchd_templates(root: Path = PROJECT_ROOT) -> DoctorCheck:
    launchd_dir = Path(os.environ.get("MARKET_MONITOR_LAUNCHD_DIR", root / "launchd"))
    plists = sorted(launchd_dir.glob("com.market-monitor.*.plist"))
    if not plists:
        return _fail("launchd", f"no plist files found in {launchd_dir}")

    stale_path_offenders = []
    for plist in plists:
        try:
            payload = plistlib.loads(plist.read_bytes())
        except Exception as e:
            return _fail("launchd", f"{plist.name} is not valid plist: {e}")

        expected_root = str(root)
        working_dir = payload.get("WorkingDirectory")
        pythonpath = (payload.get("EnvironmentVariables") or {}).get("PYTHONPATH")
        if working_dir != expected_root or pythonpath != expected_root:
            stale_path_offenders.append(plist.name)

    if stale_path_offenders:
        return _fail("launchd", "stale project path in " + ", ".join(stale_path_offenders))
    return _ok("launchd", f"{len(plists)} plist files target {root}")


def check_config_exists(config_path: Path = CONFIG_PATH) -> DoctorCheck:
    if config_path.exists():
        return _ok("config", f"found {config_path}")
    rel = config_path.relative_to(PROJECT_ROOT)
    return _fail("config", f"missing {rel}; copy config/config.example.yaml to {rel}")


def _is_placeholder(value) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return stripped in PLACEHOLDER_VALUES or stripped.startswith("YOUR_")


def check_config_file(
    config_path: Path = CONFIG_PATH,
    require_credentials: bool = True,
) -> DoctorCheck:
    if yaml is None:
        return _fail("config", "pyyaml is not installed")
    if not config_path.exists():
        return check_config_exists(config_path)

    try:
        payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        return _fail("config", f"invalid yaml in {config_path}: {e}")

    if not isinstance(payload, dict):
        return _fail("config", "config root must be a mapping")

    missing = [name for name in REQUIRED_CONFIG_SECTIONS if name not in payload]
    if missing:
        return _fail("config", "missing sections: " + ", ".join(missing))

    common = payload.get("common") or {}
    if not isinstance(common, dict):
        return _fail("config", "common must be a mapping")
    for key in ("state_dir", "log_dir"):
        if not isinstance(common.get(key), str) or not common.get(key).strip():
            return _fail("config", f"common.{key} must be a non-empty string")

    feishu = payload.get("feishu") or {}
    if not isinstance(feishu, dict):
        return _fail("config", "feishu must be a mapping")

    for section in (
        "stabilize",
        "price_alert",
        "us_market",
        "hk_market",
        "shock",
        "morning_report",
        "evening_report",
        "ai",
    ):
        node = payload.get(section)
        if not isinstance(node, dict):
            return _fail("config", f"{section} must be a mapping")
        if "enabled" in node and not isinstance(node["enabled"], bool):
            return _fail("config", f"{section}.enabled must be true or false")

    if require_credentials:
        credential_values = {
            "common.feishu_user_id": os.environ.get("FEISHU_USER_ID") or common.get("feishu_user_id"),
            "feishu.app_id": os.environ.get("FEISHU_APP_ID") or feishu.get("app_id"),
            "feishu.app_secret": os.environ.get("FEISHU_APP_SECRET") or feishu.get("app_secret"),
        }
        placeholders = [
            key for key, value in credential_values.items()
            if _is_placeholder(value)
        ]
        if placeholders:
            return _fail("config", "placeholder credentials: " + ", ".join(placeholders))

    return _ok("config", f"validated {config_path}")


def check_runtime_dirs() -> DoctorCheck:
    writable = []
    for label, raw_path in [
        ("tmp", "/tmp"),
        ("project", str(PROJECT_ROOT)),
    ]:
        path = Path(os.path.expanduser(raw_path))
        if os.access(path, os.W_OK):
            writable.append(label)
    if "tmp" in writable and "project" in writable:
        return _ok("writable", "/tmp and project directory are writable")
    return _fail("writable", "expected /tmp and project directory to be writable")


def check_database_url() -> DoctorCheck:
    db_url = os.environ.get("MARKET_DB_URL")
    sqlite_path = sqlite_path_from_url(db_url) if db_url else sqlite_db_path()
    if sqlite_path is not None:
        try:
            ensure_sqlite_parent(sqlite_path)
        except Exception as e:
            return _fail("database", f"cannot create sqlite parent for {sqlite_path}: {e}")
        return _ok("database", f"sqlite path {sqlite_path}")
    return _ok("database", f"non-sqlite MARKET_DB_URL configured: {db_url}")


def run_checks(ci: bool = False) -> list[DoctorCheck]:
    checks = [
        check_python(),
        check_registry(),
        check_launchd_templates(PROJECT_ROOT),
        check_runtime_dirs(),
        check_database_url(),
    ]
    if ci:
        checks.append(check_config_file(EXAMPLE_CONFIG_PATH, require_credentials=False))
    else:
        checks.append(check_config_file(CONFIG_PATH, require_credentials=True))
    return checks


def format_checks(checks: Iterable[DoctorCheck]) -> str:
    lines = []
    for check in checks:
        mark = "OK" if check.ok else "FAIL"
        lines.append(f"[{mark}] {check.name}: {check.message}")
    return "\n".join(lines)


def exit_code(checks: Iterable[DoctorCheck]) -> int:
    return 0 if all(check.ok for check in checks) else 1
