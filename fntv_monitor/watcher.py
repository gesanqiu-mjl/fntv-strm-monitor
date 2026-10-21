"""基于 watchdog 的 .strm 目录监控与事件去抖。

多目录并行监听；每个目录内的 strm 新增/删除/移动事件先记入待处理列表，
去抖静默期（debounce_seconds）内事件合并，静默期结束后只触发一次
对应媒体库扫描。
"""
from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .config import LibraryMapping

# 回调签名：去抖结束后上报本次合并的新增/删除数量
TriggerCallback = Callable[[int, int], None]


@dataclass
class _DirState:
    """单个监控目录的事件去抖状态。"""

    mapping: LibraryMapping
    timer: Optional[threading.Timer] = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    created: List[str] = field(default_factory=list)   # 本次去抖窗口内新增的 strm 路径
    deleted: List[str] = field(default_factory=list)   # 本次去抖窗口内删除的 strm 路径


class StrmEventHandler(FileSystemEventHandler):
    """只关心 .strm 文件事件，并对高频事件做去抖合并。"""

    def __init__(
        self,
        mapping: LibraryMapping,
        debounce_seconds: float,
        on_trigger: TriggerCallback,
        logger: logging.Logger,
    ) -> None:
        self._mapping = mapping
        self._debounce = debounce_seconds
        self._on_trigger = on_trigger
        self._logger = logger
        self._state = _DirState(mapping=mapping)

    # ------------------------------------------------------------ 事件入口

    def on_created(self, event) -> None:
        self._register("created", event.src_path)

    def on_deleted(self, event) -> None:
        self._register("deleted", event.src_path)

    def on_moved(self, event) -> None:
        """移动/重命名：源路径视为删除，目标路径视为新增。"""
        if str(event.src_path).lower().endswith(".strm"):
            self._register("deleted", event.src_path)
        if str(event.dest_path).lower().endswith(".strm"):
            self._register("created", event.dest_path)

    # ---------------------------------------------------------------- 内部

    def _register(self, event_type: str, path: str) -> None:
        """记录事件（仅 .strm）并重启去抖计时器。"""
        if not str(path).lower().endswith(".strm"):
            return
        state = self._state
        with state.lock:
            if event_type == "created":
                state.created.append(path)
            else:
                state.deleted.append(path)
            # 日志：记录 strm 新增/删除时间
            self._logger.info(
                "strm %s: %s（监控目录 %s）",
                "新增" if event_type == "created" else "删除",
                path,
                self._mapping.watch_dir,
            )

            if state.timer is not None:
                state.timer.cancel()
            state.timer = threading.Timer(self._debounce, self._flush)
            state.timer.daemon = True
            state.timer.start()

    def _flush(self) -> None:
        """去抖静默期结束：统计本次合并结果并触发扫描回调。"""
        state = self._state
        with state.lock:
            created = list(state.created)
            deleted = list(state.deleted)
            state.created.clear()
            state.deleted.clear()
            state.timer = None
        if not created and not deleted:
            return

        self._logger.info(
            "去抖结束：目录 %s 本次新增 %d 个 / 删除 %d 个 strm，准备触发媒体库扫描",
            self._mapping.watch_dir, len(created), len(deleted),
        )
        try:
            self._on_trigger(len(created), len(deleted))
        except Exception:
            self._logger.exception("触发扫描回调执行异常")

    def cancel_pending(self) -> None:
        """取消尚未触发的去抖计时器（用于优雅退出）。"""
        with self._state.lock:
            if self._state.timer is not None:
                self._state.timer.cancel()
                self._state.timer = None


class MultiDirWatcher:
    """同时监控多个 strm 目录，每个目录映射独立媒体库。"""

    def __init__(
        self,
        mappings: List[LibraryMapping],
        library_id_map: Dict[str, str],
        debounce_seconds: float,
        on_trigger: TriggerCallback,
        logger: logging.Logger,
    ) -> None:
        self._observer = Observer()
        self._handlers: List[StrmEventHandler] = []
        for mapping in mappings:
            library_id = library_id_map[mapping.watch_dir]

            def _trigger(created: int, deleted: int, _lib_id: str = library_id) -> None:
                on_trigger(_lib_id, created, deleted)

            handler = StrmEventHandler(mapping, debounce_seconds, _trigger, logger)
            path = str(mapping.watch_dir)
            Path(path).mkdir(parents=True, exist_ok=True)  # 监控目录不存在时自动创建
            self._observer.schedule(handler, path, recursive=mapping.recursive)
            self._handlers.append(handler)
            logger.info(
                "已注册监控目录 %s（媒体库 %s，递归=%s）",
                path, library_id, mapping.recursive,
            )

    def start(self) -> None:
        """启动观察线程。"""
        self._observer.start()

    def stop(self) -> None:
        """停止观察线程并取消未触发的去抖计时器。"""
        for handler in self._handlers:
            handler.cancel_pending()
        self._observer.stop()
        self._observer.join(timeout=10)
