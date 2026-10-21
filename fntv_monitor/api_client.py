"""飞牛影视（fnOS 影视）HTTP API 客户端。

接口依据 fntv_api_notes.md 调研笔记实现：
- 登录:      POST /v/api/v1/login            （body: username/password/app_name + authx）
- 媒体库列表: GET /v/api/v1/mdb/list          （Authorization + authx）
- 触发扫描:   POST /v/api/v1/mdb/scan/{guid}  （Authorization + Content-Type + authx）
- authx:     cse 签名头 nonce=<6位数字>&timestamp=<毫秒>&sign=<MD5>
- code == -2 : 鉴权失效，自动重新登录后重试当前请求
- code == -14: 已有扫描任务在跑，视为成功忽略
"""
from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from .config import AppConfig


class FnvApiError(Exception):
    """飞牛影视 API 业务错误（code != 0 且不可忽略）。"""


class FnvRetryExhausted(Exception):
    """重试次数耗尽。"""


def _md5(text: str) -> str:
    """计算 UTF-8 文本的 MD5 十六进制摘要。"""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def build_authx(
    method: str,
    path: str,
    secret: str,
    params: Optional[Dict[str, Any]] = None,
    body: Optional[Dict[str, Any]] = None,
) -> str:
    """构造 authx cse 签名头（每个请求实时计算）。

    签名步骤（见调研笔记第 6 节）：
    1. nonce: 6 位随机数字；timestamp: 毫秒时间戳；
    2. body_hash:
       - GET: 对 params 按 key 排序后 urlencode，再做 MD5（无参数时为空串 MD5）；
       - 非 GET: 请求体 JSON 排序+紧凑序列化（separators=(',', ':'), sort_keys=True），再做 MD5；
    3. sign = MD5(路径 + nonce + timestamp + body_hash + secret)。
    """
    nonce = f"{random.randint(100000, 999999):06d}"
    timestamp = str(int(time.time() * 1000))

    if method.upper() == "GET":
        query = urlencode({key: params[key] for key in sorted(params)}) if params else ""
        body_hash = _md5(query)
    else:
        payload = json.dumps(body or {}, sort_keys=True, separators=(",", ":"))
        body_hash = _md5(payload)

    sign = _md5(f"{path}{nonce}{timestamp}{body_hash}{secret}")
    return f"nonce={nonce}&timestamp={timestamp}&sign={sign}"


class FnvClient:
    """飞牛影视 API 客户端：登录 / 媒体库列表 / 触发扫描。

    特性：
    - 超时设置（config.timeout）；
    - 指数退避失败重试：超时、网络错误、5xx 自动重试；
    - code == -2 自动重新登录后重试（最多 max_relogin 次）；
    - code == -14 视为已扫描中，直接忽略当作成功；
    - token 过期自动重登。
    """

    def __init__(self, config: AppConfig, logger: logging.Logger) -> None:
        self._config = config
        self._logger = logger
        self._session = requests.Session()
        self._session.headers["User-Agent"] = "fntv-strm-monitor/1.0"
        self.token: Optional[str] = config.token

    # ------------------------------------------------------------------ 鉴权

    @property
    def _can_relogin(self) -> bool:
        """是否具备自动重登条件（配置了用户名密码）。"""
        return bool(self._config.username and self._config.password)

    def _headers(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        """组装请求头：authx 签名 + 按需 Authorization / Content-Type / api-key。"""
        headers = {"authx": build_authx(method, path, self._config.secret, params, body)}
        if method.upper() != "GET":
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = self.token
        if self._config.api_key:
            headers["api-key"] = self._config.api_key
        return headers

    # ------------------------------------------------------------- 核心请求

    def _backoff(self, n: int) -> float:
        """指数退避：base * 2^n，封顶 max_backoff。"""
        retry = self._config.retry
        return min(retry.base_backoff * (2 ** n), retry.max_backoff)

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        body: Optional[Dict[str, Any]] = None,
        *,
        allow_relogin: bool = True,
    ) -> Dict[str, Any]:
        """统一请求封装：超时 + 指数退避重试 + 自动重登 + code=-14 忽略。

        - 超时 / 网络错误 / 5xx：指数退避重试（max_retries 次）；
        - code == -2：重新登录后立即重试当前请求（最多 max_relogin 次）；
        - code == -14：已有扫描任务在跑，视为成功直接返回。
        """
        retry = self._config.retry
        url = f"{self._config.nas_url}{path}"
        attempt = 0
        relogin_count = 0

        while True:
            try:
                resp = self._session.request(
                    method,
                    url,
                    params=params,
                    json=body if body is not None else None,
                    headers=self._headers(method, path, params, body),
                    timeout=self._config.timeout,
                )
                resp.raise_for_status()  # 4xx/5xx 进入异常分支
                data = resp.json()

                code = data.get("code")
                if code == -2 and allow_relogin and self._can_relogin:
                    # 鉴权失效：重新登录后重试当前请求
                    if relogin_count >= retry.max_relogin:
                        raise FnvApiError(f"鉴权失效(code=-2)，重新登录次数已达上限 {retry.max_relogin}")
                    relogin_count += 1
                    self._logger.warning("鉴权失效(code=-2)，第 %d 次重新登录后重试", relogin_count)
                    self.login()
                    continue
                if code == -14:
                    # 已有扫描任务在跑：可视为成功/忽略
                    self._logger.info("媒体库已有扫描任务在跑(code=-14)，忽略本次触发")
                    return data
                return data

            except (requests.Timeout, requests.ConnectionError) as exc:
                self._logger.warning("请求异常(%s %s): %s", method, path, exc)
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else 0
                if status < 500:
                    # 4xx 业务外错误：重试无意义，直接失败
                    raise FnvApiError(f"HTTP {status} 请求 {method} {path} 失败") from exc
                self._logger.warning("服务端错误(HTTP %d) %s %s，准备重试", status, method, path)

            if attempt >= retry.max_retries:
                raise FnvRetryExhausted(f"{method} {path} 重试 {attempt} 次后仍失败")
            attempt += 1
            delay = self._backoff(attempt - 1)
            self._logger.info("第 %d 次重试 %s %s，%.1f 秒后重试", attempt, method, path, delay)
            time.sleep(delay)

    # ---------------------------------------------------------------- 业务

    def login(self) -> str:
        """登录飞牛影视，成功后将 token 写入 self.token 并返回。"""
        if not self._config.username or not self._config.password:
            raise FnvApiError("未配置 username/password，无法登录")
        body = {
            "username": self._config.username,
            "password": self._config.password,
            "app_name": self._config.app_name,
        }
        data = self._request("POST", "/v/api/v1/login", body=body, allow_relogin=False)
        code = data.get("code")
        if code != 0 or not data.get("data", {}).get("token"):
            raise FnvApiError(
                f"登录失败: code={code}, msg={data.get('msg') or data.get('message')}"
            )
        self.token = data["data"]["token"]
        self._logger.info("登录成功，已获取 token")
        return self.token

    def list_libraries(self) -> List[Dict[str, Any]]:
        """获取媒体库列表（GET /v/api/v1/mdb/list）。"""
        data = self._request("GET", "/v/api/v1/mdb/list")
        if data.get("code") != 0:
            raise FnvApiError(
                f"获取媒体库列表失败: code={data.get('code')}, msg={data.get('msg')}"
            )
        return data.get("data") or []

    def resolve_library_id(self, name: str) -> str:
        """按媒体库名称自动解析 guid（用于 library_name 配置）。"""
        for lib in self.list_libraries():
            if lib.get("name") == name:
                guid = lib.get("guid")
                if not guid:
                    raise FnvApiError(f"媒体库 {name} 缺少 guid 字段")
                self._logger.info("媒体库名称解析: %s -> %s", name, guid)
                return str(guid)
        raise FnvApiError(f"未找到名为 {name!r} 的媒体库，请检查 library_name 或改用 library_id")

    def trigger_scan(self, library_id: str) -> Dict[str, Any]:
        """触发媒体库扫描（POST /v/api/v1/mdb/scan/{library_id}）。

        code == -14 已在 _request 中作为成功忽略处理。
        """
        path = f"/v/api/v1/mdb/scan/{library_id}"
        data = self._request("POST", path, body={})
        code = data.get("code")
        if code != 0:
            raise FnvApiError(f"触发扫描失败: code={code}, msg={data.get('msg')}")
        return data
