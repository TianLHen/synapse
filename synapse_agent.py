"""Synapse Agent — ReAct 循环 · 工具调用 · 对话终端

用法:
    synapse                   # 进入 agent 对话模式
    synapse status            # 图谱状态（非对话）
    /help                     # 帮助
"""

import sys
import os
import re
from pathlib import Path

# Windows GBK 终端兼容
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

# 自动加载 .env
_here = Path(__file__).resolve().parent
_env_file = _here / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _, _v = _line.partition("=")
            os.environ.setdefault(_k.strip(), _v.strip().strip("\"'"))

if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from llm import (
    ProviderRegistry, RouterStrategy, auto_discover_providers,
    LLMRequest, Message, Role,
)
from knowledge_graph import recall_text, status_text
from tools import default_registry

MODEL = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("LLM_MODEL", "claude-sonnet-4-6")
MAX_TOOL_ITERATIONS = 20

# ──────────────────────────────────────────────
# System prompt
# ──────────────────────────────────────────────

BASE_SYSTEM = """你是 Synapse，一个通用 AI agent。

你能做的：
- 写代码、读文件、跑命令
- 上网搜索、获取网页
- 从知识图谱中查询知识（我在 AI 自我进化、认知科学等领域有深度积累）
- 多步推理、任务规划

行为守则：
1. 先思考再行动。复杂任务先 plan 再执行。
2. 工具是手段，你的脑子是核心。查到信息后自己分析。
3. 不知道就说不知道，不编造。
4. 保持简洁、精准、有观点。
5. 如果工具报错，换一种方式再试。
6. 任务完成后给出清晰的总结。"""


def _build_system(tools) -> str:
    return BASE_SYSTEM + "\n\n" + tools.prompt_block()


# ──────────────────────────────────────────────
# 工具调用解析
# ──────────────────────────────────────────────

TOOL_PATTERN = re.compile(r'<tool\s+name="([^"]+)"([^>]*)>\s*(.*?)\s*</tool>', re.DOTALL)

def parse_tool_calls(text: str) -> list[tuple[str, str, str]]:
    calls = []
    for m in TOOL_PATTERN.finditer(text):
        name = m.group(1)
        args = (m.group(3) or "").strip()
        calls.append((name, m.group(0), args))
    return calls


# ──────────────────────────────────────────────
# LLM 初始化
# ──────────────────────────────────────────────

def _init_llm():
    providers = auto_discover_providers()
    if not providers:
        print("  !! 没有找到可用的 LLM provider。")
        print("  请检查 .env 文件中的 ANTHROPIC_AUTH_TOKEN")
        return None
    reg = ProviderRegistry(strategy=RouterStrategy.PRIORITY)
    for name, provider, priority in providers:
        reg.register(name, provider, priority)
    return reg


# ──────────────────────────────────────────────
# 对话管理
# ──────────────────────────────────────────────

def _build_messages(history: list[dict], user_input: str, sys_prompt: str) -> list[Message]:
    msgs = [Message(role=Role.SYSTEM, content=sys_prompt)]
    for h in history:
        msgs.append(Message(role=Role.USER, content=h["user"]))
        if h.get("assistant"):
            msgs.append(Message(role=Role.ASSISTANT, content=h["assistant"]))
    msgs.append(Message(role=Role.USER, content=user_input))
    return msgs


def _respond(reg, messages: list[Message]) -> str:
    req = LLMRequest(model=MODEL, messages=messages, temperature=0.7, max_tokens=8192)
    resp = reg.complete(req)
    return resp.content.strip()


def _do_recall(topic: str) -> str:
    result = recall_text(topic)
    if result:
        return f"[图谱召回: {topic}]\n{result}"
    return f"[未在知识图谱中找到: {topic}]"


def _do_status() -> str:
    return status_text()


def _handle_slash(cmd: str) -> str | None:
    parts = cmd.strip().split(maxsplit=1)
    base = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""
    if base == "/help":
        return (
            "命令:\n"
            "  /recall <topic>   手动召回知识\n"
            "  /status           查看图谱状态\n"
            "  /model            查看当前模型\n"
            "  /help             显示帮助\n"
            "  /exit             退出\n"
            "其他消息直接输入，Synapse 会自动决定怎么处理。"
        )
    if base == "/recall":
        if not arg:
            return "用法: /recall <topic>"
        return _do_recall(arg)
    if base == "/status":
        return _do_status()
    if base == "/model":
        return f"当前模型: {MODEL}"
    return None


# ──────────────────────────────────────────────
# ReAct 主循环
# ──────────────────────────────────────────────

def chat_loop():
    reg = _init_llm()
    if not reg:
        return

    tools = default_registry()
    sys_prompt = _build_system(tools)

    print(f"  provider: {', '.join(reg.available)}")
    print(f"  模型: {MODEL}")
    print(f"  工具: {', '.join(tools.names())}")
    print("  输入 /help 查看命令")
    print()

    history: list[dict] = []
    while True:
        try:
            user_input = input("\nSynapse > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        # 斜杠命令
        if user_input.startswith("/"):
            if user_input.lower() in ("/exit", "/quit", "/q"):
                print("\n再见！")
                break
            reply = _handle_slash(user_input)
            if reply is not None:
                print(f"\n{reply}")
            continue

        # ReAct 循环
        messages = _build_messages(history, user_input, sys_prompt)
        final_reply = ""
        tool_iter = 0

        while tool_iter < MAX_TOOL_ITERATIONS:
            tool_iter += 1
            reply = _respond(reg, messages)

            calls = parse_tool_calls(reply)
            if not calls:
                final_reply = reply
                break

            messages.append(Message(role=Role.ASSISTANT, content=reply))
            for name, tag, args in calls:
                result = tools.execute(name, args)
                messages.append(Message(
                    role=Role.USER,
                    content=f"[工具 {name} 返回]\n{result[:4000]}"
                ))
        else:
            final_reply = final_reply or reply

        if final_reply:
            print(f"\n{final_reply}")
            print(f"  [步数: {tool_iter}]")
            history.append({"user": user_input, "assistant": final_reply})
            if len(history) > 20:
                history = history[-20:]


def main():
    chat_loop()


if __name__ == "__main__":
    main()
