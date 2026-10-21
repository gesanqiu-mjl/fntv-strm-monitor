---
AIGC:
    Label: "1"
    ContentProducer: 001191440300708461136T1XGW3
    ProduceID: 240c62b6fc56ebb99c385ae28b4f0035_567116a7cd1011f1b76f525400638852
    ReservedCode1: 5hauvO8XHOcrQrw6IXgPcFYPoTzjwvl8Etka9V8WGJKbTIX5Zz0Fzo9V4M51+bZahCof0XqLmHpjXvCRdu3syF9Kt6jjdOoYHqrokytHWdc67ArtqkWtjVYnU+dd/7kju7VtrN8te2MWvYQhRfJ789FLnx0sZyGGc5Lw6sEUN416Nsjf4vU7NQk1xMw=
    ContentPropagator: 001191440300708461136T1XGW3
    PropagateID: 240c62b6fc56ebb99c385ae28b4f0035_567116a7cd1011f1b76f525400638852
    ReservedCode2: 5hauvO8XHOcrQrw6IXgPcFYPoTzjwvl8Etka9V8WGJKbTIX5Zz0Fzo9V4M51+bZahCof0XqLmHpjXvCRdu3syF9Kt6jjdOoYHqrokytHWdc67ArtqkWtjVYnU+dd/7kju7VtrN8te2MWvYQhRfJ789FLnx0sZyGGc5Lw6sEUN416Nsjf4vU7NQk1xMw=
---





# 飞牛影视 SRTM 实时监控 - 部署说明

本文档面向 NAS / Linux 服务器，使用 Docker Compose 一键部署。

## 0. 前置要求

- Docker Engine（含 Compose v2 插件，`docker compose version` 可验证）
- git
- 服务器时间准确（认证签名依赖时间戳）

## 1. 拉取项目

```bash
# HTTPS 方式（私有仓库需配置 PAT 凭据）
git clone https://github.com/gesanqiu-mjl/fntv-strm-monitor.git
cd fntv-strm-monitor

# 或 SSH 方式
# git clone git@github.com:gesanqiu-mjl/fntv-strm-monitor.git
```

## 2. 生成并填写 config.yaml

```bash
cp config.example.yaml config.yaml
vi config.yaml
```

必填项：

| 字段 | 说明 |
| --- | --- |
| `nas_url` | 飞牛影视地址，如 `http://192.168.1.100:5666`（HTTP 默认 5666，HTTPS 默认 5667） |
| `auth.username` / `auth.password` | 飞牛影视账号密码（用于登录换取 token，过期自动重登） |
| `secret` | authx 签名密钥。浏览器登录飞牛影视后 Ctrl+U 查看源码，搜索 `",s,l,c,o,e].join("_")` 左侧引号内的字符串 |
| `libraries[].watch_dir` | 容器内监控路径，**必须与 docker-compose.yml 挂载一致**（默认 `/strm/updating`、`/strm/overseas`、`/strm/doc`） |
| `libraries[].library_id` 或 `library_name` | 媒体库 guid（二选一，只填名称时启动自动解析） |

> 若只使用一个监控目录，请删除多余的 `libraries` 条目，并同步删除 docker-compose.yml 中对应挂载行。

## 3. 编辑 docker-compose.yml 挂载路径

打开 `docker-compose.yml`，将 `volumes` 中 strm 目录的宿主机路径（`/vol1/1000/容器/LitePan/strm/更新中`、`/vol1/1000/容器/LitePan/strm/海外纪录片`、`/vol1/1000/容器/LitePan/strm/纪录片`）改为 NAS 上的实际路径，并确保与 `config.yaml` 的 `libraries[].watch_dir` 一一对应（容器内默认 `/strm/updating`、`/strm/overseas`、`/strm/doc`）。

如需调整时区，直接修改 `environment` 下的 `TZ`；日志目录默认挂载 `./logs`。

## 4. 拉取镜像并启动

镜像由 GitHub Actions 自动构建并发布到 `ghcr.io/gesanqiu-mjl/fntv-strm-monitor:latest`，无需本地构建。私有仓库的镜像默认私有，首次拉取需先登录：

```bash
# 使用 GitHub PAT（需 read:packages 权限）登录 ghcr.io
echo "<你的GitHub PAT>" | docker login ghcr.io -u gesanqiu-mjl --password-stdin

docker compose up -d
```

- 首次会自动拉取 ghcr.io 镜像 `ghcr.io/gesanqiu-mjl/fntv-strm-monitor:latest` 并后台启动容器 `fntv-strm-monitor`。
- 配置文件以只读方式挂载（`config.yaml:/app/config.yaml:ro`），strm 目录只读挂载，不会修改原文件。

## 5. 查看日志

```bash
# 跟随输出
docker compose logs -f fntv-strm-monitor

# 查看最近 200 行
docker compose logs --tail=200 fntv-strm-monitor

# 容器内日志文件（挂载到宿主机 ./logs）
tail -f ./logs/monitor.log
```

常见日志含义：

- `登录成功` / `token 已刷新`：认证正常
- `触发扫描 library_id=...`：strm 变化已触发媒体库扫描
- `code=-14`：媒体库已在扫描中，忽略即可
- `code=-2`：鉴权失效，程序会自动重新登录（`max_relogin` 次内）

## 6. 更新版本

```bash
git pull
docker compose pull          # 拉取最新 ghcr.io 镜像
docker compose up -d         # 用新镜像重建容器
```

镜像由 GitHub Actions 自动构建，更新只需拉取新镜像并重建容器，config.yaml 保持不变。

## 7. 停止与卸载

```bash
docker compose down          # 停止并删除容器（保留镜像与数据）
docker compose down --rmi local   # 同时删除本地构建镜像
```

## 8. 常见问题

- **容器一直重启 / 日志报找不到配置**：确认 `config.yaml` 存在且已填写，`docker compose up -d` 在项目根目录执行。
- **strm 目录没被监控**：检查宿主机挂载路径与 `config.yaml` 的 `watch_dir` 是否一一对应，挂载使用 `:ro` 只读不影响监听。
- **改完 config.yaml 未生效**：配置文件是启动时挂载的，执行 `docker compose restart fntv-strm-monitor` 或 `docker compose up -d` 重新创建容器。
- **拉取 ghcr.io 镜像报 denied / unauthorized**：私有镜像需先 `echo "<你的GitHub PAT>" | docker login ghcr.io -u gesanqiu-mjl --password-stdin`（PAT 勾选 `read:packages` 权限），登录后重试 `docker compose up -d`。
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
*（内容由AI生成，仅供参考）*
