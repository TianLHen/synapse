"""Synapse 工具系统 — 注册 · 执行 · 安全控制"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.parse
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

    def register(self, name: str, tool: Tool):
        self._tools[name] = tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def list(self) -> list[Tool]:
        return list(self._tools.values())

    def names(self) -> list[str]:
        return list(self._tools.keys())

    def execute(self, name: str, args: str) -> str:
        tool = self.get(name)
        if not tool:
            return f"[错误] 未知工具: {name}"
        return tool(args)

    def prompt_block(self) -> str:
        lines = ["## 可用工具"]
        for t in self._tools.values():
            lines.append(f"  <tool name=\"{t.name}\"> — {t.description}")
        lines.append("")
        lines.append("使用格式: <tool name=\"工具名\">参数</tool>")
        lines.append("系统自动执行并返回结果，然后你结合结果继续思考。")
        lines.append("重复思考-工具-观察 循环直到任务完成，然后给出最终答案。")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# 内置工具实现
# ──────────────────────────────────────────────

def _tool_recall(args: str) -> str:
    """从知识图谱中召回知识。"""
    from knowledge_graph import recall_text
    topic = args.strip()
    if not topic:
        return ""
    result = recall_text(topic)
    if result:
        return f"[图谱召回: {topic}]\n{result}"
    return f"[未在知识图谱中找到: {topic}]"


def _tool_read(args: str) -> str:
    """读取本地文件内容。"""
    path = args.strip().strip("\"'")
    if not path:
        return ""
    p = Path(path)
    if not p.is_absolute():
        p = _here / p
    if not p.exists():
        return f"[错误] 文件不存在: {p}"
    if p.is_dir():
        return f"[错误] 是目录不是文件: {p}"
    if p.stat().st_size > 100000:
        return f"[错误] 文件太大 (>100KB): {p}"
    try:
        return p.read_text(encoding="utf-8")[:5000]
    except UnicodeDecodeError:
        try:
            return p.read_text(encoding="gbk")[:5000]
        except Exception:
            return "[错误] 无法解码文件"


def _tool_exec(args: str) -> str:
    """在系统终端中执行命令。"""
    cmd = args.strip()
    if not cmd:
        return ""
    try:
        r = subprocess.run(
            cmd, shell=True, capture_output=True, text=False, timeout=60
        )
        def _safe_decode(b: bytes) -> str:
            try:
                return b.decode("utf-8", errors="replace")
            except Exception:
                return b.decode("gbk", errors="replace")
        out = _safe_decode(r.stdout or b"")[:3000]
        err = _safe_decode(r.stderr or b"")[:2000]
        result = ""
        if out:
            result += out
        if err:
            if result:
                result += "\n--- stderr ---\n"
            result += err
        if not result:
            result = f"(exit code: {r.returncode}, 无输出)"
        return result
    except subprocess.TimeoutExpired:
        return "[错误] 命令超时 (60s)"
    except Exception as e:
        return f"[错误] {e}"


def _tool_think(args: str) -> str:
    """内部推理思考——做计划、分析、推理用。"""
    return f"[思考: {args.strip()}]"


def _tool_write(args: str) -> str:
    """写入或创建文件。参数格式: 路径\n\n内容"""
    text = args.strip()
    if "\n\n" not in text:
        return "[错误] 格式: 路径\\n\\n内容"
    path_str, content = text.split("\n\n", 1)
    path_str = path_str.strip().strip("\"'")
    if not path_str:
        return ""
    p = Path(path_str)
    if not p.is_absolute():
        p = _here / p
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content.strip(), encoding="utf-8")
    return f"[已写入 {len(content.strip())} 字节到 {p}]"


def _tool_web_search(args: str) -> str:
    """搜索互联网。"""
    query = args.strip()
    if not query:
        return ""
    try:
        import httpx
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        resp = httpx.get(url, timeout=15, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        # 简单提取搜索结果片段
        import re
        results = re.findall(
            r'<a rel="nofollow" class="result__a" href="(.*?)".*?>.*?<a class="result__snippet".*?>(.*?)</a>',
            resp.text, re.DOTALL
        )[:5]
        if not results:
            return "(搜索结果为空)"
        lines = []
        for i, (link, snippet) in enumerate(results, 1):
            clean = re.sub(r'<[^>]+>', '', snippet).strip()
            lines.append(f"{i}. {clean}\n   {link}")
        return "\n".join(lines)
    except Exception as e:
        return f"[搜索失败] {e}"


def _tool_web_fetch(args: str) -> str:
    """获取网页内容。参数: URL"""
    url = args.strip()
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    try:
        import httpx
        resp = httpx.get(url, timeout=30, follow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        resp.raise_for_status()
        text = resp.text
        # 提取纯文本
        import re
        text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
        text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
        text = re.sub(r'<[^>]+>', ' ', text)
        text = re.sub(r'\s+', ' ', text).strip()
        return text[:4000]
    except Exception as e:
        return f"[获取失败] {e}"


PLAN_FILE = _here / "_plan.json"


def _tool_plan(args: str) -> str:
    """任务规划: list / add / done / clear"""
    cmd = args.strip()
    plan: list[dict] = []
    if PLAN_FILE.exists():
        plan = json.loads(PLAN_FILE.read_text("utf-8"))

    if cmd == "list":
        if not plan:
            return "(无规划任务)"
        lines = []
        for i, t in enumerate(plan, 1):
            status = "✓" if t.get("done") else "○"
            lines.append(f"{i}. [{status}] {t['task']}")
        return "\n".join(lines)

    elif cmd.startswith("add "):
        task_text = cmd[4:].strip()
        plan.append({"task": task_text, "done": False})
        PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
        return f"[已添加任务: {task_text}]"

    elif cmd.startswith("done "):
        try:
            idx = int(cmd[5:].strip()) - 1
            if 0 <= idx < len(plan):
                plan[idx]["done"] = True
                PLAN_FILE.write_text(json.dumps(plan, ensure_ascii=False, indent=2))
                return f"[已完成: {plan[idx]['task']}]"
            return "[错误] 序号无效"
        except ValueError:
            return "[错误] 用法: plan done <序号>"

    elif cmd == "clear":
        PLAN_FILE.unlink(missing_ok=True)
        return "[已清空任务列表]"

    else:
        return "用法: plan add/ list/ done <N>/ clear"


# ──────────────────────────────────────────────
# 默认注册表
# ──────────────────────────────────────────────

def default_registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register("recall", Tool("recall", "从知识图谱中查询相关知识", _tool_recall))
    reg.register("read", Tool("read", "读取本地文件内容", _tool_read))
    reg.register("write", Tool("write", "写入/创建文件。参数: 路径\\n\\n内容", _tool_write))
    reg.register("exec", Tool("exec", "在系统终端执行命令（shell）", _tool_exec))
    reg.register("web_search", Tool("web_search", "搜索互联网获取最新信息", _tool_web_search))
    reg.register("web_fetch", Tool("web_fetch", "获取网页内容。参数: URL", _tool_web_fetch))
    reg.register("think", Tool("think", "内部推理思考、做计划", _tool_think))
    reg.register("plan", Tool("plan", "任务规划管理: add / list / done <N> / clear", _tool_plan))
    return reg
