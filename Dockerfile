# 飞牛影视 SRTM 实时监控 镜像
FROM python:3.11-slim

LABEL maintainer="fntv-strm-monitor" \
      description="监听 .strm 文件变化并触发飞牛影视媒体库扫描"

WORKDIR /app

# 先装依赖，利用 Docker 层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 拷贝项目代码与默认配置
COPY . .

# 容器内默认监控根目录与日志卷目录
RUN mkdir -p /strm /logs

# 使用 UTF-8 避免日志中文乱码
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8

# 默认入口：python main.py --config /app/config.yaml
# 实际配置通过 docker-compose 挂载覆盖
CMD ["python", "main.py", "--config", "/app/config.yaml"]
