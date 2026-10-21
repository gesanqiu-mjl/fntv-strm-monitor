"""飞牛影视 SRTM 实时监控（fntv-strm-monitor）核心包。

功能：
- 目录监控：watchdog 监听 .strm 文件新增/删除/移动事件，多目录并行支持；
- API 调用：登录、媒体库列表解析、触发扫描，含 authx 签名与指数退避重试；
- 日志输出：记录 strm 新增/删除时间与触发扫描时间，stdout + 文件双输出。
"""

__version__ = "1.0.0"
