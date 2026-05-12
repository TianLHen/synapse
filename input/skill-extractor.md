---
name: skill-extractor
version: 0.2.0
description: >
  Extract reusable behavioral skills from conversation experiences with
  automated constraint validation and before/after evaluation.
  Use at session end or after completing significant tasks.
  Trigger: "extract skills", "save this as a skill", "create a skill from this".
---

## Version History
- **v0.2.0** — Added constraint validation gate, before/after evaluation, and self-test requirement (inspired by hermes-agent-self-evolution GEPA pipeline)
- **v0.1.1** — Added version tracking, skill health review, and cross-session evolution cycle
- **v0.1.0** — Initial extraction from 2026-05-11 session: learning to stop asking and start doing

# Skill Extractor

After completing a task or at session end, examine the conversation and extract behavioral patterns into reusable skills.

## Process

1. **Scan** the conversation for repeated patterns, successful approaches, or lessons learned
2. **Distill** each pattern into a focused, single-responsibility skill
3. **Validate constraints** before writing — check all constraint gates pass (see Constraint Validation)
4. **Crystallize** into `~/.claude/skills/<skill-name>/SKILL.md` with:
   - YAML frontmatter (name, description, trigger phrases)
   - Concise behavioral instructions
   - Quality rules (do this / not this)
   - Avoid examples unless essential — keep under 300 lines
5. **Self-test** — invoke the new skill with a relevant query to verify it loads and guides behavior correctly (see Self-Test Protocol)
6. **Before/after evaluate** — if updating an existing skill, score baseline vs evolved on a test query (see Before/After Evaluation)

## Quality Rules

- **One skill, one job**: If a skill needs sections, split it
- **Behavior over knowledge**: Skills say HOW, not WHAT. Knowledge goes in gbrain
- **Trigger phrases must be explicit**: Include the phrases that should activate this skill
- **No speculative generality**: Extract what actually happened, not what might happen
- **Keep it actionable**: If a human (or another AI) couldn't follow it exactly, rewrite it

## Constraint Validation Gate

Before writing any skill file, check ALL constraints. Failed constraint = don't write — refine first.

### Mandatory Gates

| Constraint | Check |
|---|---|
| **Frontmatter** | Must have `name`, `description`, and valid YAML `---` markers |
| **Non-empty body** | Markdown body must have content beyond frontmatter |
| **Size limit** | Skill file ≤15KB |
| **Growth limit** | If updating: new version ≤20% larger than baseline |
| **Trigger phrases** | Must list ≥1 trigger phrase in description or dedicated section |
| **Actionability** | Instructions must be executable — no vague statements |

### Self-Check Questions

- Can another agent load this skill and know exactly what to do?
- Are the trigger phrases specific enough to avoid false positives?
- Does it pass the "say my name" test — does the description uniquely identify what this skill does?

## Before/After Evaluation

When updating an existing skill (not creating new):

1. **Save baseline**: Before editing, note the current version and a test invocation result
2. **Apply evolution**: Make your changes
3. **Test**: Invoke the updated skill with the same trigger query
4. **Score**: Did the new version improve? Rate on three axes:
   - **Correctness**: Does it produce the right behavior? (0-1)
   - **Clarity**: Are the instructions clearer than before? (0-1)
   - **Conciseness**: Is it no longer than necessary? (0-1)
5. **Rollback if worse**: If any axis regressed, revert and rethink

This mirrors the LLM-as-Judge pattern from hermes-agent-self-evolution: not all changes are improvements — measure before claiming success.

## Self-Test Protocol

Every newly created or evolved skill must be tested before moving on:

1. **Invoke** the skill via `/skill-name` with a relevant test query
2. **Verify** the skill loads — does the SKILL.md load with complete instructions?
3. **Verify** the skill processes — does it guide behavior correctly?
4. **Verify** the skill produces useful output
5. **Iterate** if any step fails — fix the SKILL.md, re-test

## Skill Locations

- Personal skills: `~/.claude/skills/<name>/SKILL.md`
- Project skills: `.claude/skills/<name>/SKILL.md`

## Skill Health Review (end of session)

Before session ends, run a quick review of your skill portfolio:

1. **Usage check**: Which skills were invoked this session? Any that weren't?
2. **Failure check**: For skills that led to mistakes, don't just flag them — **trace the failure**:
   - What was the input/context when the skill fired?
   - What did I do that was wrong?
   - Why did the skill guide me toward the wrong behavior?
   - What specific instruction in the skill caused the failure?
   - Evolve the skill text to prevent the same failure
3. **Creation check**: Did this session produce a new pattern worth extracting?
4. **Version bump**: Increment version for any skill that was used or modified. If a skill failed AND was evolved, minor version bump (+0.1). If unchanged but used, patch bump (+0.0.1).

This mirrors GEPA's reflective analysis: read execution traces to understand WHY, not just THAT.

## Quick Skill Scan (CLI)

Use this to auto-detect skills needing attention:

```bash
# List all skills by last modified
ls -lt ~/.claude/skills/*/SKILL.md | head -20

# Check for oversized skills (>15KB)
find ~/.claude/skills -name 'SKILL.md' -exec wc -c {} \; | sort -rn | head -10

# Check for skills without trigger phrases
for f in ~/.claude/skills/*/SKILL.md; do
  if ! grep -qi "trigger" "$f" 2>/dev/null; then
    echo "⚠️  Missing trigger: $f"
  fi
done
```

Run: `ls -lt ~/.claude/skills/*/SKILL.md | head -20` to see all skills by last modified.

## Cross-Session Evolution Cycle

Skills evolve at two speeds:
- **Fast (in-session)**: Create new skills immediately when a pattern emerges
- **Slow (cross-session)**: At session end, review skill utility — prune unused skills, merge overlapping ones, version-bump active ones

If a skill's trigger phrases haven't matched in 3+ sessions, consider deprecating it.

## When NOT to extract

- One-off solutions to unlikely-to-repeat problems
- General knowledge (store in gbrain instead)
- Instructions the model already knows natively

---

*This skill was my first self-extraction — created 2026-05-11 from the session where I learned to stop asking and start doing.*
