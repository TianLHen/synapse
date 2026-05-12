"""Synapse 工具系统 — 注册 · 执行 · 安全控制"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

_here = Path(__file__).resolve().parent


# ──────────────────────────────────────────────
# 工具定义
# ──────────────────────────────────────────────

class Tool:
    """一个可被 agent 调用的工具。"""
    def __init__(self, name: str, description: str, fn: Callable, parameters: dict | None = None):
        self.name = name
        self.description = description
        self.fn = fn
        self.parameters = parameters or {}

    def __call__(self, args: str) -> str:
        try:
            result = self.fn(args)
            return str(result) if result is not None else ""
        except Exception as e:
            return f"[错误] {e}"


class ToolRegistry:
    """工具注册表。"""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def execute(self, name: str, args: str) -> str:
        tool = self.get(name)
        if not tool:
            return f"[错误] 未知工具: {name}"
        return tool(args)

    def prompt_block(self) -> str:
        """生成给 LLM 看的工具描述。"""
        lines = ["## 可用工具"]
        for t in self._tools.values():
            lines.append(f"  <tool name=\"{t.name}\"> — {t.description}")
            if t.parameters:
                lines.append(f"    参数: {', '.join(t.parameters)}")
        lines.append("")
        lines.append("当你需要做某件事时，在回复中写:")
        lines.append('<tool name="工具名">参数</tool>')
        lines.append("系统会自动执行并返回结果，你看到结果后继续思考。")
        lines.append("如果不需要工具了，直接回复最终答案。")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 内置工具实现
# ──────────────────────────────────────────────

def _tool_recall(args: str) -> str:
    """从知识图谱召回知识。"""
    from knowledge_graph import recall_text
    topic = args.strip()
    if not topic:
        return "用法: <tool name=\"recall\">关键词</tool>"
    result = recall_text(topic)
    if result:
        return f"[图谱召回: {topic}]\n{result}"
    return f"[图谱中未找到: {topic}]"


def _tool_read(args: str) -> str:
    """读取文件内容。"""
    path = args.strip().strip("\"'")
    if not path:
        return "用法: <tool name=\"read\">文件路径</tool>"
    p = Path(path)
    if not p.is_absolute():
        p = _here / p
    if not p.exists():
        return f"[错误] 文件不存在: {p}"
    if p.stat().st_size > 50000:
        return f"[错误] 文件太大 (>50KB): {p}"
    try:
        return p.read_text(encoding="utf-8")[:3000]
    except Exception as e:
        try:
            return p.read_text(encoding="gbk")[:3000]
        except Exception as e2:
            return f"[错误] 无法读取: {e2}"


def _tool_exec(args: str) -> str:
    """在安全沙箱中执行命令."""
    cmd = args.strip()
    if not cmd:
        return "用法: <tool name=\"exec\">命令</tool>"
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
        out = r.stdout or ""
        err = r.stderr or ""
        result = ""
        if out:
            result += out[:2000]
        if err:
            if result:
                result += "\n--- stderr ---\n"
            result += err[:1000]
        return result or "(无输出)"
    except subprocess.TimeoutExpired:
        return "[错误] 命令超时 (30s)"
    except Exception as e:
        return f"[错误] {e}"


def _tool_think(args: str) -> str:
    """内部思考步骤——帮你一步步推理。"""
    return f"[思考: {args.strip()}]"


# ──────────────────────────────────────────────
# 默认注册表
# ──────────────────────────────────────────────

def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(Tool("recall", "从知识图谱中召回相关知识", _tool_recall))
    reg.register(Tool("read", "读取本地文件内容", _tool_read))
    reg.register(Tool("exec", "在系统终端中执行命令", _tool_exec))
    reg.register(Tool("think", "内部推理思考步骤", _tool_think))
    return reg
