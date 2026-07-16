"""配置加载"""
import os
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = PROJECT_ROOT / "config" / "config.yaml"


class Config:
    """全局配置对象"""

    def __init__(self, path: Path = CONFIG_PATH):
        if yaml is None:
            raise ImportError("请先安装 pyyaml: pip3 install --break-system-packages pyyaml")
        if not path.exists():
            raise FileNotFoundError(
                f"配置文件不存在: {path}\n"
                f"请复制 config/config.example.yaml → config/config.yaml 并填入凭据"
            )
        with open(path, encoding="utf-8") as f:
            self._data = yaml.safe_load(f)

    def get(self, path: str, default=None):
        """按 dot path 取值，例: get('stabilize.symbols')"""
        node = self._data
        for key in path.split("."):
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                return default
        return node

    # ==== 飞书凭据 ====
    # 优先级: 环境变量 > config.yaml
    @property
    def feishu_app_id(self):
        return os.environ.get("FEISHU_APP_ID") or self.get("feishu.app_id")

    @property
    def feishu_app_secret(self):
        return os.environ.get("FEISHU_APP_SECRET") or self.get("feishu.app_secret")

    @property
    def feishu_user_id(self):
        return os.environ.get("FEISHU_USER_ID") or self.get("common.feishu_user_id")

    # ==== AI 凭据 ====
    # 优先级: 环境变量 > config.yaml
    @property
    def ai_base_url(self):
        return os.environ.get("AI_BASE_URL") or self.get("ai.base_url")

    @property
    def ai_api_key(self):
        return os.environ.get("AI_API_KEY") or self.get("ai.api_key")

    @property
    def ai_model(self):
        return self.get("ai.model", "qwen3.7-plus")

    # ==== 通用 ====
    @property
    def state_dir(self):
        return os.path.expanduser(self.get("common.state_dir", "/tmp"))

    @property
    def log_dir(self):
        return os.path.expanduser(self.get("common.log_dir", str(PROJECT_ROOT / "logs")))


_config_instance = None


def get_config() -> Config:
    """获取单例配置"""
    global _config_instance
    if _config_instance is None:
        _config_instance = Config()
    return _config_instance


def reload_config():
    """重载配置（测试用）"""
    global _config_instance
    _config_instance = None
    return get_config()
