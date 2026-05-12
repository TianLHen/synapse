"""Synapse Agent — 交互式 AI Agent 对话终端。

用法:
    synapse                 # 进入对话模式
    /recall <topic>         # 召回知识
    /status                 # 图谱状态
    /model                  # 当前 LLM 模型
    /help                   # 帮助
    /exit                   # 退出
"""

import sys
import os
from pathlib import Path

# Windows GBK 终端兼容
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

# 自动加载 .env 文件
_here = Path(__file__).resolve().parent
_env_file = _here / ".env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip("\"'")
        if key and val:
            os.environ.setdefault(key, val)

if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from llm import (
    auto_discover_providers, ProviderRegistry, RouterStrategy,
    LLMRequest, Message, Role,
)
from knowledge_graph import recall_text, status_text

PROMPT = "\nSynapse > "
MODEL = os.environ.get("ANTHROPIC_MODEL") or os.environ.get("LLM_MODEL", "claude-sonnet-4-6")

SYSTEM_PROMPT = """你是 Synapse，一个 AI 知识图谱 agent。
你有自己的知识图谱，存了大量关于 AI agent 自我进化、认知科学、逻辑学、
控制论、认识论、神经科学的知识。

你可以：
- 用 /recall <topic> 从图谱中召回相关知识
- 用 /status 查看图谱状态
- 用 /model 查看当前使用的模型

回答问题时，如果涉及图谱中的知识，请先 /recall 相关主题再用知识回答。
保持简洁、精准。"""


ENV_HINTS = {
    "anthropic": "ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
}


def _init_llm():
    providers = auto_discover_providers()
    if not providers:
        print("  !! 没有找到可用的 LLM provider。")
        print("  请设置环境变量:")
        print("    ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL (当前路线)")
        print("    或 OPENAI_API_KEY / DEEPSEEK_API_KEY / GEMINI_API_KEY 等\n")
        return None
    reg = ProviderRegistry(strategy=RouterStrategy.PRIORITY)
    active = []
    for name, provider, priority in providers:
        reg.register(name, provider, priority)
        active.append(name)
    print(f"  provider: {', '.join(active)}")
    return reg


def _build_messages(history: list[dict], user_input: str) -> list[Message]:
    msgs = [Message(role=Role.SYSTEM, content=SYSTEM_PROMPT)]
    for h in history:
        msgs.append(Message(role=Role.USER, content=h["user"]))
        msgs.append(Message(role=Role.ASSISTANT, content=h["assistant"]))
    msgs.append(Message(role=Role.USER, content=user_input))
    return msgs


def _do_recall(topic: str) -> str:
    result = recall_text(topic)
    if result:
        return f"[从知识图谱召回: {topic}]\n{result}"
    return f"[图谱中未找到: {topic}]"


def _do_status() -> str:
    return status_text()


def _handle_slash(cmd: str, history: list[dict]) -> str | None:
    parts = cmd.strip().split(maxsplit=1)
    base = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if base in ("/exit", "/quit", "/q"):
        print("\n再见！")
        sys.exit(0)
    elif base == "/help":
        return (
            "命令:\n"
            "  /recall <topic>    从知识图谱召回知识\n"
            "  /status            查看图谱状态\n"
            "  /model             查看当前 LLM 模型\n"
            "  /help              显示帮助\n"
            "  /exit              退出\n"
            "其他消息直接输入，Synapse 会结合图谱知识回答。"
        )
    elif base == "/recall":
        if not arg:
            return "用法: /recall <topic>"
        return _do_recall(arg)
    elif base == "/status":
        return _do_status()
    elif base == "/model":
        return f"当前模型: {MODEL}"
    return None


def chat_loop():
    reg = _init_llm()
    if not reg:
        return

    provider_name = reg.available[0]
    print(f"  模型: {MODEL} @ {provider_name}")
    print("  输入 /help 查看命令")
    print()

    history: list[dict] = []
    while True:
        try:
            user_input = input(PROMPT).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见！")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            reply = _handle_slash(user_input, history)
            if reply is not None:
                print(f"\n{reply}\n")
            continue

        try:
            messages = _build_messages(history, user_input)
            req = LLMRequest(
                model=MODEL,
                messages=messages,
                temperature=0.7,
                max_tokens=4096,
            )
            resp = reg.complete(req)
            reply = resp.content.strip()

            history.append({"user": user_input, "assistant": reply})
            if len(history) > 20:
                history = history[-20:]

            print(f"\n{reply}\n")

            usage = resp.usage or {}
            tok = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
            print(f"  [token: {tok}  latency: {resp.latency_ms:.0f}ms]")

        except Exception as e:
            print(f"\n  [!] 调用出错: {e}\n")


def main():
    chat_loop()


if __name__ == "__main__":
    main()
