"""配置加载与校验。

从 config.yaml 读取运行配置，转换为类型安全的 AppConfig 对象。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import yaml


class ConfigError(Exception):
    """配置错误。"""


@dataclass
class LibraryMapping:
    """媒体库映射：监控目录 -> 飞牛影视媒体库。"""

    watch_dir: str                       # 监控目录（容器内路径，由 docker-compose 挂载）
    library_id: Optional[str] = None     # 媒体库 guid（来自 mdb/list），与 library_name 二选一
    library_name: Optional[str] = None   # 媒体库名称，配置后启动时自动解析为 guid
    recursive: bool = True               # 是否递归监控子目录

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "LibraryMapping":
        watch_dir = str(data.get("watch_dir", "")).strip()
        if not watch_dir:
            raise ConfigError("媒体库映射缺少 watch_dir")
        lib_id = data.get("library_id") or data.get("guid")
        lib_name = data.get("library_name")
        if not lib_id and not lib_name:
            raise ConfigError(f"监控目录 {watch_dir} 的媒体库必须配置 library_id 或 library_name")
        return cls(
            watch_dir=watch_dir,
            library_id=str(lib_id) if lib_id else None,
            library_name=str(lib_name) if lib_name else None,
            recursive=bool(data.get("recursive", True)),
        )


@dataclass
class RetryConfig:
    """指数退避重试参数。"""

    max_retries: int = 5        # 单次请求最大重试次数（网络错误/超时/5xx）
    base_backoff: float = 2.0   # 基础退避秒数：base_backoff * 2^n
    max_backoff: float = 60.0   # 退避上限（秒）
    max_relogin: int = 3        # code=-2 鉴权失效时最多重新登录次数

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RetryConfig":
        return cls(
            max_retries=int(data.get("max_retries", 5)),
            base_backoff=float(data.get("base_backoff", 2.0)),
            max_backoff=float(data.get("max_backoff", 60.0)),
            max_relogin=int(data.get("max_relogin", 3)),
        )


@dataclass
class AppConfig:
    """全局运行配置。"""

    nas_url: str                          # NAS 地址，如 http://192.168.1.100:5666
    secret: str                           # authx 签名 secret（从飞牛影视网页 JS 提取）
    username: Optional[str] = None        # 登录用户名（与 token 二选一）
    password: Optional[str] = None        # 登录密码
    token: Optional[str] = None           # 已登录 token（可选，配置后跳过登录）
    api_key: Optional[str] = None         # 可选 api-key 请求头
    app_name: str = "trimemedia-web"      # 登录接口的 app_name
    libraries: List[LibraryMapping] = field(default_factory=list)
    debounce_seconds: float = 5.0         # 事件去抖静默期（秒）
    timeout: float = 10.0                 # 单次请求超时（秒）
    retry: RetryConfig = field(default_factory=RetryConfig)
    log_dir: str = "/logs"                # 日志目录（容器内为挂载卷）
    log_file: str = "monitor.log"         # 日志文件名
    log_level: str = "INFO"               # 日志级别

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        nas_url = str(data.get("nas_url", "")).strip().rstrip("/")
        if not nas_url:
            raise ConfigError("缺少 nas_url")
        if not nas_url.startswith(("http://", "https://")):
            raise ConfigError("nas_url 必须以 http:// 或 https:// 开头")

        secret = str(data.get("secret", "")).strip()
        if not secret:
            raise ConfigError("缺少 secret（authx 签名密钥）")

        auth = data.get("auth", {}) or {}
        username = auth.get("username")
        password = auth.get("password")
        token = data.get("token") or auth.get("token")
        if not token and not (username and password):
            raise ConfigError("必须配置 token，或同时配置 username + password")

        raw_libs = data.get("libraries")
        if not raw_libs:
            raise ConfigError("缺少 libraries 媒体库映射")
        libraries = [LibraryMapping.from_dict(item) for item in raw_libs]

        debounce = float(data.get("debounce_seconds", 5.0))
        if debounce <= 0:
            raise ConfigError("debounce_seconds 必须大于 0")

        return cls(
            nas_url=nas_url,
            secret=secret,
            username=str(username) if username else None,
            password=str(password) if password else None,
            token=str(token) if token else None,
            api_key=str(data["api_key"]) if data.get("api_key") else None,
            app_name=str(data.get("app_name", "trimemedia-web")),
            libraries=libraries,
            debounce_seconds=debounce,
            timeout=float(data.get("timeout", 10.0)),
            retry=RetryConfig.from_dict(data.get("retry", {}) or {}),
            log_dir=str(data.get("log_dir", "/logs")),
            log_file=str(data.get("log_file", "monitor.log")),
            log_level=str(data.get("log_level", "INFO")).upper(),
        )


def load_config(path: str) -> AppConfig:
    """加载 YAML 配置文件并校验。"""
    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    if not isinstance(raw, dict):
        raise ConfigError(f"配置文件 {path} 格式错误：应为 YAML 字典")
    return AppConfig.from_dict(raw)
