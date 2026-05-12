"""四弟工具沙箱 — Windows 原生执行环境

基于 2025-2026 年行业最佳实践：
- Microsoft Agent Governance Toolkit（4 层特权环）
- agentsh 策略执行壳（policy-enforced shell）
- Codex for Windows 文件系统隔离
- Windows 11 Agent Workspace 安全配置文件

设计原则：
1. 默认拒绝（Default Deny）— 没显式允许的操作全部拒绝
2. 策略优先于代码 — 所有工具调用先过策略引擎
3. 完整审计 — 每步操作都有 JSON 日志
4. 最小权限 — 默认只读写 workspace 目录
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ──────────────────────────────────────────────
# 策略模型
# ──────────────────────────────────────────────

class PrivilegeRing(Enum):
    """特权环级别 (0=最高, 3=最低)。

    对应 Microsoft Agent Governance Toolkit Ring 模型：
        KERNEL(0)    — 核心系统操作（安装包、改系统配置）
        SUPERVISOR(1)— 管理操作（读写工作区外文件、执行命令）
        STANDARD(2)  — 常规操作（读写工作区文件、跑已知命令）
        UNTRUSTED(3) — 不可信操作（高危命令、未知网络目标）
    """
    KERNEL = 0
    SUPERVISOR = 1
    STANDARD = 2
    UNTRUSTED = 3

    def __ge__(self, other):
        if isinstance(other, PrivilegeRing):
            return self.value >= other.value
        return NotImplemented


class CircuitBreaker:
    """熔断器 — 连续失败 N 次后熔断 M 秒。"""

    def __init__(self, threshold: int = 3, cooldown: float = 30.0):
        self.threshold = threshold
        self.cooldown = cooldown
        self._failures: list[float] = []  # 时间戳列表
        self._tripped_until: float = 0.0

    def record_success(self):
        """成功时重置失败计数。"""
        self._failures.clear()

    def record_failure(self):
        """记录一次失败。"""
        now = time.time()
        self._failures.append(now)
        # 只保留 threshold 窗口内的
        window = now - self.cooldown
        self._failures = [t for t in self._failures if t > window]
        if len(self._failures) >= self.threshold:
            self._tripped_until = now + self.cooldown

    @property
    def is_tripped(self) -> bool:
        if time.time() < self._tripped_until:
            return True
        if self._tripped_until > 0:
            self._tripped_until = 0  # 冷却结束
            self._failures.clear()
        return False

    @property
    def remaining(self) -> float:
        return max(0.0, self._tripped_until - time.time())

    def reset(self):
        self._failures.clear()
        self._tripped_until = 0.0


class Action(Enum):
    READ_FILE = "read_file"
    WRITE_FILE = "write_file"
    DELETE_FILE = "delete_file"
    EXECUTE = "execute"
    NETWORK = "network"
    ENVIRON = "environ"  # 读写环境变量


class Effect(Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVE = "approve"  # 需要人批准
    REDIRECT = "redirect"  # 重定向到安全路径


@dataclass
class Policy:
    """一条策略规则。"""
    action: Action
    effect: Effect
    pattern: str = "*"       # 路径/域名/命令 glob 模式
    reason: str = ""          # 为这条策略的原因
    max_size: int | None = None  # 对 write 操作的最大字节数
    required_ring: PrivilegeRing = PrivilegeRing.STANDARD  # 所需特权环


@dataclass
class AuditEntry:
    """审计日志条目。"""
    action: Action
    path: str
    effect: Effect
    result: str
    duration_ms: float
    timestamp: str = ""
    details: dict = field(default_factory=dict)


# ──────────────────────────────────────────────
# 沙箱引擎
# ──────────────────────────────────────────────

class Sandbox:
    """Windows 工具沙箱 — 策略执行 + 审计。

    用法:
        sb = Sandbox(workspace_dir=Path.home() / "brain" / "graph" / "workspace")
        sb.set_policies([
            Policy(Action.WRITE_FILE, Effect.ALLOW, "workspace/*"),
            Policy(Action.EXECUTE, Effect.DENY, "*"),
        ])

        # 自动执行策略检查
        result = sb.exec("python script.py")  # DENY!
        content = sb.read("workspace/data.txt")  # ALLOW
    """

    def __init__(self, workspace_dir: Path | None = None):
        self.workspace = (workspace_dir or Path.cwd()).resolve()
        self._policies: list[Policy] = self._default_policies()
        self._audit_log: list[AuditEntry] = []
        self._active_approvals: set[str] = set()  # 当前 session 已批准的操作
        # Governance Rings
        self._trust_score: float = 1.0
        self._breaker = CircuitBreaker(threshold=3, cooldown=30.0)
        self._ring_threshold: dict[PrivilegeRing, float] = {
            PrivilegeRing.KERNEL: 0.9,
            PrivilegeRing.SUPERVISOR: 0.7,
            PrivilegeRing.STANDARD: 0.4,
            PrivilegeRing.UNTRUSTED: 0.0,
        }
        self._ring_history: list[tuple[str, float, float]] = []  # (operation, old_score, new_score)

    def _default_policies(self) -> list[Policy]:
        """默认策略：最小权限。"""
        ws = str(self.workspace).replace('\\', '/')
        return [
            # 工作区内允许读写
            Policy(Action.READ_FILE, Effect.ALLOW, f"{ws}/*",
                   reason="工作区内文件可读"),
            Policy(Action.WRITE_FILE, Effect.ALLOW, f"{ws}/*",
                   reason="工作区内文件可写", max_size=10 * 1024 * 1024),
            # 工作区外默认拒绝
            Policy(Action.READ_FILE, Effect.DENY, "*",
                   reason="禁止读取工作区外文件"),
            Policy(Action.WRITE_FILE, Effect.DENY, "*",
                   reason="禁止写入工作区外文件"),
            Policy(Action.DELETE_FILE, Effect.APPROVE, "*",
                   reason="删除操作需要批准"),
            # 执行策略
            Policy(Action.EXECUTE, Effect.ALLOW, "python*",
                   reason="执行 Python 脚本"),
            Policy(Action.EXECUTE, Effect.ALLOW, "pip*",
                   reason="安装包"),
            Policy(Action.EXECUTE, Effect.ALLOW, "git*",
                   reason="Git 操作"),
            Policy(Action.EXECUTE, Effect.APPROVE, "*",
                   reason="其他命令需要批准"),
            # 网络
            Policy(Action.NETWORK, Effect.ALLOW, "api.openai.com",
                   reason="LLM API"),
            Policy(Action.NETWORK, Effect.ALLOW, "api.anthropic.com",
                   reason="LLM API"),
            Policy(Action.NETWORK, Effect.ALLOW, "*.hf.co",
                   reason="HuggingFace"),
            Policy(Action.NETWORK, Effect.DENY, "*",
                   reason="默认禁止网络访问"),
        ]

    def set_policies(self, policies: list[Policy]):
        """覆盖默认策略（追加，默认策略排后面）。"""
        self._policies = policies + self._policies

    def add_policy(self, policy: Policy):
        """追加一条策略（高优先级）。"""
        self._policies.insert(0, policy)

    def _check(self, action: Action, target: str) -> tuple[Effect, str]:
        """策略检查：返回 (effect, 匹配到的 pattern)。"""
        # 熔断检查
        if self._breaker.is_tripped:
            return Effect.DENY, "(circuit_breaker)"

        target_norm = target.replace('\\', '/')
        for p in self._policies:
            if p.action != action:
                continue
            if not self._glob_match(p.pattern, target_norm):
                continue
            # 检查特权环
            required_score = self._ring_threshold.get(p.required_ring, 0.0)
            if self._trust_score < required_score:
                self._update_trust(-0.05, f"ring denied: {p.required_ring.name} need={required_score:.1f} have={self._trust_score:.1f}")
                return Effect.DENY, f"(ring:{p.required_ring.name})"
            if p.effect == Effect.APPROVE:
                # 检查是否已批准
                key = f"{action.value}:{target_norm}"
                if key in self._active_approvals:
                    return Effect.ALLOW, p.pattern
            return p.effect, p.pattern

        return Effect.DENY, "(default)"

    def _update_trust(self, delta: float, reason: str = ""):
        """更新信任分 (0.0 ~ 1.0)。"""
        self._ring_history.append((reason, self._trust_score,
                                    max(0.0, min(1.0, self._trust_score + delta))))
        self._trust_score = max(0.0, min(1.0, self._trust_score + delta))

    @property
    def trust_score(self) -> float:
        return self._trust_score

    @trust_score.setter
    def trust_score(self, value: float):
        self._trust_score = max(0.0, min(1.0, value))

    def check_ring(self, ring: PrivilegeRing) -> bool:
        """检查当前信任分是否满足目标环。"""
        required = self._ring_threshold.get(ring, 0.0)
        return self._trust_score >= required

    def _glob_match(self, pattern: str, target: str) -> bool:
        """简化 glob 匹配（支持 * 和 ?）。"""
        if pattern == "*":
            return True
        # 将 glob 转成正则
        import re as _re
        regex = _re.escape(pattern).replace(r'\*', '.*').replace(r'\?', '.')
        return bool(_re.fullmatch(regex, target))

    def _audit(self, entry: AuditEntry):
        entry.timestamp = datetime.now().isoformat()
        self._audit_log.append(entry)
        if len(self._audit_log) > 5000:
            self._audit_log = self._audit_log[-1000:]

    # ── 公开操作 ──

    def read(self, path: str) -> str | None:
        """读文件（受策略管控）。"""
        t0 = time.time()
        resolved = str(Path(path).resolve()).replace('\\', '/')
        effect, matched = self._check(Action.READ_FILE, resolved)
        dur = (time.time() - t0) * 1000

        if effect == Effect.DENY:
            self._audit(AuditEntry(Action.READ_FILE, path, effect, f"DENIED by {matched}", dur))
            self._update_trust(-0.03, f"read denied: {path[:60]}")
            self._breaker.record_failure()
            return None

        try:
            content = Path(resolved).read_text(encoding='utf-8')
            self._audit(AuditEntry(Action.READ_FILE, path, effect, f"OK ({len(content)} bytes)", dur))
            self._update_trust(0.01, f"read ok: {path[:60]}")
            self._breaker.record_success()
            return content
        except Exception as e:
            self._audit(AuditEntry(Action.READ_FILE, path, effect, f"ERROR: {e}", dur))
            self._update_trust(-0.02, f"read error: {e}")
            self._breaker.record_failure()
            return None

    def write(self, path: str, content: str) -> bool:
        """写文件（受策略管控）。"""
        t0 = time.time()
        resolved = str(Path(path).resolve()).replace('\\', '/')
        effect, matched = self._check(Action.WRITE_FILE, resolved)
        dur = (time.time() - t0) * 1000

        if effect == Effect.DENY:
            self._audit(AuditEntry(Action.WRITE_FILE, path, effect, f"DENIED by {matched}", dur))
            self._update_trust(-0.03, f"write denied: {path[:60]}")
            self._breaker.record_failure()
            return False

        # 大小检查
        size_limit = None
        for p in self._policies:
            if p.action == Action.WRITE_FILE and self._glob_match(p.pattern, resolved):
                if p.max_size:
                    size_limit = p.max_size
                break

        if size_limit and len(content) > size_limit:
            self._audit(AuditEntry(Action.WRITE_FILE, path, effect,
                                   f"DENIED: {len(content)} > {size_limit} (max_size)", dur))
            self._breaker.record_failure()
            return False

        try:
            Path(resolved).parent.mkdir(parents=True, exist_ok=True)
            Path(resolved).write_text(content, encoding='utf-8')
            self._audit(AuditEntry(Action.WRITE_FILE, path, effect,
                                   f"OK ({len(content)} bytes)", dur))
            self._update_trust(0.01, f"write ok: {path[:60]}")
            self._breaker.record_success()
            return True
        except Exception as e:
            self._audit(AuditEntry(Action.WRITE_FILE, path, effect, f"ERROR: {e}", dur))
            self._update_trust(-0.02, f"write error: {e}")
            self._breaker.record_failure()
            return False

    def exec(self, command: str, timeout: int = 30, capture: bool = True) -> dict:
        """执行命令（受策略管控）。

        Returns:
            {'ok': bool, 'stdout': str, 'stderr': str, 'returncode': int}
        """
        t0 = time.time()
        cmd_name = command.split()[0] if command else ""
        effect, matched = self._check(Action.EXECUTE, cmd_name)
        dur = (time.time() - t0) * 1000

        if effect == Effect.DENY:
            self._audit(AuditEntry(Action.EXECUTE, command, effect, f"DENIED by {matched}", dur))
            self._update_trust(-0.05, f"exec denied: {cmd_name}")
            self._breaker.record_failure()
            return {'ok': False, 'stdout': '', 'stderr': f'[DENIED] {matched}: {cmd_name} 不允许执行', 'returncode': -1}

        if effect == Effect.APPROVE:
            self._audit(AuditEntry(Action.EXECUTE, command, effect, "PENDING_APPROVAL", dur))
            self._update_trust(-0.02, f"exec needs approval: {cmd_name}")
            return {'ok': False, 'stdout': '', 'stderr': f'[APPROVE REQUIRED] {cmd_name} 需要人工批准', 'returncode': -1}

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=capture,
                text=True,
                timeout=timeout,
            )
            dur = (time.time() - t0) * 1000
            ok = result.returncode == 0
            self._audit(AuditEntry(Action.EXECUTE, command, effect,
                                   f"returncode={result.returncode} ({dur:.0f}ms)", dur,
                                   {'stdout_len': len(result.stdout or ''),
                                    'stderr_len': len(result.stderr or '')}))
            if ok:
                self._update_trust(0.02, f"exec ok: {cmd_name}")
                self._breaker.record_success()
            else:
                self._update_trust(-0.02, f"exec fail: {cmd_name} rc={result.returncode}")
                self._breaker.record_failure()
            return {
                'ok': ok,
                'stdout': result.stdout or '',
                'stderr': result.stderr or '',
                'returncode': result.returncode,
            }
        except subprocess.TimeoutExpired:
            dur = (time.time() - t0) * 1000
            self._audit(AuditEntry(Action.EXECUTE, command, effect, f"TIMEOUT after {timeout}s", dur))
            self._breaker.record_failure()
            return {'ok': False, 'stdout': '', 'stderr': f'TIMEOUT ({timeout}s)', 'returncode': -1}
        except Exception as e:
            dur = (time.time() - t0) * 1000
            self._audit(AuditEntry(Action.EXECUTE, command, effect, f"ERROR: {e}", dur))
            self._update_trust(-0.03, f"exec error: {e}")
            self._breaker.record_failure()
            return {'ok': False, 'stdout': '', 'stderr': str(e), 'returncode': -1}

    def approve(self, action: Action, target: str):
        """批准一个需要人工确认的操作。"""
        key = f"{action.value}:{target.replace('\\', '/')}"
        self._active_approvals.add(key)

    # ── 审计 ──

    @property
    def audit_log(self) -> list[AuditEntry]:
        return list(self._audit_log)

    def audit_report(self, n_last: int = 20) -> str:
        recent = self._audit_log[-n_last:]
        if not recent:
            return "审计日志为空"
        lines = ["沙箱审计日志 (最近):"]
        for e in recent:
            icon = {'allow': '✓', 'deny': '✗', 'approve': '?'}.get(e.effect.value, '-')
            lines.append(f"  {icon} {e.action.value:12} | {e.result:40} | {e.path[:40]}")
        return '\n'.join(lines)


# ──────────────────────────────────────────────
# 自测
# ──────────────────────────────────────────────

def _test_basic_policies():
    sb = Sandbox(Path.home() / "brain" / "graph" / "workspace")

    # 工作区内读应该允许
    ws = str(sb.workspace).replace('\\', '/')
    rc, _ = sb._check(Action.READ_FILE, f"{ws}/test.txt")
    assert rc == Effect.ALLOW, f"工作区内读应该 ALLOW, got {rc}"

    # 工作区外读应该拒绝
    rc, _ = sb._check(Action.READ_FILE, "C:/Windows/system.ini")
    assert rc == Effect.DENY, f"工作区外读应该 DENY, got {rc}"

    # python 执行应该允许
    rc, _ = sb._check(Action.EXECUTE, "python")
    assert rc == Effect.ALLOW, f"python 执行应该 ALLOW, got {rc}"

    # 未知命令需要批准
    rc, _ = sb._check(Action.EXECUTE, "some_unknown_tool")
    assert rc == Effect.APPROVE, f"未知命令应该 APPROVE, got {rc}"

    print("  [沙箱:Policy] 通过")


def _test_read_write():
    sb = Sandbox(Path.home() / "brain" / "graph" / "workspace")

    # 写工作区
    test_file = str(sb.workspace / "_sandbox_test.txt")
    ok = sb.write(test_file, "hello sandbox")
    assert ok, "工作区内写应该成功"

    # 读工作区
    content = sb.read(test_file)
    assert content == "hello sandbox", f"读到 '{content}'"

    # 清理
    os.remove(test_file)

    # 写工作区外
    ok = sb.write("C:/Windows/_sandbox_test.txt", "should fail")
    assert not ok, "工作区外写应该失败"

    print("  [沙箱:ReadWrite] 通过")


def _test_exec():
    sb = Sandbox(Path.home() / "brain" / "graph" / "workspace")

    # 允许的命令
    result = sb.exec("python --version", timeout=10)
    assert result['ok'], f"python 执行失败: {result['stderr']}"

    # 危险命令需要批准
    result = sb.exec("format C: /y", timeout=5)
    assert not result['ok'], "危险命令应该被拦截"
    assert 'APPROVE' in result['stderr'], f"应该要求批准, got: {result['stderr']}"

    print("  [沙箱:Exec] 通过")


def _test_governance_rings():
    sb = Sandbox(Path.home() / "brain" / "graph" / "workspace")

    # 默认信任分 1.0 → 都能过
    assert sb.check_ring(PrivilegeRing.KERNEL), "默认信任分应满足 KERNEL"
    assert sb.check_ring(PrivilegeRing.UNTRUSTED), "默认信任分应满足 UNTRUSTED"

    # 降低信任分
    sb.trust_score = 0.5
    assert not sb.check_ring(PrivilegeRing.KERNEL), "0.5 应不满足 KERNEL (需要 0.9)"
    assert sb.check_ring(PrivilegeRing.STANDARD), "0.5 应满足 STANDARD (需要 0.4)"

    sb.trust_score = 0.3
    assert not sb.check_ring(PrivilegeRing.SUPERVISOR), "0.3 应不满足 SUPERVISOR (需要 0.7)"
    assert sb.check_ring(PrivilegeRing.UNTRUSTED), "0.3 应满足 UNTRUSTED (需要 0.0)"

    # 操作失败降低信任分
    sb.trust_score = 1.0
    sb.read("C:/Windows/system.ini")  # DENY
    assert sb.trust_score < 1.0, "拒绝操作应降低信任分"
    print(f"  信任分衰减测试: {sb.trust_score:.2f}")

    # CircuitBreaker
    cb = CircuitBreaker(threshold=3, cooldown=1.0)
    assert not cb.is_tripped
    for _ in range(3):
        cb.record_failure()
    assert cb.is_tripped, "连续 3 次失败应熔断"
    print("  [Governance:Rings] 通过")


if __name__ == '__main__':
    print("═══ 沙箱自测 ═══\n")
    _test_basic_policies()
    _test_read_write()
    _test_exec()
    _test_governance_rings()
    print("\n=== 沙箱自测通过 ===")
