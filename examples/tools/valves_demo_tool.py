"""
title: Valves Demo
author: open-webui
description: 用于测试所有 Valves 配置项类型的演示工具，包含字符串、数值、布尔、枚举、密码、下拉、颜色、单选、多选等。
version: 0.1.0
required_open_webui_version: 0.5.0
"""

from typing import Literal
from pydantic import BaseModel, Field


class Tools:
    class Valves(BaseModel):
        # 1) 普通字符串 -> 多行 textarea
        api_endpoint: str = Field(
            default="https://api.example.com/v1",
            title="API 端点",
            description="后端服务地址（演示默认 textarea 渲染）",
        )

        # 2) 密码 -> SensitiveInput
        api_key: str = Field(
            default="",
            title="API Key",
            description="敏感信息，渲染为可隐藏/显示的密码框",
            json_schema_extra={"input": {"type": "password"}},
        )

        # 3) 布尔 -> Switch
        enable_cache: bool = Field(
            default=True,
            title="启用缓存",
            description="开关式布尔字段",
        )

        # 4) 数值 -> 单行 input
        timeout_seconds: int = Field(
            default=30,
            title="超时时间（秒）",
            description="非字符串、非布尔，回退为单行输入",
        )

        # 5) Literal 枚举 -> 下拉框（由 Pydantic 自动生成 enum）
        log_level: Literal["debug", "info", "warning", "error"] = Field(
            default="info",
            title="日志级别",
            description="使用 Literal 自动生成 enum 下拉",
        )

        # 6) 下拉框（静态 options，含 label）
        region: str = Field(
            default="cn-east-1",
            title="区域",
            description="select + 静态 options（{value, label} 形式）",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": [
                        {"value": "cn-east-1", "label": "华东 1"},
                        {"value": "cn-north-1", "label": "华北 1"},
                        {"value": "ap-southeast-1", "label": "新加坡"},
                        {"value": "us-west-2", "label": "美国西部"},
                    ],
                }
            },
        )

        # 7) 颜色选择器
        accent_color: str = Field(
            default="#3B82F6",
            title="主题色",
            description="颜色选择器，存储为 #RRGGBB",
            json_schema_extra={"input": {"type": "color"}},
        )

        # 8) 单选（radio 风格的 checkbox 类型）
        output_format: str = Field(
            default="markdown",
            title="输出格式",
            description="单选：底层为 str，UI 渲染为 radio",
            json_schema_extra={
                "input": {
                    "type": "checkbox",
                    "options": [
                        {"value": "markdown", "label": "Markdown"},
                        {"value": "plain", "label": "纯文本"},
                        {"value": "json", "label": "JSON"},
                    ],
                }
            },
        )

        # 9) 多选（checkbox 风格 + 静态 options）
        enabled_sections: list[str] = Field(
            default=["summary", "details"],
            title="启用的章节",
            description="多选：底层为 list[str]，UI 渲染为 checkbox 组",
            json_schema_extra={
                "input": {
                    "type": "checkbox",
                    "multiple": True,
                    "options": [
                        {"value": "summary", "label": "摘要"},
                        {"value": "details", "label": "详情"},
                        {"value": "examples", "label": "示例"},
                        {"value": "references", "label": "参考资料"},
                        {"value": "changelog", "label": "变更日志"},
                    ],
                }
            },
        )

    class UserValves(BaseModel):
        # 10) 用户级偏好：昵称（默认 textarea）
        nickname: str = Field(
            default="",
            title="昵称",
            description="问候语中使用的称呼",
        )

        # 11) 用户级单选（动态 options - 演示方法名形式）
        preferred_model: str = Field(
            default="",
            title="首选模型",
            description="select + 动态 options（方法名形式，运行时调用）",
            json_schema_extra={
                "input": {
                    "type": "select",
                    "options": "get_model_options",
                }
            },
        )

        # 12) 用户级多选（动态 options - 演示带 __user__ 参数的方法名）
        subscribed_topics: list[str] = Field(
            default=[],
            title="订阅主题",
            description="checkbox 多选 + 动态 options（接收 __user__ 注入）",
            json_schema_extra={
                "input": {
                    "type": "checkbox",
                    "multiple": True,
                    "options": "get_topic_options",
                }
            },
        )

        # 13) 用户级语气单选（纯字符串 options）
        tone: str = Field(
            default="friendly",
            title="语气",
            description="单选 + 纯字符串 options（不带 label）",
            json_schema_extra={
                "input": {
                    "type": "checkbox",
                    "options": ["formal", "friendly", "playful"],
                }
            },
        )

        @classmethod
        def get_model_options(cls) -> list[dict]:
            """无参动态 options：返回静态列表"""
            return [
                {"value": "gpt-4o", "label": "GPT-4o"},
                {"value": "claude-3-5-sonnet", "label": "Claude 3.5 Sonnet"},
                {"value": "gemini-1.5-pro", "label": "Gemini 1.5 Pro"},
                {"value": "qwen-max", "label": "通义千问 Max"},
            ]

        @classmethod
        def get_topic_options(cls, __user__=None) -> list[dict]:
            """
            带 __user__ 注入的动态 options：
            演示如何根据当前用户角色返回不同选项。
            """
            base = [
                {"value": "tech", "label": "科技"},
                {"value": "ai", "label": "AI"},
                {"value": "design", "label": "设计"},
                {"value": "music", "label": "音乐"},
            ]
            if __user__ and __user__.get("role") == "admin":
                base.append({"value": "admin_only", "label": "(仅管理员可见)"})
            return base

    def __init__(self):
        self.valves = self.Valves()

    def show_config(self, __user__: dict = {}) -> str:
        """
        展示当前的工具配置项（Valves + UserValves）。
        调用此函数会回显所有配置项的实际值，便于在前端调整后立刻验证生效情况。

        :return: 当前配置的可读字符串
        """
        v = self.valves
        u = __user__.get("valves") if isinstance(__user__, dict) else None

        lines: list[str] = []
        lines.append("## 工具级配置 (Valves)")
        lines.append(f"- API 端点: `{v.api_endpoint}`")
        lines.append(
            f"- API Key: `{'*' * len(v.api_key) if v.api_key else '(空)'}`"
        )
        lines.append(f"- 启用缓存: **{v.enable_cache}**")
        lines.append(f"- 超时时间: **{v.timeout_seconds}** 秒")
        lines.append(f"- 日志级别: `{v.log_level}`")
        lines.append(f"- 区域: `{v.region}`")
        lines.append(f"- 主题色: `{v.accent_color}`")
        lines.append(f"- 输出格式: `{v.output_format}`")
        lines.append(f"- 启用的章节: {v.enabled_sections}")

        lines.append("")
        lines.append("## 用户级配置 (UserValves)")
        if u is None:
            lines.append("(未设置)")
        else:
            lines.append(f"- 昵称: `{u.nickname or '(未填写)'}`")
            lines.append(f"- 首选模型: `{u.preferred_model or '(未选择)'}`")
            lines.append(f"- 订阅主题: {u.subscribed_topics}")
            lines.append(f"- 语气: `{u.tone}`")

        return "\n".join(lines)

    def greet(self, __user__: dict = {}) -> str:
        """
        根据 UserValves 中的昵称和语气生成一句问候语，用于验证用户级配置是否正确读取。

        :return: 一句问候语
        """
        u = __user__.get("valves") if isinstance(__user__, dict) else None
        nickname = (u.nickname if u else "") or "朋友"
        tone = (u.tone if u else "friendly")

        templates = {
            "formal": f"您好，{nickname}。很荣幸为您服务。",
            "friendly": f"嗨，{nickname}！今天过得怎么样？",
            "playful": f"哟～{nickname}，又来玩啦？",
        }
        return templates.get(tone, templates["friendly"])
