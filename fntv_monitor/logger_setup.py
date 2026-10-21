"""日志配置：同时输出到 stdout 与挂载卷文件（支持按大小轮转）。"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

_LOGGER_NAME = "fntv-strm-monitor"


def setup_logging(log_dir: str, log_file: str = "monitor.log", level: str = "INFO") -> logging.Logger:
    """初始化全局日志器。

    - stdout 实时输出（docker logs / 终端）；
    - 文件输出到 {log_dir}/{log_file}（容器内挂载 /logs 卷），10MB 自动轮转保留 5 份。
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(getattr(logging, level, logging.INFO))
    logger.propagate = False

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

    if not logger.handlers:  # 防止重复注册
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(fmt)
        logger.addHandler(stream_handler)

        try:
            os.makedirs(log_dir, exist_ok=True)
            file_handler = RotatingFileHandler(
                os.path.join(log_dir, log_file),
                maxBytes=10 * 1024 * 1024,
                backupCount=5,
                encoding="utf-8",
            )
            file_handler.setFormatter(fmt)
            logger.addHandler(file_handler)
        except OSError as exc:
            logger.warning("日志文件初始化失败，仅输出到 stdout：%s", exc)

    return logger
