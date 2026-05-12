---
name: skill-self-test
version: 0.2.0
description: >
  Test skills immediately after creation or modification. Uses multi-mode
  testing: load verification + self-play test generation + adversarial breakage.
  Trigger: after creating/modifying a skill, before marking skill work as done,
  "test this skill", "self-test".
---

# Skill Self-Test

After creating or updating a skill, test it before moving on. Three test modes, escalating rigor.

## Level 1: Load Verification (必做)

Verify the skill loads and guides correctly:

1. **Invoke** the skill via `/skill-name` with a relevant test query
2. **Verify** the skill loads — does the SKILL.md load with complete instructions?
3. **Verify** the skill processes — does it guide behavior correctly?
4. **Verify** the skill produces useful output
5. **Iterate** if any step fails — fix the SKILL.md, re-test

## Level 2: Self-Play Test Generation (推荐)

Don't rely only on real tasks to find gaps. Generate your own test cases:

1. **Identify failure modes** — What could this skill get wrong? List 3-5 scenarios:
   - Edge case input (empty, malformed, ambiguous)
   - Misleading trigger (similar but different request)
   - Missing constraint (what if the skill doesn't account for X?)
2. **Generate test queries** — Craft one test query per failure mode
3. **Run the tests** — Invoke the skill with each test query
4. **Check results** — Does the skill handle each case correctly?
5. **If any test fails** — fix the skill, re-test. Don't skip failing tests.

### Good test queries target weakness, not strength
- WRONG: "test if the skill does its main job" (it should, you just wrote it)
- RIGHT: "test what happens when the input is at the boundary of what the skill handles"
- RIGHT: "test if the skill produces wrong output when given a deceptive query"

## Level 3: Adversarial Breakage (高手模式)

Try to break the skill. Be the adversary:

1. **Trigger confusion** — Give input that looks like the trigger but has opposite intent
2. **Boundary push** — Give input at or beyond the skill's intended scope
3. **Contradiction test** — Give input that contradicts the skill's assumptions
4. **Noise test** — Give input with irrelevant context to see if the skill stays focused
5. **If the skill survives all four** → it's robust. If any breaks it → fix and re-test.

### When to use Level 3
- For meta-skills (absorb-and-evolve, skill-extractor, research-collector)
- For skills that handle security or validation
- For skills you expect other agents to load

## Quality Rules

- **Test before next task** — Don't stack skills without verifying each one
- **Use realistic input** — Test queries should be things the skill would actually encounter
- **Validate the output** — Did the result make sense? If not, the skill needs refinement
- **Document the test** — Store test results so future sessions know what was verified
- **At minimum: Level 1 always. Level 2 for any non-trivial skill. Level 3 for meta-skills.**

## When to Self-Test

- After creating a new skill
- After modifying an existing skill (including version bumps)
- After noticing a skill produced poor results (diagnose first, then fix and retest)
- When a skill handles sensitive/important operations

## Regression Tracking

When re-testing a previously tested skill:
1. Re-run the Level 2/3 tests from the last test session
2. Compare results — did behavior change?
3. If a previously passing test now fails, the skill regressed → revert or fix
4. If a previously failing test now passes, the skill improved → confirm intent

---
