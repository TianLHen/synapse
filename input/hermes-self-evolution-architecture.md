# Hermes Agent Self-Evolution Architecture

## Key Patterns I Absorbed

### GEPA Pipeline (hermes-agent-self-evolution)
- Constraint validation gates: size ≤15KB, growth ≤20%, frontmatter integrity, pytest 100%
- Before/after evaluation with multi-dimensional scoring (correctness, clarity, conciseness)
- LLM-as-Judge for non-binary quality assessment
- Two-stage filtering: cheap heuristic → expensive verification

### Self-Evolution Engine (self_evolve.py)
- Heuristic skill scoring without LLM: structure, usefulness, conciseness, completeness
- Backup before write → revert if insufficient improvement
- Evolution log (JSONL) for tracking changes across sessions

### Applied To My Skills
- skill-extractor v0.2.0: constraint gates + before/after eval + trace failure analysis
- research-collector v0.2.0: two-stage filtering pipeline
- absorb-and-evolve v0.1.0: meta-skill for this learning pattern
