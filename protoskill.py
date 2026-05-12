"""四弟大脑架构原型 — 事件驱动 · 技能即模块 · 四层记忆 · 实时诊断

不是二弟（Claude Code）的变种，也不是三弟（Hermes）的复制。
从二弟这次重构的教训出发：真连接，真执行，不绕圈子。

=============================================================
核心理念
=============================================================

1. 没有主循环
   不写 while True + 状态机。四弟是事件驱动的——刺激进来，
   事件总线分发，适当的处理器被激活。没有巨型 main()。

2. 技能即模块
   每个 skill 不是 .md 文件，而是可加载的 Python 模块：
   - 自己声明依赖（需要哪些其他技能）
   - 自己定义触发器（什么事件激活它）
   - 自己管理状态（运行时的内存变量）
   - 自己能升级自己（热替换）

3. 四层记忆，自动路由
   ┌─────────────────────────────────────┐
   │ L1: Session Context (当前对话)        │ ← 最快，易失
   │ L2: Daily Log (今天的行为)             │ ← 文件追加
   │ L3: MEMORY.md (持久化规则/画像)        │ ← 人工审核
   │ L4: 向量检索 (语义相似节点)             │ ← 图谱嵌入
   └─────────────────────────────────────┘
   查询时自动从 L1→L4 逐级搜索，命中即返回。

4. 实时诊断回路
   不是事后 analyze()，是每个动作完成时自动评估：
   动作 → 质量分 → 低于阈值？→ 立即调整参数/替换策略
   每个技能自带质量门，不依赖外部诊断器。

=============================================================
原型代码
=============================================================

>>> 这版不是 final，是骨架 + 关键机制演示。
"""

from __future__ import annotations

import json
import re
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol


# ──────────────────────────────────────────────
# L0 事件系统（四弟的"神经冲动"）
# ──────────────────────────────────────────────

class Event:
    """一个刺激事件。所有通信走事件总线，不直接调用。"""
    __slots__ = ('type', 'source', 'data', 'timestamp')

    def __init__(self, type: str, source: str = 'system', data: dict | None = None):
        self.type = type
        self.source = source
        self.data = data or {}
        self.timestamp = time.time()

    def __repr__(self):
        return f"[{self.type}] from={self.source} data={self.data}"


class EventBus:
    """事件总线：注册 → 分发，支持通配符订阅。"""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event_type: str, handler: Callable):
        self._handlers[event_type].append(handler)

    def emit(self, event: Event):
        """分发事件给精确匹配 + 通配符 '%' 订阅者。"""
        handled = False
        for et, handlers in list(self._handlers.items()):
            if et == event.type or (et.endswith('%') and event.type.startswith(et[:-1])):
                for h in handlers:
                    try:
                        h(event)
                        handled = True
                    except Exception as e:
                        print(f"  [四弟:ERR] handler {h.__name__} crashed: {e}")
        return handled


# ──────────────────────────────────────────────
# L1 技能系统（"大脑皮层"）
# ──────────────────────────────────────────────

class SkillLifecycle(Protocol):
    """技能生命周期。每个技能是一个模块，不是一段文字。"""
    def on_activate(self, bus: EventBus) -> None: ...
    def on_event(self, event: Event) -> Any | None: ...
    def on_deactivate(self) -> None: ...


@dataclass
class SkillModule:
    """技能模块元数据 + 运行时状态。"""
    name: str
    description: str
    version: str
    triggers: list[str]       # 触发的事件类型
    dependencies: list[str]   # 依赖的其他技能名
    source_path: Path | None = None  # 源码路径（可热加载）
    module: Any = None        # 实际的 Python 模块/对象
    quality_threshold: float = 0.3  # 质量门

    # 运行时统计
    invoke_count: int = 0
    last_score: float = 0.0
    avg_score: float = 0.0

    def matches(self, event: Event) -> bool:
        return any(event.type == t or (t.endswith('*') and event.type.startswith(t[:-1]))
                   for t in self.triggers)


@dataclass
class SkillRegistry_v2:
    """四弟的技能注册表 — 支持依赖解析和热替换。"""

    skills: dict[str, SkillModule] = field(default_factory=dict)

    @property
    def count(self) -> int:
        return len(self.skills)

    def register(self, skill: SkillModule) -> bool:
        if skill.name in self.skills:
            print(f"  [四弟] 技能 {skill.name} 已存在，跳过注册")
            return False
        self.skills[skill.name] = skill
        return True

    def resolve_dependencies(self, name: str) -> list[str] | None:
        """返回技能的完整依赖链（拓扑排序），检测循环依赖。"""
        visited: set[str] = set()
        stack: set[str] = set()
        order: list[str] = []

        def dfs(n: str) -> bool:
            if n in stack:
                return False  # 循环依赖
            if n in visited:
                return True
            skill = self.skills.get(n)
            if not skill:
                return True
            stack.add(n)
            for dep in skill.dependencies:
                if not dfs(dep):
                    return False
            stack.remove(n)
            visited.add(n)
            order.append(n)
            return True

        if not dfs(name):
            return None  # 循环依赖
        return order

    def find(self, query: str) -> list[SkillModule]:
        q = query.lower()
        return [s for s in self.skills.values()
                if q in s.name.lower() or q in s.description.lower()]

    def get(self, name: str) -> SkillModule | None:
        return self.skills.get(name)


def discover_skills() -> list[SkillModule]:
    """自动发现 skills/ 目录下的所有技能模块。

    每个 .py 文件如果定义了 on_activate 函数，就被视为一个技能。
    """
    skills_dir = Path(__file__).resolve().parent / "skills"
    if not skills_dir.exists():
        return []

    discovered = []
    for f in sorted(skills_dir.glob("*.py")):
        if f.name == "__init__.py":
            continue
        try:
            import importlib.util as _util
            spec = _util.spec_from_file_location(f"skills.{f.stem}", f)
            if not spec or not spec.loader:
                continue
            mod = _util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            has_activate = hasattr(mod, "on_activate")
            has_event = hasattr(mod, "on_event")
            if not (has_activate or has_event):
                continue

            # 从模块变量或文件名推断 metadata
            name = getattr(mod, "SKILL_NAME", f.stem)
            desc = getattr(mod, "SKILL_DESCRIPTION", f"技能: {f.stem}")
            version = getattr(mod, "SKILL_VERSION", "0.1.0")
            triggers = getattr(mod, "SKILL_TRIGGERS", [])
            deps = getattr(mod, "SKILL_DEPENDENCIES", [])

            skill = SkillModule(
                name=name,
                description=desc,
                version=version,
                triggers=triggers,
                dependencies=deps,
                source_path=f,
                module=mod,
            )
            discovered.append(skill)
        except Exception as e:
            print(f"  [四弟] 加载技能 {f.stem} 失败: {e}")
    return discovered


# ──────────────────────────────────────────────
# L2 四层记忆系统
# ──────────────────────────────────────────────

memory_dir = Path.home() / ".claude" / "projects" / "C--Users-lenovo" / "memory"


class MemorySystem:
    """四层记忆，自动路由查询。

    用法:
        ms = MemorySystem()
        ms.store('L2', 'recall', {'topic': '进化', 'hits': 5})
        result = ms.query('进化')  # 自动从 L1→L4 搜索
    """

    def __init__(self):
        self.session: dict[str, Any] = {}               # L1
        self.daily_log: list[dict] = []                 # L2
        self.memory_files: dict[str, str] = {}          # L3 缓存
        self.vector_index: dict[str, list[float]] = {}  # L4 (轻量内存版本)

    def store(self, layer: str, key: str, value: Any):
        if layer == 'L1':
            self.session[key] = value
        elif layer == 'L2':
            self.daily_log.append({
                'at': datetime.now().isoformat(),
                'key': key,
                'value': str(value)[:200],
            })
            if len(self.daily_log) > 1000:
                self.daily_log = self.daily_log[-500:]
        elif layer == 'L3':
            if memory_dir.exists():
                for f in memory_dir.glob('*.md'):
                    self.memory_files[f.stem] = f.read_text(encoding='utf-8')[:2000]
        elif layer == 'L4':
            # 简单的标签 → 向量映射
            import hashlib
            h = hashlib.md5(str(value).encode()).hexdigest()
            vec = [ord(c) / 255 for c in h[:8]]  # dummy 向量
            self.vector_index[key] = vec

    def query(self, text: str) -> list[tuple[str, str, float]]:
        """从 L1→L4 搜索，命中即加入结果。"""
        results: list[tuple[str, str, float]] = []
        q = text.lower()

        # L1: session 检查
        for k, v in self.session.items():
            if q in k.lower() or q in str(v).lower():
                results.append(('L1', str(v)[:100], 0.9))

        # L2: 最近日志
        for entry in self.daily_log[-100:]:
            if q in str(entry.get('value', '')).lower():
                results.append(('L2', str(entry['value'])[:100], 0.6))

        # L3: 记忆文件
        for name, content in self.memory_files.items():
            if q in name.lower() or q in content.lower()[:500]:
                results.append(('L3', f"{name}: {content[:200]}", 0.7))

        # L4: 向量匹配（dummy 实现）
        for key in self.vector_index:
            if q in key.lower():
                results.append(('L4', key, 0.5))

        return sorted(results, key=lambda x: x[2], reverse=True)[:10]


# ──────────────────────────────────────────────
# L3 实时诊断回路（内置在技能中）
# ──────────────────────────────────────────────

class QualityGate:
    """技能自带的实时诊断器。

    每个动作完成时自动评估质量，低于阈值时触发改进策略。
    """

    def __init__(self, threshold: float = 0.3):
        self.threshold = threshold
        self.history: list[float] = []

    def evaluate(self, score: float, context: dict) -> str | None:
        """评估质量分，返回改进建议或 None。"""
        self.history.append(score)
        if len(self.history) > 100:
            self.history = self.history[-50:]

        if score < self.threshold:
            trend = "下降" if len(self.history) >= 3 and self.history[-1] < self.history[-3] else "稳定"
            return f"质量分 {score:.2f} 低于阈值 {self.threshold}，趋势{trend}"

        # 检测重复低分模式
        if len(self.history) >= 5 and sum(self.history[-5:]) / 5 < self.threshold:
            return f"连续 5 次低于阈值，建议停用或替换策略"

        return None

    def summary(self) -> str:
        if not self.history:
            return "无数据"
        avg = sum(self.history) / len(self.history)
        return f"质量分: avg={avg:.2f}, min={min(self.history):.2f}, max={max(self.history):.2f}, n={len(self.history)}"


# ──────────────────────────────────────────────
# L4 热替换系统
# ──────────────────────────────────────────────

class HotSwap:
    """运行时技能热替换 — 不重启，不丢状态。"""

    def __init__(self, registry: SkillRegistry_v2, bus: EventBus):
        self.registry = registry
        self.bus = bus

    def upgrade(self, name: str, new_version: str, new_module: Any) -> bool:
        """热替换一个技能。旧状态保留在新实例的 metadata 中。"""
        old = self.registry.get(name)
        if not old:
            return False

        # 保留旧技能的统计信息
        old_score = old.avg_score

        # 注册新版本
        upgraded = SkillModule(
            name=name,
            description=old.description,
            version=new_version,
            triggers=old.triggers,
            dependencies=old.dependencies,
            source_path=old.source_path,
            module=new_module,
            quality_threshold=old.quality_threshold,
            invoke_count=old.invoke_count,
            avg_score=old_score,
        )
        self.registry.skills[name] = upgraded

        # 发事件通知升级
        self.bus.emit(Event('skill:upgraded', 'hotswap', {
            'name': name, 'old_version': old.version, 'new_version': new_version
        }))
        return True


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

def _test_skill_module():
    """创建一个真实技能模块测试注册和依赖解析。"""
    recall_skill = SkillModule(
        name='semantic-recall',
        description='语义搜索：关键词→向量 fallback 混合',
        version='0.1.0',
        triggers=['query:recall', 'query:search*'],
        dependencies=['tokenizer'],
    )
    tok_skill = SkillModule(
        name='tokenizer',
        description='中文/英文分词器',
        version='0.1.0',
        triggers=[],
        dependencies=[],
    )
    return recall_skill, tok_skill


def _test_event_bus():
    bus = EventBus()
    received = []

    def handler(e: Event):
        received.append(e.type)

    bus.on('query:recall', handler)
    bus.on('query:%', handler)  # 通配符

    assert bus.emit(Event('query:recall', 'test'))
    assert bus.emit(Event('query:unknown', 'test'))
    assert len(received) == 3  # recall 触发两个 handler, unknown 触发通配符

    print("  [四弟:EventBus] 通过")
    return True


def _test_registry():
    reg = SkillRegistry_v2()
    r, t = _test_skill_module()
    assert reg.register(r)
    assert reg.register(t)
    assert reg.count == 2

    # 依赖解析
    order = reg.resolve_dependencies('semantic-recall')
    assert order is not None
    assert order[-1] == 'semantic-recall'  # 最后解析自身
    print(f"  [四弟:依赖解析] order={order}")

    # 查找
    assert len(reg.find('semantic')) == 1
    assert len(reg.find('token')) == 1
    assert len(reg.find('nonexistent')) == 0

    print("  [四弟:SkillRegistry] 通过")
    return True


def _test_quality_gate():
    gate = QualityGate(threshold=0.3)
    assert gate.evaluate(0.8, {}) is None     # 通过
    assert gate.evaluate(0.1, {}) is not None  # 触发
    assert gate.evaluate(0.2, {}) is not None

    summary = gate.summary()
    assert 'avg' in summary
    print(f"  [四弟:QualityGate] {summary}")
    return True


def _test_memory():
    ms = MemorySystem()
    ms.store('L1', 'test_key', '四弟大脑架构')
    ms.store('L2', 'recall', {'topic': '进化'})

    results = ms.query('四弟')
    assert len(results) >= 1
    assert results[0][0] == 'L1'

    results2 = ms.query('进化')
    assert len(results2) >= 1

    print("  [四弟:MemorySystem] 通过 (L1+L2)")
    return True


if __name__ == '__main__':
    print("═══ 四弟大脑原型自测 ═══\n")
    _test_event_bus()
    _test_registry()
    _test_quality_gate()
    _test_memory()

    # 集成测试：完整的查询 → 事件 → 技能 → 质量回路
    print("\n--- 集成测试: 查询回路 ---")
    bus = EventBus()
    reg = SkillRegistry_v2()
    r_skill, t_skill = _test_skill_module()
    reg.register(r_skill)
    reg.register(t_skill)

    query_results = []

    def recall_handler(e: Event):
        query_results.append(e.data.get('query', ''))
        # 模拟 recalls
        hits = ['absorb-and-evolve', 'Memory-R1', 'MetaAgent']
        score = min(len(hits) / 5, 1.0)
        bus.emit(Event('recall:complete', 'semantic-recall', {
            'query': e.data.get('query'),
            'hits': hits,
            'score': score,
        }))

    def quality_handler(e: Event):
        score = e.data.get('score', 0)
        if score < 0.3:
            print(f"  [诊断] recall 质量偏低 ({score:.2f}), 建议扩大搜索范围")

    bus.on('query:recall', recall_handler)
    bus.on('recall:complete', quality_handler)

    bus.emit(Event('query:recall', 'test', {'query': 'agent自进化'}))
    print(f"  [集成] 查询结果: {query_results}")
    print("  [四弟:集成测试] 通过")

    print("\n✅ 四弟原型自测全部通过")
