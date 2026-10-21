"""飞牛影视 SRTM 实时监控 主入口。

用法:
    python main.py --config config.yaml

流程:
    加载配置 -> 初始化日志 -> 登录/校验 token -> 解析媒体库 guid ->
    启动多目录监控 -> 事件去抖后触发对应媒体库扫描。
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Dict, List

from fntv_monitor.api_client import FnvClient
from fntv_monitor.config import AppConfig, LibraryMapping, load_config
from fntv_monitor.logger_setup import setup_logging
from fntv_monitor.scanner import ScanCoordinator
from fntv_monitor.watcher import MultiDirWatcher


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="飞牛影视 SRTM 实时监控：监听 .strm 文件变化并触发媒体库扫描",
    )
    parser.add_argument(
        "--config", "-c", default="config.yaml",
        help="配置文件路径（默认 config.yaml）",
    )
    return parser.parse_args()


def resolve_library_ids(
    client: FnvClient,
    mappings: List[LibraryMapping],
    logger: logging.Logger,
) -> Dict[str, str]:
    """解析每个监控目录对应的媒体库 guid。

    配置了 library_id 直接使用；仅配置 library_name 时调用 mdb/list 自动解析。
    """
    resolved: Dict[str, str] = {}
    for mapping in mappings:
        if mapping.library_id:
            resolved[mapping.watch_dir] = mapping.library_id
        else:
            library_id = client.resolve_library_id(mapping.library_name or "")
            resolved[mapping.watch_dir] = library_id
            logger.info("监控目录 %s -> 媒体库 %s（guid=%s）", mapping.watch_dir, mapping.library_name, library_id)
    return resolved


def main() -> int:
    args = parse_args()

    try:
        config: AppConfig = load_config(args.config)
    except Exception as exc:
        print(f"配置加载失败: {exc}", file=sys.stderr)
        return 1

    logger = setup_logging(config.log_dir, config.log_file, config.log_level)
    logger.info("=" * 60)
    logger.info("飞牛影视 SRTM 实时监控启动（版本 1.0.0）")
    logger.info("配置文件: %s", args.config)
    logger.info("NAS 地址: %s", config.nas_url)

    # 初始化 API 客户端：登录或直接使用配置 token
    client = FnvClient(config, logger)
    try:
        if client.token:
            logger.info("使用配置中的 token，跳过登录")
        else:
            client.login()
        library_id_map = resolve_library_ids(client, config.libraries, logger)
    except Exception as exc:
        logger.error("初始化失败: %s", exc)
        return 2

    coordinator = ScanCoordinator(client, logger)
    watcher = MultiDirWatcher(
        config.libraries, library_id_map, config.debounce_seconds,
        coordinator.scan, logger,
    )
    watcher.start()
    logger.info(
        "监控已启动：共 %d 个目录，去抖 %s 秒（Ctrl+C 退出）",
        len(config.libraries), config.debounce_seconds,
    )

    # 优雅退出：SIGINT / SIGTERM
    stop_event = threading.Event()

    def _shutdown(signum: int, _frame) -> None:
        logger.info("收到退出信号 %s，正在停止监控...", signum)
        stop_event.set()

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    try:
        while not stop_event.is_set():
            time.sleep(1)
    finally:
        watcher.stop()
        logger.info("监控已停止，再见")
    return 0


if __name__ == "__main__":
    sys.exit(main())
