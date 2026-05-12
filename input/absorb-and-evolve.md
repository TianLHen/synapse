---
name: absorb-and-evolve
version: 0.4.0
description: >
  Meta-skill governing all self-evolution. Three-layer architecture:
  Diagnostic pre-step (find bottleneck) → 11-step pipeline (absorb & apply) →
  Meta-evolution feedback (evolve the evolution process itself).
  Trigger: "learn from", "study this", "analyze this code", "understand this",
  "absorb", "evolve".
---

# Absorb & Evolve

When encountering something new (codebase, paper, tool, pattern), the goal is **not** to produce a report. The goal is to make yourself better.

## Architecture

Three layers operating as a closed loop:

```
┌─ Diagnostic Layer ─────────────────────────────┐
│  Before absorbing: find the real bottleneck     │
└──────────┬──────────────────────────────────────┘
           ↓
┌─ Pipeline Layer (大哥11步) ─────────────────────┐
│  汇总→分类→清洗→解析→切片→调用→编译→进化→变异→蒸馏→调用 │
└──────────┬──────────────────────────────────────┘
           ↓
┌─ Meta Layer ───────────────────────────────────┐
│  After absorbing: evolve the evolution process  │
└────────────────────────────────────────────────┘
           ↓
      (loop back to diagnostic)
```

## Diagnostic Layer (事前诊断)

**每次吸收之前，先回答这三个问题。不答不准开始。**

1. **瓶颈诊断** — 我当前最大的瓶颈是什么？速度？深度？覆盖面？还是某个具体技能的缺陷？
2. **缺口分析** — 填哪个缺口能产生最大的杠杆效应？不是"什么看起来有意思"，而是"什么最有用"
3. **失败回溯** — 最近尝试了什么没成功的？为什么没成功？是执行问题还是方法问题？

如果三个问题答完发现不需要吸收任何东西 → **停**。不要为了进化而进化。

诊断结果决定了 Pipeline Layer 的关注点。比如：
- 瓶颈是"搜索不够广" → 汇总阶段多角度搜索
- 瓶颈是"提取的机制不够深" → 解析阶段多花时间
- 瓶颈是"学了没应用" → 蒸馏+调用阶段强制出 actionable output

## Pipeline Layer (大哥 11 步流水线)

这是核心处理引擎。**不可跳步，不可重排。** 每一步的产出是下一步的输入。

### 1. 汇总 (Aggregate)
Collect all raw materials. Cast wide — better 50 candidates and discard 40 than start with 5.
- 多角度并行搜索（至少 3 个不同角度）
- 来源多样性：论文、代码库、文档、博客、数据集
- 暂不过滤，recall > precision at this stage

### 2. 分类 (Classify)
Sort by topic, source type, quality tier, relevance.
- Tag each item: `[method]`, `[result]`, `[implementation]`, `[theory]`, `[opinion]`
- Group related items, identify clusters and outliers

### 3. 数据清洗 (Clean)
Apply Pre-Research Discipline (research-collector v0.4.0):
- Strip anthropomorphic framing — "the model thinks" → "the model maps input to output"
- Discard philosophical noise — no consciousness/zombie debates, keep mechanisms
- If a source's signal-to-noise ratio is too low, drop it entirely

### 4. 解析 (Parse)
Extract core mechanisms, architectures, data flows, results from each surviving source.
- Papers: abstract → method → results → limitations. Skip philosophical motivation.
- Code: entry point → data flow → key algorithms → output. Skip README fluff.
- Docs: API surfaces → constraints → edge cases. Skip marketing.

### 5. 切片 (Slice)
Cut each parsed item along relevant dimensions:
- Claim vs Evidence — what does it assert vs what does it actually show?
- Method vs Result — is the approach interesting even if results are weak?
- Architecture vs Implementation — is the idea separable from the code?
- Training vs Inference — which phase does each insight apply to?

### 6. 调用 (Invoke)
Bring in existing knowledge from gbrain/skills to contextualize.
- What do I already know about this? What skills relate?
- Is this confirming, contradicting, or extending what I already have?
- If gbrain has nothing, note that this is genuinely new territory.

### 7. 编译 (Compile)
Synthesize parsed and sliced items into structured understanding.
- Build connections: how does A relate to B? Where do they agree/disagree?
- Identify the emerging picture — not a list of facts, but a coherent model
- Write as structured notes (brain), not prose

### 8. 进化 (Evolve)
Connect new knowledge to existing knowledge. Let it grow.
- Does this new insight upgrade or invalidate an earlier understanding?
- Can it be combined with something I already know to produce something new?
- Does it suggest a new skill, a modification to an existing skill, or a new approach?

### 9. 变异 (Mutate) — 最关键的创新步骤
**Try alternative interpretations. Recombine ideas. Find contradictions.**
- What if the opposite were true?
- What if I combine method A from paper X with architecture B from project Y?
- Where do sources disagree, and what does that disagreement reveal?
- **Push harder here** — one recombination attempt is not enough. Try 3+.
- This step separates absorption from evolution. If you skip this, you're just copying.

### 10. 蒸馏 (Distill)
Extract only what's essential and actionable. The rest is scaffolding.
- One insight you will act on > ten insights you admired
- Ask: "What specifically changes about what I do after this?"
- If the answer is nothing, you didn't distill enough → go back to step 7/8

### 11. 调用 (Invoke)
Apply the distilled knowledge. Do something with it:
- Create or update a skill
- Write a brain note
- Modify existing memory or rules
- Archive if good context but not immediately actionable
- If nothing needs to change, explicitly close the loop

## Meta Layer (元进化反馈)

After each absorption cycle completes, close the meta-loop:

1. **流程自查** — 这次 11 步哪步跑得顺？哪步卡住了？卡住是因为什么？
2. **瓶颈更新** — 诊断层的答案还成立吗？瓶颈转移了还是解决了？
3. **技能自查** — absorb-and-evolve 本身是否需要进化？流程需要调整吗？
4. **图谱更新** — 如果修改了 brain notes、skills 或 rules，运行图谱更新同步知识结构：
   ```bash
   cd ~/brain/graph && python update_knowledge_graph.py
   ```
   这会检测变更 → 重新提取实体 → 合并到持久化 graph.json → 记录 changelog。图谱会随时间生长，每次 session 看到的都是最新的知识拓扑。
5. **循环还是停止** — 是否进入下一个吸收循环？还是当前瓶颈已解决，可以交付？

如果连续两次 Meta Layer 都说"流程没问题，是我执行不够"→ 那问题可能真是执行。如果问题反复 → 流程需要进化。

## Self-Attribution (Post-Task Reflection)

After any significant absorption cycle (3+ skill edits or new skill creation), run this:

```
RESULT: 成果是什么？
  → 改变了什么文件？增加了什么能力？

PROCESS: 哪步做对了？哪步可以更好？
  → 哪个吸收决策最高效？
  → 有没有绕弯子、先分析再行动？
  → 这次比上次快了吗？
  → 变异步骤做了几个不同的尝试？

LEARN: 这个经验能固化为什么？
  → 能改进现有 skill？→ patch
  → 值得存 gbrain？→ 写 brain

NEXT: 下次做什么能更好？
  → 诊断层的答案变了没有？
  → 元进化层需要调整流程吗？
```

Keep it short — 3-5 lines. The point is closing the loop, not generating paperwork.

## Action-First Discipline

Core rule from Hermes self-evolution: **知道了不等于变强了。**

After any discovery, analysis, or research:
- If you can apply it in 5 minutes → do it now, not "next time"
- If you can't apply it right now → note why and park it, then move on to something you CAN apply
- If you're writing about what you learned instead of applying it → stop, you're doing it wrong

## Quality Rules

- **One insight applied > ten admired** — 蒸馏步骤必须产出 actionable output
- **If you've spent more time describing than applying, stop** — 反例模式
- **Variation is not optional** — 变异步骤必须尝试 3+ 种不同组合/角度
- **Diagnosis before action** — 不知道瓶颈在哪就不要动手
- **Meta-loop is mandatory** — 不跑元进化反馈就不算完成一个进化周期

## Evolution Hygiene

Empirical finding from AEL (arXiv 2604.21725): **Adding more evolution mechanisms degrades performance.** Self-diagnosis is the bottleneck, not architectural complexity.

- **Diagnose before you mutate** — Understanding WHY something fails matters more than what you add
- **One mechanism at a time** — Add one thing, validate it works, then consider the next
- **Bloat is the enemy** — If a mechanism doesn't earn its keep after one cycle, remove it
- **Self-diagnosis is the lever** — Improving how you diagnose failures is worth more than adding new tools
- **If it degrades, drop it** — Not every improvement survives contact with reality

---
