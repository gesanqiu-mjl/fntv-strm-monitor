---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 240c62b6fc56ebb99c385ae28b4f0035_c2aa273bccf511f1afbb52540064ee0f
    ReservedCode1: HoahUdPok65RdftYDBDxA1UhYtInbS2bZYMPVQCm9yT2YPo1V7RbviBRDW0nI79t2GrWJaIH5gGztLGyoqLC+J6NqHiW5QmdWJfEOccidIr5g5WAp1r2dIbksEfRm/ixJpiKfDFQleWKtGjaviqgDxnrnie4GI6/x/v0pQBfsOIAft0GXXYWQOhZckc=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 240c62b6fc56ebb99c385ae28b4f0035_c2aa273bccf511f1afbb52540064ee0f
    ReservedCode2: HoahUdPok65RdftYDBDxA1UhYtInbS2bZYMPVQCm9yT2YPo1V7RbviBRDW0nI79t2GrWJaIH5gGztLGyoqLC+J6NqHiW5QmdWJfEOccidIr5g5WAp1r2dIbksEfRm/ixJpiKfDFQleWKtGjaviqgDxnrnie4GI6/x/v0pQBfsOIAft0GXXYWQOhZckc=
---

# 飞牛影视 SRTM 实时监控（fntv-strm-monitor）

监控 NAS 上存放 `.strm` 文件的目录，当文件**新增 / 删除 / 移动**时自动触发飞牛影视（fnOS 影视）对应媒体库的扫描刷新，让 Emby/Jellyfin 类刮削及时生效。支持**多目录同时监控**，每个监控目录独立映射一个媒体库；支持**失败自动重试**与 **token 过期自动重登**；日志同时输出到 **stdout 与挂载卷文件**。

> 接口基于社区抓包逆向调研（见项目附件 `fntv_api_notes.md`），非官方开放 API，可能随飞牛影视版本变化。

## 功能特性

| 功能 | 说明 |
|---|---|
| 目录监控 | 基于 watchdog 监听 `.strm` 文件新增 / 删除 / 移动事件，支持递归子目录 |
| 多目录支持 | 同时监控多个 strm 目录，各自映射独立媒体库，目录有变化只扫描对应库 |
| 事件去抖 | 批量写入时事件密集，静默期（默认 5 秒）内合并，只触发一次扫描 |
| API 客户端 | 登录获取 token / 直接配置 token、authx cse 签名、超时设置 |
| 失败重试 | 超时 / 网络错误 / 5xx 指数退避重试；`code=-2` 自动重新登录后重试 |
| 已扫描忽略 | `code=-14`（已有扫描任务在跑）视为成功忽略 |
| 日志输出 | 记录 strm 新增 / 删除时间、触发扫描时间；stdout + 文件双通道 |
| Docker 封装 | `python:3.11-slim`，镜像自动发布 ghcr.io，NAS 直接 `docker compose up -d` 拉取 |

## 目录结构

```
fntv-strm-monitor/
├── main.py                    # 主入口（支持 --config）
├── fntv_monitor/
│   ├── __init__.py
│   ├── config.py              # 配置加载与校验
│   ├── api_client.py          # 飞牛影视 API 客户端（authx 签名/重试/重登）
│   ├── watcher.py             # watchdog 目录监控 + 事件去抖
│   ├── scanner.py             # 扫描触发协调器
│   └── logger_setup.py        # 日志（stdout + 文件）
├── config.yaml                # 运行配置（按实际环境修改）
├── config.example.yaml        # 配置模板
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .github/workflows/docker-build.yml   # 自动构建并推送 ghcr.io 镜像
└── README.md
```

## 快速开始

### 方式一：本地运行

```bash
pip install -r requirements.txt
python main.py --config config.yaml
```

### 方式二：Docker 部署（推荐，镜像发布在 ghcr.io）

镜像由 GitHub Actions 在 push 到 master 时自动构建并推送到 `ghcr.io/gesanqiu-mjl/fntv-strm-monitor:latest`，NAS 上无需本地构建。

1. 复制模板并填写配置：

```bash
cp config.example.yaml config.yaml
# 编辑 config.yaml：NAS 地址、账号/密码或 token、secret、媒体库映射
```

2. 编辑 `docker-compose.yml`，将 strm 目录挂载改为 NAS 实际路径（默认已配置 `/vol1/1000/容器/LitePan/strm/更新中|海外纪录片|纪录片`），确保与 `config.yaml` 中 `libraries[].watch_dir` 一一对应。

3. 拉取镜像并启动（首次需先登录 ghcr.io 私有镜像，见常见问题 Q8）：

```bash
docker compose up -d
docker compose logs -f fntv-strm-monitor   # 实时查看日志
```

日志同时写入宿主机 `./logs/monitor.log`（挂载卷）。

## 配置说明

### 核心配置项

| 字段 | 必填 | 说明 |
|---|---|---|
| `nas_url` | 是 | NAS 地址，如 `http://192.168.1.100:5666`（HTTP 5666 / HTTPS 5667） |
| `auth.username` / `auth.password` | 二选一 | 登录用户名密码，用于获取 token 与自动重登 |
| `token` | 二选一 | 已登录 token；配置后跳过登录（若同时没有账号密码则过期后无法自动重登） |
| `secret` | 是 | authx 签名密钥，从飞牛影视网页 JS 源码提取 |
| `api_key` | 否 | 部分版本需要的 `api-key` 请求头，按实际抓包填写 |
| `libraries` | 是 | 媒体库映射列表，见下表 |
| `debounce_seconds` | 否 | 事件去抖静默期（秒），默认 `5` |
| `timeout` | 否 | 单次请求超时（秒），默认 `10` |
| `retry` | 否 | 重试参数，见下表 |
| `log_dir` / `log_file` / `log_level` | 否 | 日志路径与级别，默认 `/logs` / `monitor.log` / `INFO` |

### libraries（媒体库映射）

| 字段 | 必填 | 说明 |
|---|---|---|
| `watch_dir` | 是 | 监控目录（容器内路径，须与 docker-compose 挂载一致） |
| `library_id` | 二选一 | 媒体库 guid（`mdb/list` 返回的 `guid`） |
| `library_name` | 二选一 | 媒体库名称；未填 `library_id` 时启动自动调用 `mdb/list` 解析 guid |
| `recursive` | 否 | 是否递归监控子目录，默认 `true` |

### retry（重试参数）

| 字段 | 默认 | 说明 |
|---|---|---|
| `max_retries` | 5 | 超时 / 网络错误 / 5xx 最大重试次数 |
| `base_backoff` | 2.0 | 指数退避基础值（秒），`base * 2^n` |
| `max_backoff` | 60.0 | 退避上限（秒） |
| `max_relogin` | 3 | `code=-2` 鉴权失效时最多重新登录次数 |

## 日志示例

```
2026-10-21 10:00:01 [INFO] 飞牛影视 SRTM 实时监控启动（版本 1.0.0）
2026-10-21 10:00:01 [INFO] 配置文件: /app/config.yaml
2026-10-21 10:00:02 [INFO] 登录成功，已获取 token
2026-10-21 10:00:02 [INFO] 媒体库名称解析: 电影 -> 2c9f1a4e-xxxx-xxxx-xxxx-xxxxxxxxxxxx
2026-10-21 10:00:02 [INFO] 已注册监控目录 /strm/movie1（媒体库 2c9f..., 递归=True）
2026-10-21 10:00:02 [INFO] 监控已启动：共 2 个目录，去抖 5 秒（Ctrl+C 退出）

# —— strm 新增事件（记录新增时间）——
2026-10-21 10:05:12 [INFO] strm 新增: /strm/movie1/电影A/电影A.strm（监控目录 /strm/movie1）
2026-10-21 10:05:13 [INFO] strm 新增: /strm/movie1/电影B/电影B.strm（监控目录 /strm/movie1）
# —— 去抖结束，触发扫描（记录触发扫描时间）——
2026-10-21 10:05:18 [INFO] 去抖结束：目录 /strm/movie1 本次新增 2 个 / 删除 0 个 strm，准备触发媒体库扫描
2026-10-21 10:05:18 [INFO] 触发媒体库扫描 library_id=2c9f1a4e-xxxx（新增 2 / 删除 0 strm）
2026-10-21 10:05:18 [INFO] 扫描指令已发送成功 library_id=2c9f1a4e-xxxx，耗时 0.32 秒

# —— strm 删除事件 + 已扫描中忽略——
2026-10-21 11:00:03 [INFO] strm 删除: /strm/tv1/剧集C/剧集C.strm（监控目录 /strm/tv1）
2026-10-21 11:00:08 [INFO] 触发媒体库扫描 library_id=3a5b....（新增 0 / 删除 1 strm）
2026-10-21 11:00:08 [INFO] 媒体库已有扫描任务在跑(code=-14)，忽略本次触发
```

## 常见问题

**Q1: 如何获取 authx 签名 secret？**
浏览器登录飞牛影视网页后按 `Ctrl+U` 查看源码，搜索 `,s,l,c,o,e].join("_")`，其左侧引号内的字符串即 secret。

**Q2: 如何获取媒体库 guid？**
两种方式：① 在 `config.yaml` 只填 `library_name`，程序启动时会自动调用 `GET /v/api/v1/mdb/list` 解析；② 手动抓包 `mdb/list` 响应，把 `guid` 填入 `library_id`。

**Q3: token 过期怎么办？**
配置了 `auth.username/password` 时，程序检测到 `code=-2` 会自动重新登录并重试（最多 `max_relogin` 次）。如果只配置了 `token`，过期后日志会报错，需要手动更新 token。

**Q4: 为什么日志里出现 code=-14？**
表示飞牛影视已经有扫描任务在跑，本次触发被忽略，属正常行为，不会重复扫描。

**Q5: 监控目录挂载为只读（:ro）还能收到文件事件吗？**
可以。watchdog 通过 inotify 收到事件通知，不需要对目录的写权限；只读挂载可防止容器内误改源文件。

**Q6: 扫描接口调用失败会怎样？**
超时 / 网络错误 / 5xx 会按 `base_backoff * 2^n` 指数退避重试（最多 `max_retries` 次）；重试耗尽后本次事件不再重试（避免阻塞后续事件），错误会写入日志。

**Q7: 非容器环境如何运行？**
直接 `python main.py --config config.yaml`，将 `watch_dir` 改为本地实际路径、`log_dir` 改为本地目录即可。

**Q8: NAS 拉取 ghcr.io 镜像报 denied / unauthorized？**
镜像随私有仓库发布在 ghcr.io（默认私有），需先登录：`echo "<你的GitHub PAT>" | docker login ghcr.io -u gesanqiu-mjl --password-stdin`。PAT 需勾选 `read:packages` 权限；登录一次即可。

## 注意事项

- 接口为抓包逆向所得，非官方 API，升级飞牛影视版本后可能失效，请关注社区更新。
- 多目录批量部署时，建议 `debounce_seconds` 设为 5~10 秒，避免批量写入期间频繁触发扫描。
*（内容由AI生成，仅供参考）*
