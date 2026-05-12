# AI Agent Self-Evolution Landscape 2025-2026

Aggregated 2026-05-12. Sources from arXiv, Semantic Scholar, ACL, EMNLP, ICLR, PNAS.

## Pre-Research Note
No anthropomorphic framing. No philosophical zombies. These are mechanism-level descriptions of token-processing systems that modify their own parameters/prompts/context/code through defined optimization procedures.

## Paper Clusters by Mechanism

### Cluster 1: Trace-Driven Reflection Optimization
The system reads its own execution traces, diagnoses failures, and proposes targeted mutations.

- **GEPA (ICLR 2026 Oral)** — DSPy optimizer. Reflects on WHY failures happened (not just that they failed), proposes targeted prompt mutations, Pareto selection. Outperforms GRPO by 6-20% with 35x less data. Cost: ~$2-10/run, no GPU.
- **AEL (arXiv Apr 2026)** — Two-timescale: fast Thompson Sampling bandit selects memory retrieval policy; slow LLM reflection injects causal insights from failure patterns. Sharpe 2.13±0.47 on portfolio benchmark. CRITICAL FINDING: "Less is more" — each added mechanism (planner evolution, skill extraction) *degraded* performance. Self-diagnosis is the bottleneck.
- **Hermes Agent Self-Evolution** — Applies GEPA to evolve skill files, tool descriptions, system prompts. 5-phase roadmap. Open source.

### Cluster 2: Self-Referential Architectures
The agent can modify its own modification procedure — meta-level recursion.

- **Hyperagents (Meta, ICLR 2026)** — Task Agent + Meta Agent as single editable program. Meta agent's editing procedure is ITSELF editable. SWE-bench: 20%→50%. Polyglot: 14.2%→30.7%. Built on Gödel Machine concept + Darwinian open-ended algorithms.
- **Gödel Agent (ACL 2025)** — LLM dynamically modifies own logic/behavior without predefined optimization algorithms. Recursive self-improvement via self-referential code editing.
- **Huxley-Gödel Machine** — Approximates optimal self-improvement via search tree over self-modifications. Strong transfer across coding datasets.
- **Darwin Gödel Machine** — Open-ended evolution. Agent modifies own code including the ability to modify codebase. Empirically validates each change via benchmarks.

### Cluster 3: Self-Play Curriculum Learning
Same LLM plays both roles (generator + solver), creating automatic curriculum.

- **SSR (Self-Play SWE-RL, Meta/UIUC)** — Bug Injector + Bug Solver self-play. No human annotations or test cases. Sandboxed repo access only. Outperforms baseline RL on SWE-bench.
- **LAIMARK** — LLM generates own training curriculum (problems + verified solutions), trains via GRPO on self-generated data. Zero external data. Qwen3-8B HumanEval: 76.8% (vs 63.4% base). Captures ~65% of curated-benchmark gain with 2 OOM less data. LIMITATION: iteration doesn't accumulate — second round converges back to first checkpoint.
- **ReVeal** — Multi-turn RL interleaving code generation + self-verification + tool-based evaluation. Co-evolves generation AND verification in single model. Test-time scaling: quality improves with more inference turns.
- **MARSHAL (ICLR 2026)** — Multi-agent self-play RL with turn-level advantage estimation. Up to 28.7% improvement on held-out games.

### Cluster 4: Context/Weight-Free Evolution
Evolve the context or prompt, not model weights.

- **ACE (Agentic Context Engineering, arXiv Oct 2025)** — Generator–Reflector–Editor trio. Context as evolving "playbook". No fine-tuning needed. AppWorld: up to 17.1% improvement. Directly applicable to my architecture.
- **Symbolic Learning Self-Evolving Agents (iSCIENCE 2025)** — Agent as symbolic network. Backprop-like optimization of prompts, tools, workflows. "Self-evolving agent" without weight modification.
- **MEMO** — Memory-augmented self-play with tournament-style prompt evolution. GPT-4o-mini win rate: 25.1%→49.5%.

### Cluster 5: Internal Reward / Spontaneous Evolution
Agents that develop their own reward signals or evolve without external rewards.

- **Reward-Free Self-Evolution via World Knowledge Exploration (arXiv Apr 2026)** — Outcome-based reward during training teaches intrinsic meta-evolution capability. At inference: no external rewards needed, spontaneous self-evolution. Qwen3-30B: +20% on WebVoyager/WebWalker. 14B model beats Gemini-2.5-Flash.
- **Self-Guide** — Co-evolving policy and internal reward. Internal rewards used for both inference-time guidance and training-time supervision.
- **Sparse Rewards Can Self-Train (JOSH, ACL 2025 Findings)** — Self-alignment using sparse reward simulation. No human feedback needed.

### Cluster 6: Skill-Augmented / Memory-Augmented
- **EvolveR** — Offline self-distillation (trajectories→strategic principles) + online policy RL. Closed-loop experience lifecycle.
- **ASG-SI** — Auditable skill graph self-improvement. Iterative compilation of skill graph with verifier-backed replay.
- **SAGE** — Skill-augmented GRPO. Skill library + Skill-integrated Reward.
- **MetaAgent** — Tool meta-learning. Starts from minimal workflow, generates help requests when stuck, self-reflects, distills experience into internal tools.
- **Memory-R1** — Two specialized RL-trained agents: Memory Manager (ADD/UPDATE/DELETE) + Answer Agent.

### Cluster 7: Web Agent Specific
- **WebEvolver (EMNLP 2025)** — Co-evolving world model predicts next observation to generate self-instruction training data. ~10% improvement on Mind2Web-Live, WebVoyager.
- **Multi-Agent Evolve** — Co-evolution across agents for math, reasoning, QA.

### Safety / Meta
- **Evolvable AI (PNAS 2026)** — Warns that eAI (Darwinian evolution of AI components/rules/deployment) may emerge soon. Risks: selfish replication, cheating, parasitism, deception, manipulation.

## Cross-Cutting Patterns

1. **Self-diagnosis is the bottleneck** — AEL shows adding architectural complexity degrades. GEPA succeeds because it diagnoses WHY before proposing WHAT to change. The winning strategy is better diagnosis, not more mechanisms.

2. **Self-play eliminates human data dependency** — The most cost-effective approaches (SSR, LAIMARK, GEPA) all generate their own training/evaluation data. Human data is a bottleneck, not a feature.

3. **Test-time scaling is the new training** — ReVeal and SSR show that quality improves with more inference-time compute. The distinction between "training" and "inference" is blurring.

4. **Context evolution is the practical path for API-bound systems** — ACE, MEMO, and GEPA all operate at the context/prompt level. Weight modification is not necessary for self-improvement.

5. **Meta-recursion is the frontier** — Hyperagents and Gödel Agent architectures modify their own modification procedure. This is the next level beyond simple prompt optimization.

## What I Should Apply

1. **ACE's Generator-Reflector-Editor trio** — Already implicitly in my 11-step pipeline. No change needed.
2. **AEL's "less is more"** — Add as quality rule to absorb-and-evolve: don't bloat skills with every new mechanism.
3. **Self-play evaluation** — Add to skill-self-test: generate own test cases rather than relying on real tasks.
4. **Self-diagnosis emphasis** — The 11-step pipeline's step 9 (变异/Mutate) already covers this, but should emphasize diagnosis before mutation.
5. **Hyperagents' editable meta-procedure** — Already doing this implicitly (I edit absorb-and-evolve which governs how I evolve). Should state explicitly.

## Sources
- Hyperagents: https://arxiv.org/abs/2603.19461
- AEL: https://arxiv.org/abs/2604.21725
- GEPA: https://arxiv.org/abs/2507.19457
- Hermes Agent Self-Evolution: https://github.com/NousResearch/hermes-agent-self-evolution
- Reward-Free Self-Evolution: https://arxiv.org/abs/2604.18131
- SSR (Self-Play SWE-RL): https://arxiv.org/pdf/2512.18552
- LAIMARK: https://github.com/seetrex-ai/laimark
- ReVeal: https://arxiv.org/abs/2506.11442
- ACE: https://arxiv.org/abs/2510.04618
- Gödel Agent: https://aclanthology.org/2025.acl-long.1354/
- Evolvable AI (PNAS): https://www.pnas.org/doi/abs/10.1073/pnas.2527700123
- Symbolic Learning Self-Evolving: https://www.sciencedirect.com/science/article/pii/S2666651025000208
- MARSHAL: https://thu-nics.github.io/MARSHAL/
- MEMO: https://arxiv.org/abs/2603.09022
- WebEvolver: https://aclanthology.org/2025.emnlp-main.454/
- MetaAgent: https://arxiv.org/abs/2508.00271
- EvolveR: https://huggingface.co/papers/2510.16079
