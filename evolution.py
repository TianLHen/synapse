"""自我进化系统：行为日志 / 诊断 / 改进建议。

从 knowledge_graph.py 提取，保持独立可测。
load_graph() 在 diagnose() 中延迟导入以避免循环依赖。
"""

import json
from collections import Counter, defaultdict
from datetime import datetime

from const import BEHAVIOR_LOG, EVOLUTION_LOG


def log_behavior(action_type: str, details=None, score: float | None = None,
                 duration: float | None = None):
    """记录每次关键行为（learn/recall/stimulate/invoke）到行为日志。"""
    if details is None:
        details = {}
    log = []
    if BEHAVIOR_LOG.exists():
        log = json.loads(BEHAVIOR_LOG.read_text(encoding='utf-8'))
    log.append({
        'at': datetime.now().isoformat(),
        'action': action_type,
        'details': str(details)[:300] if not isinstance(details, dict) else details,
        'score': score,
        'duration': duration,
    })
    if len(log) > 500:
        log = log[-500:]
    BEHAVIOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    BEHAVIOR_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
    return len(log)


def analyze_behavior(n_last: int = 50) -> str:
    """分析最近 N 次行为，输出模式摘要。"""
    if not BEHAVIOR_LOG.exists():
        return "行为日志为空"

    log = json.loads(BEHAVIOR_LOG.read_text(encoding='utf-8'))
    if not log:
        return "行为日志为空"
    recent = log[-n_last:]

    lines = []
    lines.append(f"分析最近 {len(recent)} 次行为:\n")

    by_type = defaultdict(list)
    for entry in recent:
        by_type[entry['action']].append(entry)

    for action_type in sorted(by_type):
        entries = by_type[action_type]
        scores = [e.get('score') for e in entries if e.get('score') is not None]
        avg = sum(scores) / len(scores) if scores else None
        line = f"  {action_type}: {len(entries)} 次"
        if avg is not None:
            line += f", 平均评分 {avg:.2f}"
        lines.append(line)

    if len(recent) >= 2:
        first = recent[0]['at']
        last = recent[-1]['at']
        lines.append(f"\n  时间跨度: {first[:16]} → {last[:16]}")

    return '\n'.join(lines)


def diagnose() -> list:
    """自我诊断：扫描图谱 + 行为日志，输出薄弱项排名。

    Returns:
        [(issue_id, 描述, 严重度分), ...] 按严重度降序
    """
    # 延迟导入以避免循环依赖
    from knowledge_graph import load_graph

    findings = []

    # ── 1. 图谱结构诊断 ──
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']
    n, e = len(nodes), len(edges)
    ratio = e / max(n, 1)

    if ratio < 1.5:
        findings.append(('sparse_graph', f'图谱连接度 {ratio:.1f} 偏低，概念间缺连接', 5))
    elif ratio > 15:
        findings.append(('dense_graph', f'图谱连接度 {ratio:.1f} 偏高，可能有冗余边', 4))

    conv_count = sum(1 for nd in nodes if nd.get('group') == 'conversation')
    noise_ratio = conv_count / max(n, 1)
    if noise_ratio > 0.6:
        findings.append(('noise_dominated', f'conversation 节点 {noise_ratio:.0%}，噪音偏多', 7))

    deg = Counter()
    for e in edges:
        deg[e['source']] += 1
        deg[e['target']] += 1
    orphans = sum(1 for nd in nodes if deg.get(nd['id'], 0) == 0)
    if orphans > n * 0.1:
        findings.append(('orphan_nodes', f'{orphans} 个孤立节点 ({orphans/n:.0%})', 6))

    # ── 2. 行为日志诊断 ──
    if BEHAVIOR_LOG.exists():
        log = json.loads(BEHAVIOR_LOG.read_text(encoding='utf-8'))
        recent = log[-100:]

        recall_entries = [x for x in recent if x['action'] == 'recall']
        if recall_entries:
            null_recalls = sum(1 for x in recall_entries
                               if isinstance(x.get('score'), (int, float)) and x['score'] == 0)
            if len(recall_entries) >= 3:
                miss_rate = null_recalls / len(recall_entries)
                if miss_rate > 0.4:
                    findings.append(('recall_miss', f'recall 无结果率 {miss_rate:.0%}，匹配逻辑需优化', 9))

        learn_entries = [x for x in recent if x['action'] == 'learn']
        if learn_entries:
            low_quality = sum(1 for x in learn_entries
                              if isinstance(x.get('details'), dict)
                              and x['details'].get('nodes', 10) < 5)
            if len(learn_entries) >= 3 and low_quality > len(learn_entries) * 0.5:
                findings.append(('low_learn_yield', f'learn 过半产出 <5 节点，quality gate 过严或话题过窄', 5))

    findings.sort(key=lambda x: x[2], reverse=True)
    return findings


def suggest_improvements(diagnosis: list) -> list:
    """根据诊断结果生成可执行的改进方案。"""
    remedies = {
        'sparse_graph':    '增加 learn() 调用频率，或在对话中主动提取更多连接',
        'dense_graph':     '运行 trim_cooccurrence() 修剪冗余共现边',
        'noise_dominated': '运行 clean_conversation() 清理噪音，或 tighten learn() quality gate',
        'orphan_nodes':    '孤立节点可删除，或通过 cross_reference() 尝试连接',
        'recall_miss':     ('① 检查 recall 匹配逻辑：增加中文分词广度\n'
                            '② 尝试 BFS depth=2 扩大搜索范围\n'
                            '③ 确认查询关键词存在于图谱中'),
        'low_learn_yield': '检查 text 是否过短，或 quality gate 阈值可微调',
    }
    return [remedies.get(f[0], f'未预定义方案: {f[1]}') for f in diagnosis]


def append_evolution_log(entry: str):
    """追加进化日志条目。"""
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    line = f"\n## {timestamp}\n{entry}\n"
    EVOLUTION_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(EVOLUTION_LOG, 'a', encoding='utf-8') as f:
        f.write(line)
