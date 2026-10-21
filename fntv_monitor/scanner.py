"""扫描触发协调器：把监控事件转换为媒体库扫描 API 调用并记录日志。"""
from __future__ import annotations

import logging
import time
from typing import Optional

from .api_client import FnvClient, FnvApiError


class ScanCoordinator:
    """接收目录去抖回调，调用飞牛影视触发扫描接口。"""

    def __init__(self, client: FnvClient, logger: logging.Logger) -> None:
        self._client = client
        self._logger = logger

    def scan(self, library_id: str, created: int, deleted: int) -> None:
        """触发指定媒体库扫描，记录触发时间与结果。

        参数:
            library_id: 媒体库 guid（mdb/list 中的 guid）；
            created:    本次去抖窗口内新增的 strm 数量；
            deleted:    本次去抖窗口内删除的 strm 数量。
        """
        started_at = time.time()
        # 日志：记录触发扫描时间与原因（对应新增/删除事件）
        self._logger.info(
            "触发媒体库扫描 library_id=%s（新增 %d / 删除 %d strm）",
            library_id, created, deleted,
        )
        try:
            self._client.trigger_scan(library_id)
            self._logger.info(
                "扫描指令已发送成功 library_id=%s，耗时 %.2f 秒",
                library_id, time.time() - started_at,
            )
        except Exception as exc:
            self._logger.error("触发扫描失败 library_id=%s：%s", library_id, exc)
