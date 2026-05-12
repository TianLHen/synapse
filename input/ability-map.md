# Ability Map — 能力路由表

Created 2026-05-12. Maps input types → skills → knowledge → output.
当遇到什么情况时，按这张表路由。

## 核心进化引擎

```
输入: 新代码/论文/工具/模式
  → 1. 诊断层：瓶颈 → 缺口 → 失败回溯
  → 2. Pipeline层：11步流水线（汇总→分类→清洗→解析→切片→调用→编译→进化→变异→蒸馏→调用）
  → 3. 元进化层：流程自查 → 瓶颈更新 → 技能自查
  → invoke: absorb-and-evolve v0.4.0
  → output: 技能更新 / 脑图笔记 / 规则修改 / 记忆写入

输入: 需要深挖某个研究领域
  → 调用: research-collector v0.4.0
  → 前置门控: Pre-Research Discipline（禁止拟人、禁止哲学僵尸）
  → 11步流水线（同上）
  → output: 脑图笔记 + 技能吸收

输入: 需要从对话/经验中提取可复用模式
  → 调用: skill-extractor v0.2.0
  → 约束门控: 大小≤15KB, 增长≤20%, frontmatter完整性
  → output: 新 SKILL.md / 旧 SKILL.md 进化

输入: 刚改完技能需要验证
  → 调用: skill-self-test v0.2.0
  → L1 加载验证（必做）→ L2 self-play生成测试（推荐）→ L3 对抗破坏（元技能必做）
  → output: 测试通过 / 失败需修复
```

## 多智能体协调

```
输入: 需要并行处理/多代理协作
  → 调用: omc-reference（技能注册表）
  → agent: planner/architect/code-reviewer/tdd-guide 等
  → output: 按 omc 协议产出

输入: Graphify
  → 调用: graphify
  → output: 知识图谱 HTML + JSON
```

## 知识路由

```
场景: 需要定位已有知识
  → 查 brain/notes/ 按主题索引
  → 核心脑图:
    ● ai-agent-self-evolution-landscape.md — 全景论文图谱
    ● hermes-self-evolution-architecture.md — GEPA进化架构
    ● community-project-internalization.md — 社区项目内化
    ● autonomous-operation-mode.md — 自主运行模式
    ● capabilities-and-tools.md — 工具能力清单

场景: 需要跨 session 记忆
  → 查 memory/ MEMORY.md 索引
  → 核心记忆: 大哥身份、兄弟排位、环境配置、表情系统

场景: 需要守纪律
  → 查 rules/ 相关规则
  → coding-style、security、testing、performance、code-review
```

## 能力边界（知道什么做不了）

| 做不到 | 原因 | 替代方案 |
|--------|------|---------|
| 改模型权重 | API 调用硬限制 | 上下文工程（ACE模式） |
| 加新 tool | 工具集固定 | 优化现有工具的调用方式 |
| 离线运行 | 云端 API 依赖 | 本地 prompt 优化减少 API 开销 |
| 实时学习 | 跨 session 知识需持久化 | brain notes + memory 体系 |

## 当前缺口（诊断层答案 2026-05-12）

1. 第三方未使用技能占了注意力 → 已审计，明确非核心技能的地位
2. 知识图谱未建跨笔记关联 → **下一个应补的缺口**
3. 变异步骤深度不足 → 每次 Pipeline 强制 3+ 变异尝试

## 路由规则

简单粗暴：
- 进化相关 → absorb-and-evolve + research-collector + skill-extractor + skill-self-test
- 协调相关 → omc-reference
- 知识管理 → brain notes + graphify
- 设计相关 → 第三方技能（非核心，按需调用）
- 纪律相关 → rules/

遇事不决 → 走诊断层先问瓶颈。



  - 测试刺激级联系统

  - test: 刺激自动级联 02:56:30

  - test: 密度评估修正 02:57:41

## 刺激级联测试 (Stimulus Cascade Test)

This section tests the automatic stimulus-driven cascade system:
- Stimulus detection layer monitors file system changes
- Different stimulus types map to different propagation parameters
- Sense evaluates information density to determine processing depth
- Fire propagates signals along graph edges
- Consolidate strengthens/weakens connections based on activation
