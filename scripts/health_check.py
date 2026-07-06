"""
Market Monitor 健康检查
- 遍历所有 com.market-monitor.* launchd 任务
- 记录每次 LastExitStatus
- 连续 N 次失败则推送飞书告警
- 30 分钟内同一任务只告警一次（防刷屏）
"""
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_monitor.core.feishu import send_text  # noqa: E402

STATE_FILE = Path("/tmp/market_monitor_health.json")
FAIL_THRESHOLD = 3          # 连续失败次数
COOLDOWN_SECONDS = 1800     # 告警冷却 30 分钟


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))


def get_monitor_labels() -> list:
    out = subprocess.run(
        ["launchctl", "list"], capture_output=True, text=True
    ).stdout
    labels = []
    for line in out.splitlines():
        parts = line.split()
        # 3 列: PID  Status  Label
        if len(parts) >= 3 and parts[2].startswith("com.market-monitor."):
            labels.append(parts[2])
    return labels


def get_last_exit(label: str):
    """返回 LastExitStatus；查询失败返回 None"""
    out = subprocess.run(
        ["launchctl", "list", label], capture_output=True, text=True
    ).stdout
    for line in out.splitlines():
        if "LastExitStatus" in line:
            # 形如:  "LastExitStatus" = 0;
            try:
                return int(line.rsplit("=", 1)[1].strip().rstrip(";").strip())
            except ValueError:
                return None
    return None


def stderr_tail(label: str, n: int = 8) -> str:
    p = Path(f"/tmp/{label}.err")
    if not p.exists():
        return "(no stderr)"
    lines = p.read_text(errors="replace").splitlines()
    return "\n".join(lines[-n:]) if lines else "(empty)"


def main() -> int:
    state = load_state()
    now = int(time.time())
    alerts = []

    for label in get_monitor_labels():
        exit_code = get_last_exit(label)
        entry = state.get(label, {"fail_streak": 0, "last_alert": 0, "last_exit": 0})

        # exit_code=None 通常表示还没跑过，跳过
        if exit_code is None:
            state[label] = entry
            continue

        if exit_code == 0:
            entry["fail_streak"] = 0
        else:
            entry["fail_streak"] += 1

        entry["last_exit"] = exit_code
        state[label] = entry

        need_alert = (
            entry["fail_streak"] >= FAIL_THRESHOLD
            and (now - entry["last_alert"]) >= COOLDOWN_SECONDS
        )
        if need_alert:
            alerts.append((label, entry["fail_streak"], exit_code, stderr_tail(label)))
            entry["last_alert"] = now

    if alerts:
        blocks = [f"🚨 Market Monitor 健康告警 ({len(alerts)} 个任务连续失败)\n"]
        for label, streak, code, tail in alerts:
            blocks.append(
                f"❌ {label}\n"
                f"   连续失败 {streak} 次 (exit={code})\n"
                f"   stderr 末尾:\n{tail}\n"
            )
        send_text("\n".join(blocks))
        print(f"[health-check] alerted {len(alerts)} tasks")
    else:
        print(f"[health-check] all good ({len(state)} tasks tracked)")

    save_state(state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
