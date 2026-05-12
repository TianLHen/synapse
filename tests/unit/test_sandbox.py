"""测试沙箱 — 策略引擎 + Governance Rings + CircuitBreaker。"""

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest


class TestPolicy:
    def test_default_allow_workspace(self):
        from sandbox import Sandbox, Action, Effect
        sb = Sandbox()
        ws = str(sb.workspace).replace('\\', '/')
        effect, _ = sb._check(Action.READ_FILE, f"{ws}/test.txt")
        assert effect == Effect.ALLOW

    def test_default_deny_outside(self):
        from sandbox import Sandbox, Action, Effect
        sb = Sandbox()
        effect, _ = sb._check(Action.READ_FILE, "C:/Windows/system.ini")
        # DENY or APPROVE — must not be ALLOW
        assert effect != Effect.ALLOW

    def test_exec_python_allowed(self):
        from sandbox import Sandbox, Action, Effect
        sb = Sandbox()
        effect, _ = sb._check(Action.EXECUTE, "python")
        assert effect == Effect.ALLOW

    def test_exec_unknown_requires_approval(self):
        from sandbox import Sandbox, Action, Effect
        sb = Sandbox()
        effect, _ = sb._check(Action.EXECUTE, "some_unknown_tool")
        assert effect == Effect.APPROVE

    def test_add_policy_precedence(self):
        from sandbox import Sandbox, Action, Effect, Policy
        sb = Sandbox()
        sb.add_policy(Policy(Action.EXECUTE, Effect.DENY, "python*"))
        effect, _ = sb._check(Action.EXECUTE, "python")
        assert effect == Effect.DENY


class TestGovernanceRings:
    def test_default_trust_score(self):
        from sandbox import Sandbox
        sb = Sandbox()
        assert sb.trust_score == 1.0

    def test_check_ring_high_trust(self):
        from sandbox import Sandbox, PrivilegeRing
        sb = Sandbox()
        assert sb.check_ring(PrivilegeRing.KERNEL) is True
        assert sb.check_ring(PrivilegeRing.UNTRUSTED) is True

    def test_low_trust_denies_kernel(self):
        from sandbox import Sandbox, PrivilegeRing
        sb = Sandbox()
        sb.trust_score = 0.5
        assert sb.check_ring(PrivilegeRing.KERNEL) is False
        assert sb.check_ring(PrivilegeRing.STANDARD) is True

    def test_denied_op_lowers_trust(self):
        from sandbox import Sandbox
        sb = Sandbox()
        sb.trust_score = 1.0
        sb.read("C:/Windows/system.ini")  # DENY
        assert sb.trust_score < 1.0

    def test_set_trust_clamped(self):
        from sandbox import Sandbox
        sb = Sandbox()
        sb.trust_score = -0.5
        assert sb.trust_score == 0.0
        sb.trust_score = 1.5
        assert sb.trust_score == 1.0


class TestCircuitBreaker:
    def test_not_tripped_by_default(self):
        from sandbox import CircuitBreaker
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        assert cb.is_tripped is False

    def test_trips_after_threshold(self):
        from sandbox import CircuitBreaker
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        for _ in range(3):
            cb.record_failure()
        assert cb.is_tripped is True

    def test_reset_clears(self):
        from sandbox import CircuitBreaker
        cb = CircuitBreaker(threshold=2, cooldown=60.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.is_tripped is True
        cb.reset()
        assert cb.is_tripped is False

    def test_success_resets(self):
        from sandbox import CircuitBreaker
        cb = CircuitBreaker(threshold=3, cooldown=60.0)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()  # resets the failure count
        assert cb.is_tripped is False

    def test_remaining_time(self):
        from sandbox import CircuitBreaker
        cb = CircuitBreaker(threshold=2, cooldown=3600.0)
        cb.record_failure()
        cb.record_failure()
        assert cb.remaining > 0
        cb.reset()
        assert cb.remaining == 0
