"""配置加载"""
import os
import json
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"
OPENCLAW_CONFIG = Path.home() / ".openclaw" / "openclaw.json"


class Config:
    """全局配置对象"""

    def __init__(self, path: Path = CONFIG_PATH):
        if yaml is None:
            raise ImportError("请先安装 pyyaml: pip install pyyaml")
        if not path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {path}\n"
                f"请复制 config/config.example.yaml → config/config.yaml"
            )
        with open(path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

        self._load_openclaw_secrets()

    def _load_openclaw_secrets(self):
        """从 ~/.openclaw/openclaw.json 加载敏感凭据"""
        if not OPENCLAW_CONFIG.exists():
            self._feishu_app_id = None
            self._feishu_app_secret = None
            self._ai_base_url = None
            self._ai_api_key = None
            return

        with open(OPENCLAW_CONFIG) as f:
            cfg = json.load(f)

        # 飞书
        fs = cfg.get("channels", {}).get("feishu", {})
        self._feishu_app_id = fs.get("appId")
        self._feishu_app_secret = fs.get("appSecret")

        # AI provider
        providers = cfg.get("models", {}).get("providers", {})
        provider_name = self.get("ai.provider", "custom")
        ai_cfg = providers.get(provider_name, {})
        self._ai_base_url = ai_cfg.get("baseUrl") or ai_cfg.get("base_url")
        self._ai_api_key = ai_cfg.get("apiKey") or ai_cfg.get("api_key")

    def get(self, path: str, default=None):
        """按 dot path 取值，例: get('stabilize.symbols')"""
        node = self._data
        for key in path.split("."):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    # ==== 便捷属性 ====
    @property
    def feishu_app_id(self):
        return self._feishu_app_id

    @property
    def feishu_app_secret(self):
        return self._feishu_app_secret

    @property
    def feishu_user_id(self):
        return self.get("common.feishu_user_id")

    @property
    def state_dir(self):
        return os.path.expanduser(self.get("common.state_dir", "/tmp"))

    @property
    def log_dir(self):
        return os.path.expanduser(self.get("common.log_dir", "~/projects/market-monitor/logs"))

    @property
    def ai_base_url(self):
        return self._ai_base_url

    @property
    def ai_api_key(self):
        return self._ai_api_key

    @property
    def ai_model(self):
        return self.get("ai.model", "deepseek-v4-flash")


_config_instance = None


def get_config() -> Config:
    """获取单例配置"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance
