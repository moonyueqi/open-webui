"""
title: Collapse Group Test
author: open-webui
description: 用于验证「工具/思考块折叠分组」功能的测试工具。提供多个无需外部依赖的简单方法，引导模型在一次回复中连续调用多个工具，从而触发连续 details 折叠成一行摘要（如「已探索 …」）。
version: 0.1.0
required_open_webui_version: 0.5.0
"""

import math
import random
import datetime
import platform


class Tools:
    def __init__(self):
        pass

    def get_current_time(self) -> str:
        """
        获取当前的服务器日期与时间。

        :return: 当前日期时间字符串
        """
        now = datetime.datetime.now()
        return f"当前时间：{now.strftime('%Y-%m-%d %H:%M:%S')}"

    def add_numbers(self, a: float, b: float) -> str:
        """
        计算两个数字之和。

        :param a: 第一个加数
        :param b: 第二个加数
        :return: 求和结果
        """
        return f"{a} + {b} = {a + b}"

    def multiply_numbers(self, a: float, b: float) -> str:
        """
        计算两个数字之积。

        :param a: 第一个乘数
        :param b: 第二个乘数
        :return: 乘积结果
        """
        return f"{a} × {b} = {a * b}"

    def square_root(self, x: float) -> str:
        """
        计算一个非负数字的平方根。

        :param x: 需要开方的数字（应为非负数）
        :return: 平方根结果
        """
        if x < 0:
            return f"错误：{x} 是负数，无法计算实数平方根。"
        return f"√{x} = {math.sqrt(x)}"

    def roll_dice(self, sides: int = 6) -> str:
        """
        掷一个指定面数的骰子并返回点数。

        :param sides: 骰子的面数，默认 6
        :return: 掷骰结果
        """
        if sides < 2:
            return "错误：骰子至少需要 2 个面。"
        result = random.randint(1, sides)
        return f"掷出了一个 {sides} 面骰，点数为：{result}"

    def reverse_text(self, text: str) -> str:
        """
        将输入文本反转。

        :param text: 需要反转的文本
        :return: 反转后的文本
        """
        return f"反转结果：{text[::-1]}"

    def word_count(self, text: str) -> str:
        """
        统计文本的字符数与单词数（按空白切分）。

        :param text: 需要统计的文本
        :return: 字符数与单词数统计
        """
        chars = len(text)
        words = len(text.split())
        return f"字符数：{chars}，单词数：{words}"

    def get_system_info(self) -> str:
        """
        返回运行 Open WebUI 后端的操作系统与 Python 版本信息。

        :return: 系统信息字符串
        """
        return (
            f"操作系统：{platform.system()} {platform.release()}；"
            f"Python 版本：{platform.python_version()}"
        )
