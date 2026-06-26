# tools_python

OpenWebUI 的 **单文件 Python Tool** 集中放在这里。

这种 tool 不是 HTTP 服务（区别于 `fengche/tool_server` 那类 OpenAPI 工具），而是
直接由 OpenWebUI 在 sandbox 里 import 并调用的 Python 文件——每个 `*.py` 文件
都需要定义一个 `class Tools` 并包含若干供模型调用的方法。

## 当前清单

| 文件 | 说明 | 测试 |
|---|---|---|
| `sz_weekly_weather_tool.py` | 调用苏州市气象局 `7DaysForecast` 接口，返回未来一周（白天/夜晚）结构化预报 | `tests/test_weekly_tool.py` |

## 安装 / 加载

OpenWebUI 管理员页 → Workspace → Tools → **Import**，上传对应的 `.py` 文件。

UI 里会按文件头部的 docstring（`title` / `author` / `version` / `description`）显示元数据。

## 跑测试

```bash
cd tools_python
python tests/test_weekly_tool.py
```

要求当前目录在 `sys.path` 里（`test_weekly_tool.py` 里 `from sz_weekly_weather_tool import Tools` 会从同级目录 import）。
