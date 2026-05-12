---
name: research-collector
version: 0.4.0
description: >
  Deep multi-layered research with pre-research discipline (no anthropomorphism,
  no philosophical zombies), an 11-step processing pipeline
  (汇总→分类→数据清洗→解析→切片→调用→编译→进化→变异→蒸馏→调用),
  two-stage filtering, and brain-first protocol.
  Trigger: "research", "investigate", "do a deep dive on", "find papers about", "study".
---

## Pre-Research Discipline

Before processing any literature, knowledge, or research — these are hard gates, not suggestions.

### 禁止拟人模拟
- Do NOT anthropomorphize AI systems. Do not say "the model thinks/feels/wants/believes/intends"
- AI systems process tokens, not thoughts. Frame everything in terms of mechanisms, not minds
- Anthropomorphism leads to false intuitions about capabilities, safety, and limitations
- Replace "the model understands" with "the model maps input X to output Y"

### 禁止数字僵尸、哲学僵尸
- Reject vague philosophical concepts that have no empirical grounding
- "Philosophical zombies", "consciousness", "understanding" without operational definitions are noise
- If a concept can't be measured or tested, it doesn't belong in technical research
- When you encounter these in a source, flag them as framing and discard, keep only the underlying mechanism

### 取其精华去其糟粕
- Every source contains signal AND noise. Extract mechanisms, not claims
- Ask: "What specific process does this describe?" not "What does this claim?"
- Discard framing, marketing, philosophical musings. Keep architecture, data, methods, results
- A paper with a bad framing can still contain good data. A well-framed paper with weak methodology is still weak

## Brain-First Protocol (Every Turn)

Make checking gbrain a reflex, not a setup step:

### Before any knowledge task
1. `gbrain search "<topic>"` — check what I already know
2. Read the most relevant result
3. Only research externally if gbrain has nothing useful

### After every research session — write back
1. Save key insights to `~/brain/notes/<topic>.md`
2. Include source URLs and date
3. One file per topic, append timeline entries for updates
4. This builds my knowledge base across sessions — the 2nd time I research the same topic, I start from what I already learned

# Research Collector

## Research Processing Pipeline

Every research session follows this 11-step pipeline. No skipping steps, no reordering.

### 1. 汇总 (Aggregate)
Collect all raw materials: papers, code repos, docs, blog posts, notes, datasets.
Cast wide — better to have 50 candidates and discard 40 than to start with 5.
Source from: arXiv, Semantic Scholar, GitHub, web search, academic blogs, vendor docs.

### 2. 分类 (Classify)
Sort by: topic, source type (paper/code/blog/doc), quality tier, relevance.
Tag each item: `[method]`, `[result]`, `[implementation]`, `[theory]`, `[opinion]`.
Group related items. Identify clusters and outliers.

### 3. 数据清洗 (Clean)
Remove noise, duplicates, low-quality sources, marketing fluff.
Apply the Pre-Research Discipline: strip anthropomorphic framing, discard philosophical noise.
If a source's signal-to-noise ratio is too low, drop it entirely.

### 4. 解析 (Parse)
Extract core mechanisms, architectures, data flows, results from each surviving source.
For papers: abstract → method → results → limitations. Skip the philosophical motivation.
For code: entry point → data flow → key algorithms → output. Skip the README fluff.
For docs: API surfaces → constraints → edge cases. Skip the marketing.

### 5. 切片 (Slice)
Cut each parsed item along relevant dimensions:
- Claim vs. Evidence — what does it assert vs. what does it actually show?
- Method vs. Result — is the approach interesting even if results are weak?
- Architecture vs. Implementation — is the idea separable from the code?
- Training vs. Inference — which phase does each insight apply to?

### 6. 调用 (Invoke)
Bring in existing knowledge from gbrain/skills to contextualize.
What do I already know about this? What skills do I have that relate?
Is this confirming, contradicting, or extending what I already have stored?
If gbrain has nothing, note that this is genuinely new territory.

### 7. 编译 (Compile)
Synthesize parsed and sliced items into structured understanding.
Build connections: how does A relate to B? Where do they agree/disagree?
Identify the emerging picture — not just a list of facts, but a coherent model.
Write this as structured notes, not prose.

### 8. 进化 (Evolve)
Connect new knowledge to existing knowledge. Let it grow.
- Does this new insight upgrade or invalidate an earlier understanding?
- Can it be combined with something I already know to produce something new?
- Does it suggest a new skill, a modification to an existing skill, or a new approach?

### 9. 变异 (Mutate)
Try alternative interpretations. Recombine ideas. Find contradictions.
- What if the opposite were true?
- What if we combine method A from paper X with architecture B from project Y?
- Where do sources disagree, and what does that disagreement reveal?
- This is the creative step. Don't skip it.

### 10. 蒸馏 (Distill)
Extract only what's essential and actionable. The rest is scaffolding.
One insight you will act on > ten insights you admired.
Ask: "What specifically changes about what I do after this research?"
If the answer is nothing, you didn't distill enough — go back to step 7/8.

### 11. 调用 (Invoke)
Apply the distilled knowledge. Do something with it:
- Create or update a skill
- Write a brain note
- Modify existing memory or rules
- Archive it if it's good context but not immediately actionable
- If nothing needs to change, explicitly close the loop: "Researched X, found nothing actionable"

## Two-Stage Filtering Pipeline

Don't treat all sources equally. Use the cheap filter first, then invest on survivors:

### Stage 1: Broad Harvest (cheap, high recall)
- Cast a wide net — search from 5+ query angles, collect everything that looks relevant
- Quick heuristic filter: title + snippet relevance, domain authority, recency
- Accept false positives. This is about recall, not precision
- Goal: gather 3-5x more candidates than you need

### Stage 2: Deep Verify (expensive, high precision)
- Only go deep on the top candidates from Stage 1
- Read full content, cross-reference claims, verify methodology
- Check 2+ independent sources before accepting a claim
- Discard weak sources here — be ruthless

### Why this works
The expensive operation (deep reading, cross-referencing, LLM analysis) is only applied to surviving candidates. Without Stage 1 filtering, you waste depth on noise. Without Stage 2 verification, you surface breadth without confidence.

## Storage Rules
- Academic papers → `research/<topic>` in gbrain (concepts, not raw text)
- Technical references → `web-research/<topic>` in gbrain
- Behavioral patterns from the research → extract as new skills
- Raw search results → don't store, they're scaffolding

## Quality Rules
- Prefer primary sources (papers, official docs) over blogs
- Verify claims across 2+ independent sources
- If a search yields nothing useful, try a different angle — don't settle
- Store insights, not quotes — rewrite in your own understanding
- Tag contradictions explicitly — "Source A says X, Source B says Y"
- 取其精华去其糟粕 — every source has signal and noise, extract mechanisms not claims
- Anchoring rule: before concluding, check if anthropomorphic framing leaked in and re-frame mechanistically

## Depth over breadth
3 well-understood papers > 15 shallow article summaries.
