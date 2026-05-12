"""四弟 LLM 推理层 — 万厂统一接口 · 配置驱动 · 智能路由

支持 12+ 厂商：OpenAI 兼容群组（7家） + 自定义适配器（5家）。
配置文件驱动，一个 dict 切换模型，自动 fallback。
"""

from __future__ import annotations

import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncIterator


# ──────────────────────────────────────────────
# 数据模型
# ──────────────────────────────────────────────

class Role(Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


@dataclass
class Message:
    role: Role
    content: str
    tool_call_id: str | None = None
    name: str | None = None


@dataclass
class ToolDef:
    name: str
    description: str
    parameters: dict


@dataclass
class LLMRequest:
    model: str
    messages: list[Message]
    tools: list[ToolDef] | None = None
    temperature: float | None = 0.7
    max_tokens: int | None = None
    stream: bool = False


@dataclass
class LLMResponse:
    content: str
    model: str
    provider: str
    usage: dict | None = None
    latency_ms: float = 0.0
    tool_calls: list[dict] | None = None

    @property
    def finish_reason(self) -> str:
        return 'tool_calls' if self.tool_calls else 'stop'


@dataclass
class ProviderConfig:
    """厂商配置 — 从环境变量+一个 dict 就能初始化一个 provider。"""
    name: str
    api_key_env: str              # 环境变量名（如 "DEEPSEEK_API_KEY"）
    base_url: str                 # API 端点
    models: list[str] = field(default_factory=list)
    priority: int = 0             # 越高越优先
    provider_type: str = "openai-compatible"  # openai-compatible | anthropic | gemini | cohere | bedrock | ollama
    api_key: str | None = None    # 不设置则从环境变量读

    def resolve_key(self) -> str | None:
        return self.api_key or os.environ.get(self.api_key_env)


# ──────────────────────────────────────────────
# 统一接口
# ──────────────────────────────────────────────

class LLMProvider(ABC):
    name: str = ""
    models: list[str] = []

    @abstractmethod
    def complete(self, request: LLMRequest) -> LLMResponse:
        ...

    @abstractmethod
    def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        ...

    @abstractmethod
    def count_tokens(self, text: str) -> int:
        ...


# ──────────────────────────────────────────────
# Group A: OpenAI 兼容群组（7+ 厂商）
# 共享同一套 messages/tools/streaming 格式
# ──────────────────────────────────────────────

class OpenAIProvider(LLMProvider):
    """OpenAI / 全兼容接口 — base_url 决定哪个厂商。"""
    name = "openai"
    models = ["gpt-4o", "gpt-4o-mini", "o3-mini", "gpt-4.1", "gpt-4.1-mini"]

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.environ.get("OPENAI_BASE_URL", "")
                         ).rstrip('/') or "https://api.openai.com/v1"
        if not self.api_key:
            raise ValueError(f"OPENAI_API_KEY 未设置（base_url={self.base_url}）")

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    def _build_body(self, request: LLMRequest) -> dict:
        body = {
            "model": request.model,
            "messages": [{"role": m.role.value, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "stream": request.stream,
        }
        if request.max_tokens:
            body["max_tokens"] = request.max_tokens
        if request.tools:
            body["tools"] = [{
                "type": "function",
                "function": {"name": t.name, "description": t.description, "parameters": t.parameters}
            } for t in request.tools]
        return body

    def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx
        t0 = time.time()
        body = self._build_body(request)
        body["stream"] = False
        resp = httpx.post(f"{self.base_url}/chat/completions", headers=self._headers(), json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        latency = (time.time() - t0) * 1000
        return LLMResponse(
            content=choice["message"].get("content", "") or "",
            model=data.get("model", request.model),
            provider=self.name,
            usage=data.get("usage"),
            latency_ms=latency,
            tool_calls=choice["message"].get("tool_calls"),
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        import httpx
        body = self._build_body(request)
        body["stream"] = True
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions",
                                      headers=self._headers(), json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        delta = chunk.get("choices", [{}])[0].get("delta", {})
                        if content := delta.get("content"):
                            yield content

    def count_tokens(self, text: str) -> int:
        en = sum(1 for c in text if c.isascii())
        cn = len(text) - en
        return en // 4 + cn + 4


# ── OpenAI 兼容厂商工厂 ──
# 每个厂商 = OpenAIProvider + 不同的 base_url + 自定义 env var

PROVIDER_ALIASES: dict[str, tuple[str, str, list[str]]] = {
    # (env_var_name, base_url, default_models)
    "deepseek":   ("DEEPSEEK_API_KEY",    "https://api.deepseek.com",              ["deepseek-chat", "deepseek-reasoner"]),
    "grok":       ("XAI_API_KEY",         "https://api.x.ai/v1",                   ["grok-2", "grok-3"]),
    "together":   ("TOGETHER_API_KEY",    "https://api.together.xyz/v1",           ["meta-llama/Llama-3.3-70B-Instruct"]),
    "groq":       ("GROQ_API_KEY",        "https://api.groq.com/openai/v1",        ["llama-3.3-70b-versatile", "mixtral-8x7b-32768"]),
    "openrouter": ("OPENROUTER_API_KEY",  "https://openrouter.ai/api/v1",          ["openai/gpt-4o", "anthropic/claude-sonnet-4"]),
    "mistral":    ("MISTRAL_API_KEY",     "https://api.mistral.ai/v1",             ["mistral-large-latest", "mistral-small-latest"]),
    "azure":      ("AZURE_OPENAI_KEY",    None,                                    ["gpt-4o"]),  # base_url 需要额外设置
}


class OpenAICompatibleProvider(OpenAIProvider):
    """任意 OpenAI 兼容厂商。"""
    def __init__(self, config: ProviderConfig):
        self.name = config.name
        self.models = config.models
        api_key = config.resolve_key()
        if not api_key:
            raise ValueError(f"{config.name}: {config.api_key_env} 未设置")
        self.api_key = api_key
        self.base_url = config.base_url.rstrip('/')


def create_openai_compatible(name: str) -> OpenAICompatibleProvider | None:
    """从 PROVIDER_ALIASES 创建一个兼容 provider（有 key 时）。"""
    if name not in PROVIDER_ALIASES:
        return None
    env_var, base_url, models = PROVIDER_ALIASES[name]
    key = os.environ.get(env_var)
    if not key:
        return None
    cfg = ProviderConfig(name=name, api_key_env=env_var, base_url=base_url or "",
                         models=models, provider_type="openai-compatible", api_key=key)
    return OpenAICompatibleProvider(cfg)


# ──────────────────────────────────────────────
# Group B: Anthropic（已有）
# ──────────────────────────────────────────────

class AnthropicProvider(LLMProvider):
    name = "anthropic"
    models = ["claude-sonnet-4-6", "claude-opus-4-7", "claude-haiku-4-5"]

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.base_url = (base_url or "https://api.anthropic.com/v1").rstrip('/')
        if not self.api_key:
            raise ValueError("ANTHROPIC_API_KEY 未设置")

    def _headers(self) -> dict:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"}

    def _build_body(self, request: LLMRequest) -> dict:
        system = None
        messages = []
        for m in request.messages:
            if m.role == Role.SYSTEM:
                system = m.content
            else:
                messages.append({"role": m.role.value, "content": m.content})
        body = {"model": request.model, "messages": messages,
                "max_tokens": request.max_tokens or 4096, "stream": request.stream}
        if system:
            body["system"] = system
        if request.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters}
                             for t in request.tools]
        return body

    def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx
        t0 = time.time()
        body = self._build_body(request)
        body["stream"] = False
        resp = httpx.post(f"{self.base_url}/messages", headers=self._headers(), json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.time() - t0) * 1000
        return LLMResponse(
            content=data["content"][0]["text"] if data.get("content") else "",
            model=data.get("model", request.model),
            provider=self.name,
            usage={"input_tokens": data.get("usage", {}).get("input_tokens"),
                   "output_tokens": data.get("usage", {}).get("output_tokens")},
            latency_ms=latency,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        import httpx
        body = self._build_body(request)
        body["stream"] = True
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", f"{self.base_url}/messages",
                                      headers=self._headers(), json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content_block_delta":
                            if text := chunk.get("delta", {}).get("text"):
                                yield text

    def count_tokens(self, text: str) -> int:
        en = sum(1 for c in text if c.isascii())
        cn = len(text) - en
        return en // 4 + cn + 4


# ──────────────────────────────────────────────
# Group C: Google Gemini
# ──────────────────────────────────────────────

class GeminiProvider(LLMProvider):
    """Google Gemini API（google-genai SDK / REST）。"""
    name = "gemini"
    models = ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"]

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY 未设置")

    def _build_contents(self, request: LLMRequest) -> tuple[list[dict], str | None]:
        system = None
        contents = []
        for m in request.messages:
            if m.role == Role.SYSTEM:
                system = m.content
            else:
                role = "model" if m.role == Role.ASSISTANT else "user"
                contents.append({"role": role, "parts": [{"text": m.content}]})
        return contents, system

    def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx
        t0 = time.time()
        contents, system = self._build_contents(request)
        body = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        if request.tools:
            body["tools"] = [{"functionDeclarations": [
                {"name": t.name, "description": t.description, "parameters": t.parameters}
                for t in request.tools
            ]}]
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:generateContent"
        resp = httpx.post(url, params={"key": self.api_key}, json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.time() - t0) * 1000
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            pass
        return LLMResponse(content=text, model=request.model, provider=self.name,
                           usage=data.get("usageMetadata"), latency_ms=latency)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        import httpx
        contents, system = self._build_contents(request)
        body = {"contents": contents}
        if system:
            body["systemInstruction"] = {"parts": [{"text": system}]}
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{request.model}:streamGenerateContent"
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", url, params={"key": self.api_key}, json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: ") and line != "data: [DONE]":
                        chunk = json.loads(line[6:])
                        try:
                            text = chunk["candidates"][0]["content"]["parts"][0]["text"]
                            yield text
                        except (KeyError, IndexError):
                            pass

    def count_tokens(self, text: str) -> int:
        en = sum(1 for c in text if c.isascii())
        cn = len(text) - en
        return en // 4 + cn + 4


# ──────────────────────────────────────────────
# Group D: Cohere
# ──────────────────────────────────────────────

class CohereProvider(LLMProvider):
    """Cohere Command R+ / R（v2 API，接近 OpenAI 格式）。"""
    name = "cohere"
    models = ["command-r-plus", "command-r", "command-a"]

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("COHERE_API_KEY", "")
        if not self.api_key:
            raise ValueError("COHERE_API_KEY 未设置")

    def complete(self, request: LLMRequest) -> LLMResponse:
        import httpx
        t0 = time.time()
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
        body = {"model": request.model, "messages": messages}
        if request.tools:
            body["tools"] = [{"name": t.name, "description": t.description, "parameter_definitions": t.parameters}
                             for t in request.tools]
        resp = httpx.post("https://api.cohere.com/v2/chat",
                          headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                          json=body, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        latency = (time.time() - t0) * 1000
        return LLMResponse(
            content=data.get("message", {}).get("content", [{}])[0].get("text", ""),
            model=request.model, provider=self.name,
            usage=data.get("usage"), latency_ms=latency,
        )

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        import httpx
        messages = [{"role": m.role.value, "content": m.content} for m in request.messages]
        body = {"model": request.model, "messages": messages, "stream": True}
        async with httpx.AsyncClient(timeout=120) as client:
            async with client.stream("POST", "https://api.cohere.com/v2/chat",
                                      headers={"Authorization": f"Bearer {self.api_key}",
                                               "Content-Type": "application/json"},
                                      json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        chunk = json.loads(line[6:])
                        if chunk.get("type") == "content-delta":
                            if text := chunk.get("delta", {}).get("message", {}).get("content", {}).get("text"):
                                yield text

    def count_tokens(self, text: str) -> int:
        en = sum(1 for c in text if c.isascii())
        cn = len(text) - en
        return en // 4 + cn + 4


# ──────────────────────────────────────────────
# Group E: Amazon Bedrock
# ──────────────────────────────────────────────

class BedrockProvider(LLMProvider):
    """Amazon Bedrock Converse API（需 boto3 + AWS 凭证）。"""
    name = "bedrock"
    models = ["anthropic.claude-sonnet-4", "anthropic.claude-opus-4",
              "meta.llama3-70b-instruct", "amazon.titan-text-premier"]

    def __init__(self, region: str | None = None):
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        # boto3 会在运行时检查 AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY

    def complete(self, request: LLMRequest) -> LLMResponse:
        try:
            import boto3
        except ImportError:
            raise RuntimeError("BedrockProvider 需要 boto3: pip install boto3")
        t0 = time.time()
        client = boto3.client("bedrock-runtime", region_name=self.region)
        messages = [{"role": m.role.value, "content": [{"text": m.content}]} for m in request.messages]
        body = {"modelId": request.model, "messages": messages, "inferenceConfig": {"maxTokens": request.max_tokens or 4096}}
        resp = client.converse(**body)
        latency = (time.time() - t0) * 1000
        text = ""
        try:
            text = resp["output"]["message"]["content"][0]["text"]
        except (KeyError, IndexError):
            pass
        return LLMResponse(content=text, model=request.model, provider=self.name,
                           usage={"input_tokens": resp.get("usage", {}).get("inputTokens"),
                                  "output_tokens": resp.get("usage", {}).get("outputTokens")},
                           latency_ms=latency)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        # Bedrock 目前不支持异步流式的通用接口，降级为同步
        yield self.complete(request).content

    def count_tokens(self, text: str) -> int:
        en = sum(1 for c in text if c.isascii())
        cn = len(text) - en
        return en // 4 + cn + 4


# ──────────────────────────────────────────────
# Group F: Ollama（本地）
# ──────────────────────────────────────────────

class OllamaProvider(LLMProvider):
    name = "ollama"
    models = []

    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        try:
            import httpx
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            if resp.status_code == 200:
                self.models = [m["name"] for m in resp.json().get("models", [])]
        except Exception:
            self.models = []

    def _inner(self) -> OpenAIProvider:
        p = OpenAIProvider.__new__(OpenAIProvider)
        p.api_key = "ollama"
        p.base_url = self.base_url + "/v1"
        p.name = "ollama"
        return p

    def complete(self, request: LLMRequest) -> LLMResponse:
        return self._inner().complete(request)

    async def stream(self, request: LLMRequest) -> AsyncIterator[str]:
        async for chunk in self._inner().stream(request):
            yield chunk

    def count_tokens(self, text: str) -> int:
        return self._inner().count_tokens(text)


# ──────────────────────────────────────────────
# 工厂函数 — 从配置自动创建 provider
# ──────────────────────────────────────────────

def create_provider(config: ProviderConfig) -> LLMProvider | None:
    """从配置创建 provider。环境变量不存在时返回 None。"""
    key = config.resolve_key()
    if not key and config.provider_type not in ("ollama", "bedrock"):
        return None

    try:
        if config.provider_type == "openai-compatible":
            return OpenAICompatibleProvider(config)
        elif config.provider_type == "anthropic":
            return AnthropicProvider(api_key=key)
        elif config.provider_type == "gemini":
            return GeminiProvider(api_key=key)
        elif config.provider_type == "cohere":
            return CohereProvider(api_key=key)
        elif config.provider_type == "bedrock":
            return BedrockProvider()
        elif config.provider_type == "ollama":
            return OllamaProvider()
        else:
            return None
    except (ValueError, ImportError):
        return None


def auto_discover_providers() -> list[tuple[str, LLMProvider, int]]:
    """自动发现所有有 API key 的 provider。返回 [(name, provider, priority)]。"""
    discovered = []

    # Anthropic
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            discovered.append(("anthropic", AnthropicProvider(), 100))
        except Exception:
            pass

    # OpenAI
    if os.environ.get("OPENAI_API_KEY"):
        try:
            discovered.append(("openai", OpenAIProvider(), 90))
        except Exception:
            pass

    # OpenAI 兼容厂商
    for alias in PROVIDER_ALIASES:
        try:
            p = create_openai_compatible(alias)
            if p:
                priority = {"deepseek": 80, "groq": 70, "mistral": 65,
                            "grok": 60, "together": 50, "openrouter": 85,
                            "azure": 75}.get(alias, 40)
                discovered.append((alias, p, priority))
        except Exception:
            pass

    # Gemini
    if os.environ.get("GEMINI_API_KEY"):
        try:
            discovered.append(("gemini", GeminiProvider(), 85))
        except Exception:
            pass

    # Cohere
    if os.environ.get("COHERE_API_KEY"):
        try:
            discovered.append(("cohere", CohereProvider(), 50))
        except Exception:
            pass

    # Ollama（无 key，本地）
    try:
        o = OllamaProvider()
        if o.models:
            discovered.append(("ollama", o, 30))
    except Exception:
        pass

    return discovered


# ──────────────────────────────────────────────
# 智能路由
# ──────────────────────────────────────────────

@dataclass
class ProviderStats:
    total_calls: int = 0
    total_latency: float = 0.0
    total_cost: float = 0.0
    errors: int = 0
    last_error: str = ""
    total_tokens: int = 0

    @property
    def avg_latency(self) -> float:
        return self.total_latency / max(self.total_calls, 1)

    @property
    def error_rate(self) -> float:
        return self.errors / max(self.total_calls, 1)


# 粗略单价（USD / 1K tokens，仅估算路由决策用）
MODEL_COST_ESTIMATE = {
    "gpt-4o": (0.005, 0.015),
    "gpt-4o-mini": (0.00015, 0.0006),
    "claude-sonnet-4-6": (0.003, 0.015),
    "claude-opus-4-7": (0.015, 0.075),
    "claude-haiku-4-5": (0.00025, 0.00125),
    "deepseek-chat": (0.00014, 0.00028),
    "gemini-2.5-flash": (0.00015, 0.0006),
    "gemini-2.5-pro": (0.00125, 0.005),
}


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """估算调用成本。"""
    rates = MODEL_COST_ESTIMATE.get(model)
    if not rates:
        return 0.0
    return (input_tokens / 1000) * rates[0] + (output_tokens / 1000) * rates[1]


class RouterStrategy(Enum):
    PRIORITY = "priority"        # 按 preset 优先级
    LATENCY = "latency"          # 选延迟最低的
    COST = "cost"                # 选成本最低的
    ROUND_ROBIN = "round-robin"  # 轮询


class ProviderRegistry:
    """厂商注册表 + 智能路由 + 统计。"""

    def __init__(self, strategy: RouterStrategy = RouterStrategy.PRIORITY):
        self._providers: dict[str, LLMProvider] = {}
        self._priority: dict[str, int] = {}
        self._stats: dict[str, ProviderStats] = {}
        self._strategy = strategy
        self._rr_index: dict[str, int] = {}  # round-robin 计数

    @classmethod
    def from_auto_discover(cls, strategy: RouterStrategy = RouterStrategy.PRIORITY):
        """自动发现所有可用的 provider。"""
        reg = cls(strategy=strategy)
        for name, provider, priority in auto_discover_providers():
            reg.register(name, provider, priority)
        return reg

    @classmethod
    def from_config(cls, configs: list[ProviderConfig], strategy: RouterStrategy = RouterStrategy.PRIORITY):
        """从配置列表创建。"""
        reg = cls(strategy=strategy)
        for cfg in configs:
            provider = create_provider(cfg)
            if provider:
                reg.register(cfg.name, provider, cfg.priority)
        return reg

    def register(self, name: str, provider: LLMProvider, priority: int = 0):
        self._providers[name] = provider
        self._priority[name] = priority
        self._stats[name] = ProviderStats()

    def health_check(self, name: str | None = None, timeout: float = 5.0) -> dict[str, bool]:
        """对 provider 做健康检查（发一个轻量请求看是否响应）。

        Args:
            name: 指定 provider，None 则检查全部
            timeout: 超时秒数

        Returns:
            {provider_name: is_healthy}
        """
        results: dict[str, bool] = {}
        targets = [name] if name else list(self._providers.keys())
        for n in targets:
            provider = self._providers.get(n)
            if not provider:
                results[n] = False
                continue
            try:
                req = LLMRequest(
                    model=list(provider.models)[0] if provider.models else "unknown",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                )
                resp = provider.complete(req)
                results[n] = resp.content is not None
            except Exception:
                results[n] = False
        return results

    @property
    def healthy_providers(self) -> list[str]:
        return [n for n, ok in self.health_check().items() if ok]

    def get(self, name: str) -> LLMProvider | None:
        return self._providers.get(name)

    @property
    def available(self) -> list[str]:
        return list(self._providers.keys())

    @property
    def all_providers(self) -> dict[str, LLMProvider]:
        return dict(self._providers)

    def complete(self, request: LLMRequest, strategy: RouterStrategy | None = None) -> LLMResponse:
        """自动路由：按策略选择 provider，失败则 fallback。"""
        strat = strategy or self._strategy
        # provider:model 语法 → 直接路由
        if ':' in request.model:
            return self._route_direct(request)

        ordered = self._ordered_providers(strat)
        last_error = ""

        for name in ordered:
            provider = self._providers.get(name)
            if not provider:
                continue
            try:
                req = LLMRequest(
                    model=request.model,
                    messages=request.messages,
                    tools=request.tools,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    stream=False,
                )
                resp = provider.complete(req)
                self._record_success(name, resp)
                return resp
            except Exception as e:
                last_error = str(e)
                self._record_error(name, e)
                continue

        raise RuntimeError(f"所有 provider 都失败了。最后错误: {last_error}")

    def _ordered_providers(self, strategy: RouterStrategy) -> list[str]:
        names = list(self._providers.keys())
        if strategy == RouterStrategy.PRIORITY:
            return sorted(names, key=lambda n: self._priority.get(n, 0), reverse=True)
        elif strategy == RouterStrategy.LATENCY:
            return sorted(names, key=lambda n: self._stats[n].avg_latency if self._stats[n].total_calls > 0 else 0)
        elif strategy == RouterStrategy.COST:
            return sorted(names, key=lambda n: self._stats[n].total_cost)
        elif strategy == RouterStrategy.ROUND_ROBIN:
            i = self._rr_index.get("_rr", 0)
            self._rr_index["_rr"] = (i + 1) % max(len(names), 1)
            return names[i:] + names[:i]
        return names

    def _route_direct(self, request: LLMRequest) -> LLMResponse:
        provider_name, model_name = request.model.split(':', 1)
        provider = self._providers.get(provider_name)
        if not provider:
            raise RuntimeError(f"未知 provider: {provider_name}")
        req = LLMRequest(
            model=model_name,
            messages=request.messages,
            tools=request.tools,
            temperature=request.temperature,
            max_tokens=request.max_tokens,
            stream=False,
        )
        resp = provider.complete(req)
        self._record_success(provider_name, resp)
        return resp

    def _record_success(self, name: str, resp: LLMResponse):
        s = self._stats[name]
        s.total_calls += 1
        s.total_latency += resp.latency_ms
        if resp.usage:
            t = resp.usage.get("input_tokens", 0) + resp.usage.get("output_tokens", 0)
            s.total_tokens += t
            s.total_cost += estimate_cost(resp.model,
                                          resp.usage.get("input_tokens", 0),
                                          resp.usage.get("output_tokens", 0))

    def _record_error(self, name: str, error: Exception):
        s = self._stats[name]
        s.errors += 1
        s.last_error = str(error)[:200]

    def stats_report(self) -> str:
        lines = ["LLM Provider 统计:"]
        for name, stats in sorted(self._stats.items()):
            lines.append(
                f"  {name}: {stats.total_calls} calls, "
                f"avg {stats.avg_latency:.0f}ms, "
                f"errors {stats.errors}, "
                f"cost ${stats.total_cost:.4f}, "
                f"tokens {stats.total_tokens}"
            )
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

def _test_token_count():
    p = OpenAIProvider.__new__(OpenAIProvider)
    assert p.count_tokens("hello world") > 0
    assert p.count_tokens("你好世界") > 0
    print("  [LLM:TokenCount] 通过")

def _test_provider_aliases():
    """验证所有厂商别名的 env var 和 base_url 配置正确。"""
    assert PROVIDER_ALIASES["deepseek"][0] == "DEEPSEEK_API_KEY"
    assert PROVIDER_ALIASES["deepseek"][1] == "https://api.deepseek.com"
    assert PROVIDER_ALIASES["grok"][1] == "https://api.x.ai/v1"
    assert PROVIDER_ALIASES["openrouter"][1] == "https://openrouter.ai/api/v1"
    assert PROVIDER_ALIASES["mistral"][1] == "https://api.mistral.ai/v1"
    assert len(PROVIDER_ALIASES) >= 7
    print(f"  [LLM:Aliases] {len(PROVIDER_ALIASES)} 个别名通过")

def _test_routing():
    reg = ProviderRegistry()
    class FakeProvider(LLMProvider):
        def __init__(self, name): self.name = name; self.models = []
        def complete(self, request): return LLMResponse(content=f"fake-{self.name}", model=request.model, provider=self.name)
        async def stream(self, request): yield "fake"
        def count_tokens(self, text): return 10

    reg.register("provider_a", FakeProvider("provider_a"), priority=10)
    reg.register("provider_b", FakeProvider("provider_b"), priority=5)

    req = LLMRequest(model="test", messages=[Message(Role.USER, "hi")])
    resp = reg.complete(req)
    assert resp.content == "fake-provider_a"
    print("  [LLM:Router] 正常路由通过")
    print("  [LLM:Router] 通过")

def _test_auto_discover():
    """测试 auto_discover 不崩溃（不管有没有 key）。"""
    providers = auto_discover_providers()
    print(f"  [LLM:AutoDiscover] 发现 {len(providers)} 个 provider (有 key 时才加载)")
    for name, p, priority in providers:
        print(f"    - {name} (priority={priority}, models={len(p.models)})")

if __name__ == '__main__':
    print("═══ LLM Provider 层自测 ═══\n")
    _test_token_count()
    _test_provider_aliases()
    _test_routing()
    _test_auto_discover()
    print("\n✅ LLM 层自测通过（未发真实 API 请求）")
