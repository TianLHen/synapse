#!/usr/bin/env python3
"""
知识图谱管道 — 11步：汇总→分类→数据清洗→解析→切片→调用→编译→进化→变异→蒸馏→调用

不是"大脑模拟"，是结构化的知识持久化系统。
每条输出都有明确用途，没有自嗨的闭环。

用法:
    python knowledge_graph.py status              # 图谱状态
    python knowledge_graph.py collect             # 01 汇总
    python knowledge_graph.py full                # 全量运行 01-10
    python knowledge_graph.py pipeline <n>        # 从第 n 步开始运行
    python knowledge_graph.py rebuild             # 全量重建（清空后全量）
    python knowledge_graph.py query <关键词>       # 查询图谱
"""

import json
import os
import re
import hashlib
import shutil
import sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

from const import (
    GRAPH_DIR, INPUT_DIR, SEMANTIC_DIR, GRAPH_JSON, CHANGELOG, HASH_FILE,
    WORKSPACE_DIR, MEMORY_DIR, EVOLUTION_LOG,
    STIMULUS_LOG, ACTION_LOG, SOURCE_FILES, STOP_WORDS_EN, STOP_LEARN_EXTRA,
)

# LLM 语义提取（延迟导入，无 key 时静默跳过）
_llm_registry = None
_sandbox = None
_bus = None


# ============================================================
# 工具函数
# ============================================================

def _file_hash(path):
    return hashlib.md5(Path(path).read_bytes()).hexdigest()


def load_hashes():
    if HASH_FILE.exists():
        return json.loads(HASH_FILE.read_text(encoding='utf-8'))
    return {}


def save_hashes(hashes):
    HASH_FILE.write_text(json.dumps(hashes, indent=2), encoding='utf-8')


WAL_PATH = GRAPH_DIR / 'graph.wal'


def _wal_write(graph_dict):
    """写入 WAL（write-ahead log），返回 JSON 字符串。"""
    import hashlib
    json_str = json.dumps(graph_dict, indent=2, ensure_ascii=False)
    checksum = hashlib.sha256(json_str.encode('utf-8')).hexdigest()
    wal_entry = json.dumps({
        'data': graph_dict,
        'checksum': checksum,
        'written_at': datetime.now().isoformat(),
    }, ensure_ascii=False)
    WAL_PATH.write_text(wal_entry, encoding='utf-8')
    return json_str


def _wal_recover():
    """从 WAL 恢复 graph.json。成功返回 True，失败返回 False。"""
    import hashlib
    if not WAL_PATH.exists():
        return False
    try:
        wal = json.loads(WAL_PATH.read_text(encoding='utf-8'))
        data = wal.get('data')
        expected = wal.get('checksum', '')
        actual = hashlib.sha256(
            json.dumps(data, indent=2, ensure_ascii=False).encode('utf-8')
        ).hexdigest()
        if actual == expected:
            GRAPH_JSON.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding='utf-8'
            )
            WAL_PATH.unlink(missing_ok=True)
            return True
    except Exception:
        pass
    return False


def load_graph():
    # 检查 WAL 恢复
    if not GRAPH_JSON.exists() and WAL_PATH.exists():
        if _wal_recover():
            print("  [!] 从 WAL 恢复 graph.json")

    sb = _ensure_sandbox()
    if not GRAPH_JSON.exists():
        return {'nodes': [], 'edges': [], 'built_at': None}
    try:
        if sb:
            content = sb.read(str(GRAPH_JSON))
            if content is None:
                raise json.JSONDecodeError("Sandbox denied", "", 0)
        else:
            content = GRAPH_JSON.read_text(encoding='utf-8')
        return json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        # JSON 损坏 → 尝试 WAL 恢复
        if WAL_PATH.exists() and _wal_recover():
            print(f"  [!] graph.json 损坏 ({e}), 从 WAL 恢复...")
            return json.loads(GRAPH_JSON.read_text(encoding='utf-8'))
        # 再尝试从 .bak 恢复
        bak = GRAPH_JSON.with_suffix('.json.bak')
        if bak.exists():
            print(f"  [!] graph.json 损坏 ({e}), 从备份恢复...")
            import shutil
            shutil.copy2(bak, GRAPH_JSON)
            return json.loads(GRAPH_JSON.read_text(encoding='utf-8'))
        print(f"  [!] graph.json 损坏且无备份, 返回空图谱: {e}")
        return {'nodes': [], 'edges': [], 'built_at': None}


def save_graph(graph):
    sb = _ensure_sandbox()
    json_str = _wal_write(graph)
    # 备份已有文件
    if GRAPH_JSON.exists():
        import shutil
        shutil.copy2(GRAPH_JSON, GRAPH_JSON.with_suffix('.json.bak'))
    if sb:
        sb.write(str(GRAPH_JSON), json_str)
    else:
        GRAPH_JSON.write_text(json_str, encoding='utf-8')
    # 写入成功 → 删除 WAL
    WAL_PATH.unlink(missing_ok=True)


def append_changelog(entry):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    with open(CHANGELOG, 'a', encoding='utf-8') as f:
        f.write(f"\n## {timestamp}\n{entry}\n")


def safe_id(text, max_len=50):
    """生成安全的节点 ID。"""
    return re.sub(r'[\s\[\]\(\)《》#“”""]+', '_', text.strip().lower())[:max_len]


# ============================================================
# 01 汇总 (Collect) — 收集原始资料，检测变更
# ============================================================

def collect():
    """01 汇总：检测变更文件 → 复制到 input/ → 返回变更清单。"""
    old_hashes = load_hashes()
    new_hashes = {}
    changed = []
    unchanged = []

    for fname, src_path in SOURCE_FILES.items():
        if not src_path.exists():
            continue
        h = _file_hash(src_path)
        new_hashes[fname] = h
        if fname not in old_hashes:
            changed.append((fname, 'new'))
        elif old_hashes[fname] != h:
            changed.append((fname, 'modified'))
        else:
            unchanged.append(fname)

        # 复制到 input/
        dst = INPUT_DIR / fname
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src_path), str(dst))

    save_hashes(new_hashes)
    return changed, unchanged


# ============================================================
# 02 分类 (Classify) — 按类型分类源文件
# ============================================================

def classify():
    """02 分类：将 input/ 文件按内容类型分组。"""
    categories = {'architecture': [], 'skill': [], 'reference': [], 'note': []}
    for f in sorted(INPUT_DIR.glob("*.md")):
        stem = f.stem
        if stem in ('ability-map', 'my-brain-architecture'):
            categories['architecture'].append(stem)
        elif stem in ('absorb-and-evolve', 'research-collector', 'skill-extractor',
                       'skill-self-test', 'omc-reference'):
            categories['skill'].append(stem)
        elif stem == 'ai-agent-self-evolution-landscape':
            categories['reference'].append(stem)
        else:
            categories['note'].append(stem)
    return categories


# ============================================================
# 03 数据清洗 (Clean) — 去重、修复编码、过滤噪音
# ============================================================

def consume_action_log():
    """消费动作日志：读取 PostToolUse hook 写入的 Write/Edit 记录。"""
    if not ACTION_LOG.exists():
        return 0, {'total': 0, 'learn': 0, 'file': 0}
    raw = ACTION_LOG.read_text(encoding='utf-8').strip().split('\n')
    raw = [r.strip() for r in raw if r.strip()]
    ACTION_LOG.write_text('', encoding='utf-8')
    if not raw:
        return 0, {'total': 0, 'learn': 0, 'file': 0}
    learn_ops = sum(1 for r in raw if 'learn' in r.lower() or 'stimulate' in r.lower())
    file_ops = len(raw) - learn_ops
    return len(raw), {'total': len(raw), 'learn': learn_ops, 'file': file_ops}


def self_awareness():
    """自我感知：检查上次动作 + 源文件变更，并做出智能响应。

    不只是报告，而是根据操作类型触发不同行为：
    - 学习操作多 → 自动 invoke() 更新 memory
    - 文件变更多 → pipeline 增量进化
    - 无操作 → 静默
    """
    actions, breakdown = consume_action_log()
    changed, _ = collect()
    responses = []

    if actions:
        responses.append(f'上次做了 {actions} 次文件操作'
                         f'（学习 {breakdown["learn"]} / 文件 {breakdown["file"]}）')

        # 有学习操作 → 更新记忆系统
        if breakdown['learn'] > 0:
            invoke()
            export_html()
            responses.append(f'自动更新 memory + HTML')
            # 自动诊断
            try:
                from evolution import diagnose
                findings = diagnose()
                if findings:
                    for issue_id, desc, severity in findings[:2]:
                        responses.append(f'诊断: {desc} ({severity}/10)')
            except Exception:
                pass

    if changed:
        responses.append(f"{len(changed)} 个源文件变更 → 增量进化")
        run_pipeline(start_step=7)
        invoke()
        responses.append(f'pipeline + memory 已更新')

    if responses:
        s = ' | '.join(responses)
        print(f'  -> {s}')
        return s
    return None


def clean_content(text):
    """03 数据清洗：修复编码问题，移除噪音字符。"""
    # 规范化换行
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    # 移除控制字符（保留换行和制表符）
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.strip()


# ============================================================
# 04 解析 (Parse) — 结构提取（标题树 + 交叉引用）
# ============================================================

def parse_structural(file_path):
    """04 解析：正则提取标题层级和交叉引用。"""
    content = file_path.read_text(encoding='utf-8')
    content = clean_content(content)
    stem = file_path.stem
    nodes = []
    edges = []

    # 文件节点
    file_label = stem.replace('-', ' ').title()
    nodes.append({
        'id': stem, 'label': file_label, 'type': 'file',
        'source': stem + '.md', 'group': 'file',
    })

    # 标题树
    for level, tag in [('h1', r'^# '), ('h2', r'^## '), ('h3', r'^### ')]:
        for h in re.findall(rf'^{tag}(.+)$', content, re.M):
            safe = safe_id(h.strip())
            nid = f"{stem}/{safe}"
            nodes.append({
                'id': nid, 'label': h.strip()[:80], 'type': 'heading',
                'source': stem + '.md', 'group': level,
            })
            edges.append({
                'source': stem, 'target': nid,
                'relation': 'contains',
                'confidence': 1.0,
            })

    # 交叉引用（文件之间的显式链接）
    known_stems = list(SOURCE_FILES.keys())
    known_stems = [s.replace('.md', '') for s in known_stems if s != stem + '.md']
    if known_stems:
        ref_pattern = '|'.join(re.escape(s) for s in known_stems)
        for ref in set(re.findall(ref_pattern, content)):
            edges.append({
                'source': stem, 'target': ref,
                'relation': 'references',
                'confidence': 1.0,
            })

    return nodes, edges


# ============================================================
# 05 切片 (Chunk) — 分块
# ============================================================

def chunk_content(content):
    """05 切片：将内容按标题和段落拆分为可处理块。"""
    chunks = []
    lines = content.split('\n')
    current_h1 = ''
    current_h2 = ''
    current_block = []
    block_start = 0

    for i, line in enumerate(lines):
        if line.startswith('# '):
            if current_block and i - block_start > 3:
                chunks.append({
                    'h1': current_h1, 'h2': current_h2,
                    'content': '\n'.join(current_block),
                    'line_start': block_start, 'line_end': i,
                })
            current_h1 = line.replace('# ', '').strip()
            current_h2 = ''
            current_block = [line]
            block_start = i
        elif line.startswith('## '):
            if current_block and i - block_start > 3:
                chunks.append({
                    'h1': current_h1, 'h2': current_h2,
                    'content': '\n'.join(current_block),
                    'line_start': block_start, 'line_end': i,
                })
            current_h2 = line.replace('## ', '').strip()
            current_block = [line]
            block_start = i
        else:
            current_block.append(line)

    if current_block:
        chunks.append({
            'h1': current_h1, 'h2': current_h2,
            'content': '\n'.join(current_block),
            'line_start': block_start, 'line_end': len(lines),
        })

    return [c for c in chunks if len(c['content']) >= 20]


# ============================================================
# 06 调用 (Process) — 为语义提取准备数据
# ============================================================

def prepare_semantic(stem):
    """06 调用：为语义提取准备输入信息。"""
    src_path = SOURCE_FILES.get(stem + '.md')
    if not src_path or not src_path.exists():
        return None
    content = src_path.read_text(encoding='utf-8')
    return {
        'file': stem + '.md',
        'path': str(src_path),
        'size': len(content),
        'lines': len(content.split('\n')),
        'chunks': chunk_content(content),
    }


def save_semantic_result(stem, data):
    """保存 Agent 语义提取结果到 semantic/ 目录。"""
    SEMANTIC_DIR.mkdir(parents=True, exist_ok=True)
    path = SEMANTIC_DIR / f"{stem}.json"
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


_LLM_EXTRACT_PROMPT = """你是一个知识图谱提取器。分析以下 Markdown 内容，提取其中的核心概念和它们之间的关系。

返回 JSON 格式（不要任何其他文字）：
{
  "nodes": [{"id": "概念名", "label": "显示名称", "type": "concept", "group": "domain"}],
  "edges": [{"source": "概念名", "target": "概念名", "relation": "关系类型", "confidence": 0.9}]
}

规则：
- 每个节点 id 用英文小写+连字符（如 "reinforcement-learning"）
- label 可以是中文
- relation 用具体的关系名（如 "part_of", "used_for", "related_to", "prerequisite_of"）
- 只提取内容中明确出现的概念，不要编造
- 如果内容太短或没有概念，返回 {"nodes": [], "edges": []}
- confidence 0.0-1.0

内容：
"""


def _ensure_llm_registry():
    """初始化 LLM provider 注册表（延迟加载）。无 key 时返回 None。"""
    global _llm_registry
    if _llm_registry is not None:
        return _llm_registry

    try:
        from llm import (AnthropicProvider, OpenAIProvider, OllamaProvider,
                          ProviderRegistry, RouteRule, LLMRequest, Message, Role)

        reg = ProviderRegistry()
        reg.rules = []
        ready = False

        # Anthropic 优先（如果有 key）
        if os.environ.get('ANTHROPIC_API_KEY'):
            try:
                reg.register('anthropic', AnthropicProvider())
                reg.rules.append(RouteRule('sonnet', 'claude-sonnet-4-6', 'anthropic', priority=20))
                ready = True
            except Exception:
                pass

        # OpenAI 备选
        if not ready and os.environ.get('OPENAI_API_KEY'):
            try:
                reg.register('openai', OpenAIProvider())
                reg.rules.append(RouteRule('gpt4o', 'gpt-4o', 'openai', priority=10))
                ready = True
            except Exception:
                pass

        # Ollama 最后
        if not ready:
            try:
                ollama = OllamaProvider()
                if ollama.models:
                    reg.register('ollama', ollama)
                    reg.rules.append(RouteRule('local', ollama.models[0], 'ollama', priority=5))
                    ready = True
            except Exception:
                pass

        if not ready:
            _llm_registry = None
            return None

        _llm_registry = reg
        return reg
    except ImportError:
        return None


def semantic_extract_with_llm(stem, content):
    """用 LLM 从内容中提取概念和关系，结果存 semantic/。失败时静默跳过。"""
    reg = _ensure_llm_registry()
    if reg is None:
        return False

    # 内容太长则截断
    max_chars = 8000
    if len(content) > max_chars:
        content = content[:max_chars] + "\n\n... [truncated]"

    try:
        req = LLMRequest(
            model='semantic-extract',
            messages=[Message(Role.USER, _LLM_EXTRACT_PROMPT + content)],
            temperature=0.1,
            max_tokens=2000,
        )
        resp = reg.complete(req)
        if not resp.content:
            return False

        # 解析 JSON
        text = resp.content.strip()
        if text.startswith('```'):
            text = text.split('\n', 1)[1]
            text = text.rsplit('```', 1)[0]
        data = json.loads(text.strip())
        if not isinstance(data, dict):
            return False

        data['_extracted_by'] = 'llm'
        data['_model'] = resp.model
        data['_provider'] = resp.provider
        save_semantic_result(stem, data)
        return True
    except Exception:
        return False


def _ensure_sandbox():
    """初始化沙箱单例（延迟加载）。"""
    global _sandbox
    if _sandbox is not None:
        return _sandbox
    try:
        from sandbox import Sandbox, Policy, Action, Effect
        sb = Sandbox(workspace_dir=GRAPH_DIR)
        # 添加执行策略
        sb.add_policy(Policy(Action.EXECUTE, Effect.ALLOW, "python*", reason="Python 脚本"))
        sb.add_policy(Policy(Action.EXECUTE, Effect.ALLOW, "pip*", reason="安装包"))
        sb.add_policy(Policy(Action.EXECUTE, Effect.ALLOW, "git*", reason="Git 操作"))
        sb.add_policy(Policy(Action.EXECUTE, Effect.ALLOW, "powershell*", reason="PowerShell"))
        _sandbox = sb
        return sb
    except Exception:
        return None


def _ensure_eventbus():
    """初始化事件总线（延迟加载）+ 发现并注册技能模块。"""
    global _bus
    if _bus is not None:
        return _bus
    try:
        from protoskill import EventBus, Event, discover_skills, SkillRegistry_v2
        bus = EventBus()
        # 注册内置 handler
        bus.on('pipeline:complete', lambda e: (
            invoke(),
            log_behavior('pipeline', {'steps': e.data.get('steps', [])}, score=0)
        ))
        bus.on('learn:complete', lambda e: log_behavior(
            'learn', {'source': e.data.get('source', ''), 'nodes': e.data.get('nodes', 0)}, score=0
        ))
        bus.on('recall:complete', lambda e: log_behavior(
            'recall', {'topic': str(e.data.get('topic', ''))[:60], 'hits': e.data.get('hits', 0)}, score=0
        ))
        # 发现并激活 skills/ 目录下的技能
        _skill_registry = SkillRegistry_v2()
        for skill in discover_skills():
            name = skill.name
            if _skill_registry.register(skill) and skill.module:
                try:
                    if hasattr(skill.module, 'on_activate'):
                        skill.module.on_activate(bus)
                except Exception as e:
                    print(f"  [四弟] 激活技能 {name} 失败: {e}")
        bus._skill_registry = _skill_registry  # 挂到总线上方便热替换
        _bus = bus
        return bus
    except Exception:
        return None


def load_semantic_results():
    """加载所有语义提取结果。"""
    all_nodes = []
    all_edges = []
    for f in sorted(SEMANTIC_DIR.glob('*.json')):
        data = json.loads(f.read_text(encoding='utf-8'))
        all_nodes.extend(data.get('nodes', []))
        all_edges.extend(data.get('edges', []))
    return all_nodes, all_edges


# ============================================================
# 07 编译 (Compile) — 构建/更新 graph.json
# ============================================================

def compile_graph(structural_nodes, structural_edges, semantic_nodes, semantic_edges):
    """07 编译：合并结构提取 + 语义提取 → graph.json。"""
    seen_ids = set()
    merged_nodes = []

    for n in structural_nodes + semantic_nodes:
        nid = n['id']
        if nid not in seen_ids:
            seen_ids.add(nid)
            # 语义节点覆盖结构节点（同 id 时）
            existing = next((x for x in merged_nodes if x['id'] == nid), None)
            if existing:
                if n.get('extracted_by') == 'llm':
                    existing.update(n)
            else:
                n.pop('file_type', None)
                if 'group' not in n:
                    n['group'] = 'concept'
                merged_nodes.append(n)

    # 边去重
    seen_edges = set()
    merged_edges = []
    for e in structural_edges + semantic_edges:
        key = (e['source'], e['target'], e.get('relation', 'references'))
        if key not in seen_edges:
            seen_edges.add(key)
            merged_edges.append(e)

    graph = {
        'nodes': merged_nodes,
        'edges': merged_edges,
        'built_at': datetime.now().isoformat(),
    }
    save_graph(graph)
    return len(merged_nodes), len(merged_edges)


# ============================================================
# 08 进化 (Evolve) — 增量更新，不重建
# ============================================================

def evolve(file_stem):
    """08 进化：增量更新单个文件的节点/边（不是全量重建）。"""
    src_path = SOURCE_FILES.get(file_stem + '.md')
    if not src_path or not src_path.exists():
        return 0, 0

    structural_nodes, structural_edges = parse_structural(src_path)

    graph = load_graph()
    existing_ids = {n['id'] for n in graph['nodes']}

    new_nodes = [n for n in structural_nodes if n['id'] not in existing_ids]
    graph['nodes'].extend(new_nodes)

    existing_edge_keys = {(e['source'], e['target'], e.get('relation', 'references'))
                          for e in graph['edges']}
    new_edges = [e for e in structural_edges
                 if (e['source'], e['target'], e.get('relation', 'references'))
                 not in existing_edge_keys]
    graph['edges'].extend(new_edges)
    graph['built_at'] = datetime.now().isoformat()

    save_graph(graph)
    return len(new_nodes), len(new_edges)


# ============================================================
# 09 变异 (Variate) — 交叉引用，受控探索
# ============================================================

def cross_reference():
    """09 变异：跨文件相似节点连接。

    只连接不同源文件的语义相似节点。
    阈值严格（Jaccard ≥ 0.5），避免噪音。
    """
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    existing = set()
    for e in edges:
        s, t = e['source'], e['target']
        existing.add((s, t))
        existing.add((t, s))

    # 只处理语义节点（非文件/标题结构）
    valid = [n for n in nodes if n.get('group') not in ('file', 'h1', 'h2', 'h3')]
    if len(valid) < 2:
        return 0

    stopwords = {'the', 'a', 'an', 'and', 'or', 'of', 'in', 'to', 'for',
                 'with', 'on', 'at', 'by', 'is', 'it', 'as', 'be', 'this'}

    node_tokens = {}
    node_source = {}
    for n in valid:
        label = n.get('label', n['id']).lower()
        tokens = set(re.findall(r'[a-z0-9一-鿿]+', label))
        node_tokens[n['id']] = {t for t in tokens if len(t) >= 2 and t not in stopwords}
        node_source[n['id']] = n.get('source', '')

    word_index = defaultdict(set)
    for nid, tokens in node_tokens.items():
        for t in tokens:
            word_index[t].add(nid)

    new_edges = 0
    compared = set()

    for candidates in word_index.values():
        cand_list = [c for c in candidates if c in node_tokens]
        if len(cand_list) < 2:
            continue
        for i in range(len(cand_list)):
            for j in range(i + 1, len(cand_list)):
                a, b = cand_list[i], cand_list[j]
                pair = (a, b) if a < b else (b, a)
                if pair in compared:
                    continue
                compared.add(pair)

                # 跳过同源文件
                if node_source.get(a) and node_source.get(a) == node_source.get(b):
                    continue
                if pair in existing:
                    continue

                tokens_a = node_tokens.get(a, set())
                tokens_b = node_tokens.get(b, set())
                if not tokens_a or not tokens_b:
                    continue

                # Jaccard 相似度
                jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
                if jaccard >= 0.5:
                    edges.append({
                        'source': a, 'target': b,
                        'relation': 'conceptually_related_to',
                        'confidence': 'INFERRED',
                        'confidence_score': round(jaccard, 2),
                    })
                    new_edges += 1

    if new_edges:
        graph['built_at'] = datetime.now().isoformat()
        save_graph(graph)

    return new_edges


# ============================================================
# 10 蒸馏 (Distill) — 剪枝 + 归档
# ============================================================

def distill():
    """10 蒸馏：删除低置信度推理边，归档冷数据。

    规则:
    - INFERRED 边置信度 < 0.3 → 删除
    - 节点无边且不是文件节点 → 删除
    - 记录变更到 changelog
    """
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']
    before_nodes = len(nodes)
    before_edges = len(edges)

    # 删除低置信度推理边
    pruned_edges = [e for e in edges
                    if not (e.get('confidence') == 'INFERRED'
                            and e.get('confidence_score', 0) < 0.3)]
    pruned_count = before_edges - len(pruned_edges)

    # 找出孤立节点（无边连接且不是文件节点）
    edge_node_ids = set()
    for e in pruned_edges:
        edge_node_ids.add(e['source'])
        edge_node_ids.add(e['target'])

    orphan_nodes = [n for n in nodes
                    if n['id'] not in edge_node_ids
                    and n.get('group') not in ('file',)]
    orphan_count = len(orphan_nodes)
    kept_nodes = [n for n in nodes if n['id'] in edge_node_ids or n.get('group') in ('file',)]

    if pruned_count or orphan_count:
        graph['nodes'] = kept_nodes
        graph['edges'] = pruned_edges
        graph['built_at'] = datetime.now().isoformat()
        save_graph(graph)

    # 记录
    summary = f"**Distill:** pruned {pruned_count} low-conf edges, removed {orphan_count} orphan nodes"
    append_changelog(summary)
    return pruned_count, orphan_count


# ============================================================
# 11 调用 (Invoke) — 写入记忆系统 → 影响行为
# ============================================================

def invoke():
    """11 调用：从图谱提取知识 → 写入记忆系统。

    输出聚焦于可用的知识，而非统计数据。
    过滤噪声节点（泛词），只保留有意义的领域概念和关系链。
    """
    if not MEMORY_DIR.exists():
        return 0

    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']
    built_at = graph.get('built_at', 'unknown')

    label_map = {n['id']: n.get('label', n['id']) for n in nodes}

    # 节点度数
    degree = Counter()
    for e in edges:
        degree[e['source']] += 1
        degree[e['target']] += 1

    # 噪声节点 — 从 learn() 引入的大量泛词
    noise_labels = STOP_WORDS_EN
    noise_ids = set()
    for n in nodes:
        label = n.get('label', '').lower().strip()
        if label in noise_labels or len(label) <= 2:
            noise_ids.add(n['id'])
        # 全是单一英文字母+数字的节点名也是噪音
        if re.match(r'^[a-z0-9]{1,2}$', label):
            noise_ids.add(n['id'])

    # 领域分组（去噪后取 top）
    domain_areas = {
        '架构与机制': ('architecture', 'mechanism', 'pattern'),
        '技能与方法': ('skill', 'method', 'step', 'constraint'),
        '核心概念': ('concept', 'principle', 'rationale'),
        '实现细节': ('code', 'protocol', 'process', 'tool', 'test', 'metric', 'capability', 'limitation', 'check', 'pipeline'),
    }

    lines = []
    lines.append("# Knowledge Graph Injection")
    lines.append(f"_Last built: {built_at}_\n")

    for area_name, area_groups in domain_areas.items():
        area_nodes = []
        for n in nodes:
            g = n.get('group', '')
            if g not in area_groups:
                continue
            if n['id'] in noise_ids:
                continue
            deg = degree.get(n['id'], 0)
            area_nodes.append((n.get('label', n['id']), deg, g))
        if not area_nodes:
            continue
        area_nodes.sort(key=lambda x: x[1], reverse=True)
        lines.append(f"## {area_name}")
        for label, deg, g in area_nodes[:6]:
            lines.append(f"- **{label}** ({g}, deg={deg})")
        lines.append("")

    # 关键关系链
    key_relations = [e for e in edges
                     if e.get('relation') in ('implements', 'uses', 'routes_to', 'built_on')]
    if key_relations:
        lines.append("## 关键关系")
        for e in key_relations[:10]:
            s = label_map.get(e['source'], e['source'])[:40]
            t = label_map.get(e['target'], e['target'])[:40]
            lines.append(f"- {s} **{e['relation']}** {t}")
        lines.append("")

    # 研究领域概览 — 从 conversation 节点提取
    research_terms = [n.get('label', '') for n in nodes
                      if n.get('group') == 'conversation'
                      and n.get('source', '').startswith('research:')
                      and n['id'] not in noise_ids]
    if research_terms:
        # 按来源分组
        research_groups = defaultdict(list)
        for n in nodes:
            if n.get('group') != 'conversation':
                continue
            src = n.get('source', '')
            if not src.startswith('research:'):
                continue
            research_groups[src.replace('research:', '', 1)].append(n.get('label', ''))
        lines.append("## 研究领域")
        for src, terms in sorted(research_groups.items()):
            lines.append(f"- **{src}**: {', '.join(sorted(set(terms))[:8])}")
        lines.append("")

    # Hub 概念（去噪）
    top_hubs = []
    seen = set()
    for nid, deg in degree.most_common(200):
        if nid in noise_ids:
            continue
        label = label_map.get(nid, nid)
        if label.lower() in noise_labels:
            continue
        if label not in seen:
            seen.add(label)
            top_hubs.append((label, deg))
        if len(top_hubs) >= 8:
            break

    lines.append("## 枢纽概念")
    for label, deg in top_hubs:
        lines.append(f"- {label} (deg={deg})")
    lines.append("")

    # 总览
    group_counts = Counter(n.get('group', 'unknown') for n in nodes
                           if n.get('group') not in ('file', 'h1', 'h2', 'h3'))
    lines.append("## 总览")
    lines.append(f"- {len(nodes)} 节点 / {len(edges)} 边")
    lines.append(f"- conversation 领域占比: {group_counts.get('conversation', 0)} 节点 ({group_counts.get('conversation', 0)/max(len(nodes),1)*100:.0f}%)")

    result = '\n'.join(lines)
    kg_memory = MEMORY_DIR / "knowledge_graph_state.md"
    kg_memory.write_text(result, encoding='utf-8')
    log_behavior('invoke', {'nodes': len(nodes), 'edges': len(edges)})
    return 1


# ============================================================
# 管道编排
# ============================================================

def run_pipeline(start_step=1):
    """从指定步骤开始运行管道。"""
    steps = {
        1: ('汇总', lambda: collect()),
        2: ('分类', lambda: classify()),
        3: ('数据清洗', lambda: "N/A (inline in parse)"),
        4: ('解析', lambda: run_parse_all()),
        5: ('切片', lambda: "N/A (inline in process)"),
        6: ('调用', lambda: run_semantic_prepare()),
        7: ('编译', lambda: compile_all()),
        8: ('进化', lambda: run_evolve_all()),
        9: ('变异', lambda: cross_reference()),
        10: ('蒸馏', lambda: distill()),
        11: ('调用 → 执行', lambda: invoke()),
    }

    results = []
    for step_num in range(start_step, 12):
        if step_num not in steps:
            continue
        name, func = steps[step_num]
        print(f"\n  [{step_num:02d}/11] {name}...")
        result = func()
        results.append((step_num, name, result))

    print("\n═══ Pipeline Results ═══")
    for step_num, name, result in results:
        output = str(result).replace('\n', ' | ') if result else '(empty)'
        print(f"  [{step_num:02d}] {name}: {output[:120]}")

    # 自动诊断
    try:
        from evolution import diagnose
        findings = diagnose()
        if findings:
            print("\n  [自动诊断] 发现潜在问题:")
            for issue_id, desc, severity in findings[:3]:
                bar = '█' * severity + '░' * (10 - severity)
                print(f"    [{bar}] ({severity}/10) {desc}")
    except Exception:
        pass

    # 发射事件
    try:
        bus = _ensure_eventbus()
        if bus:
            from protoskill import Event
            bus.emit(Event('pipeline:complete', 'system', {'steps': list(range(start_step, 11))}))
    except Exception:
        pass

    return results


def run_parse_all():
    """解析所有源文件（04 解析）。"""
    total_nodes = 0
    total_edges = 0
    for fname in SOURCE_FILES:
        src_path = SOURCE_FILES[fname]
        if src_path.exists():
            n, e = parse_structural(src_path)
            total_nodes += len(n)
            total_edges += len(e)
    return f"{total_nodes} nodes, {total_edges} edges"


def run_semantic_prepare():
    """为语义提取准备所有文件（06 调用）。有 LLM key 时自动执行语义提取。"""
    results = []
    for fname in SOURCE_FILES:
        stem = fname.replace('.md', '')
        info = prepare_semantic(stem)
        if info:
            # 尝试 LLM 语义提取（无 key 时静默跳过）
            full_text = '\n\n'.join(c['content'] for c in info.get('chunks', []))
            if full_text and semantic_extract_with_llm(stem, full_text):
                results.append(f"{stem}[llm]")
            else:
                results.append(stem)
    return f"{len(results)} files prepared: {', '.join(results)}"


def compile_all():
    """编译所有结果（07 编译）。"""
    # 先跑所有文件的结构提取
    all_s_nodes = []
    all_s_edges = []
    for fname in SOURCE_FILES:
        src_path = SOURCE_FILES[fname]
        if src_path.exists():
            n, e = parse_structural(src_path)
            all_s_nodes.extend(n)
            all_s_edges.extend(e)

    # 加载语义提取结果
    sem_nodes, sem_edges = load_semantic_results()

    n_count, e_count = compile_graph(all_s_nodes, all_s_edges, sem_nodes, sem_edges)
    return f"{n_count} nodes, {e_count} edges"


def run_evolve_all():
    """进化所有源文件（08 进化）。"""
    total_new = 0
    for fname in SOURCE_FILES:
        stem = fname.replace('.md', '')
        new_n, new_e = evolve(stem)
        total_new += new_n + new_e
    return f"{total_new} new items"


# ============================================================
# 学习函数 — 对话/文本知识直接吸收到图谱
# ============================================================

def trim_cooccurrence(top_n: int = 5):
    """修剪共现边：每个节点只保留 top N 个最高度邻居的 co_occurred_with 边。

    旧版 learn() 的全连接策略产生了 O(n²) 的噪音边。
    新版已改用滑动窗口，但已有边需要清理。
    """
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    before = len(edges)

    # 计算全局节点度数
    global_deg = Counter()
    for e in edges:
        global_deg[e['source']] += 1
        global_deg[e['target']] += 1

    # 对每个节点，按邻居度数排序，只保留 topN 的 co_occurred_with
    keep_edges = []
    cooccur_seen = set()
    for e in edges:
        if e.get('relation') != 'co_occurred_with':
            keep_edges.append(e)
            continue

        key = (e['source'], e['target'])
        if key in cooccur_seen:
            continue
        cooccur_seen.add(key)
        cooccur_seen.add((e['target'], e['source']))
        keep_edges.append(e)

    # 按 source 分组，对每个节点只保留 topN
    neighbor_map = defaultdict(list)
    for e in keep_edges:
        if e.get('relation') != 'co_occurred_with':
            continue
        deg_source = global_deg.get(e['target'], 0)
        neighbor_map[e['source']].append((deg_source, e['target']))
        deg_target = global_deg.get(e['source'], 0)
        neighbor_map[e['target']].append((deg_target, e['source']))

    # 每个节点保留 topN 邻居
    keep_pairs = set()
    for nid, neighbors in neighbor_map.items():
        neighbors.sort(key=lambda x: x[0], reverse=True)
        for _, neighbor in neighbors[:top_n]:
            keep_pairs.add((nid, neighbor))

    # 过滤 co_occurred_with 边
    final_edges = []
    for e in edges:
        if e.get('relation') != 'co_occurred_with':
            final_edges.append(e)
        elif (e['source'], e['target']) in keep_pairs or (e['target'], e['source']) in keep_pairs:
            final_edges.append(e)

    graph['edges'] = final_edges
    graph['built_at'] = datetime.now().isoformat()
    save_graph(graph)

    removed = before - len(final_edges)
    print(f"  -> 修剪: 移除 {removed} 条共现边, 保留 {len(final_edges)} 条")
    return removed


def clean_conversation():
    """清理 conversation 类别中的噪音节点。

    旧版 learn() 提取了大量单英文单词，全部标记为 conversation group。
    新版 learn() 不再产生噪音，但已有节点需要清理。
    清理策略：删除所有单英文短词（≤4 字符）的 conversation 节点及其边。
    """
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    before_nodes = len(nodes)
    before_edges = len(edges)

    # 标记噪音 conversation 节点
    noise_ids = set()
    for n in nodes:
        if n.get('group') != 'conversation':
            continue
        label = n.get('label', '')
        # 单英文词 ≤ 4 字符
        if re.match(r'^[a-zA-Z][a-zA-Z.\-]{1,3}$', label):
            noise_ids.add(n['id'])
        # 纯数字
        elif re.match(r'^\d+$', label):
            noise_ids.add(n['id'])
        # 停用词
        elif label.lower() in STOP_WORDS_EN:
            noise_ids.add(n['id'])

    if not noise_ids:
        print("  -> 无噪音节点需要清理")
        return 0, 0

    # 删除噪音节点及其边
    clean_nodes = [n for n in nodes if n['id'] not in noise_ids]
    noise_edges = set()
    for e in edges:
        if e['source'] in noise_ids or e['target'] in noise_ids:
            noise_edges.add((e['source'], e['target'], e.get('relation', '')))
    clean_edges = [e for e in edges
                   if (e['source'], e['target'], e.get('relation', '')) not in noise_edges]

    graph['nodes'] = clean_nodes
    graph['edges'] = clean_edges
    graph['built_at'] = datetime.now().isoformat()
    save_graph(graph)

    removed_nodes = before_nodes - len(clean_nodes)
    removed_edges = before_edges - len(clean_edges)
    print(f"  -> 清理: 移除 {removed_nodes} 噪音节点, {removed_edges} 噪音边")
    return removed_nodes, removed_edges


def learn(text: str, source: str = 'conversation'):
    """从文本提取知识点，直接写入 graph.json（不走文件管道）。

    每次对话中提取概念，创建节点和边，与已有节点自动连接。

    质量门:
    - 不提取单英文词（仅保留多词短语和术语）
    - 中文概念最小 3 字
    - 引号短语最小 3 字
    - 完整停用词表过滤
    """
    if not text or not text.strip():
        return 0, 0

    try:
        return _learn_impl(text, source)
    except Exception as e:
        print(f"  [ERR] learn() 异常: {e}")
        log_behavior('learn', {'error': str(e)[:200]}, score=0)
        return 0, 0


def _learn_impl(text: str, source: str) -> tuple:
    """learn() 的实际实现，被异常包裹。"""

    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    existing_ids = {n['id'] for n in nodes}
    existing_labels_lower = {n.get('label', '').lower(): n['id'] for n in nodes}

    # 提取候选概念
    candidates = set()

    # 引号短语
    for _qp in ['"', "'"]:
        for m in re.findall(_qp + r'([^' + _qp + r']{2,40})' + _qp, text):
            m = m.strip()
            if len(m) >= 3:
                candidates.add(m)

    # 英文大写词组（专有名词、术语）— 只收 ≥2 词，单大写词如 "Foundations" 不要
    for c in re.findall(r'(?:[A-Z][a-z]*[\s-]){1,3}[A-Z][a-z]*', text):
        c = c.strip()
        if len(c) < 5 or len(c) > 60:
            continue
        # 必须包含空格（至少双词）
        if ' ' not in c:
            continue
        candidates.add(c)

    # 英文多词短语（小写起头但有信息量的组合词）
    # 捕获如 "reinforcement learning"、"working memory"、"long-term potentiation"
    stop_en_learn = STOP_WORDS_EN | STOP_LEARN_EXTRA
    for m in re.finditer(r'(?:[a-zA-Z][a-z]*[\s-]){1,3}[a-zA-Z][a-z]*', text):
        phrase = m.group().strip()
        if len(phrase) < 5 or len(phrase) > 60:
            continue
        # 必须至少含一个实词（非停用词）
        words = [w.lower().strip(' -') for w in re.split(r'[\s-]', phrase) if w.strip(' -')]
        content_words = [w for w in words if w not in stop_en_learn and len(w) >= 3]
        if not content_words:
            continue
        # 至少 2 个词才收（单词短语已被删除）
        if ' ' not in phrase:
            continue
        candidates.add(phrase)

    # 中文概念（3-8字，不再收2字词）
    stop_zh = {'什么', '为什么', '怎么', '这个', '那个', '一个', '可以',
               '没有', '不是', '就是', '但是', '而且', '因为', '所以',
               '已经', '知道', '觉得', '这样', '自己', '我们',
               '他们', '你们', '东西', '时候', '问题', '如果', '虽然',
               '主要', '重要', '基本', '一般', '其他', '目前', '需要',
               '通过', '进行', '以及', '这些', '一些', '可能', '不过',
               '之间', '相关', '不同', '开始', '成为', '注意', '方面',
               '之后', '之前', '以上', '以下', '方式', '特点', '作用',
               '结果', '过程', '关系', '意义', '影响', '出现', '包括',
               '必须', '应该', '可以', '不会', '不能', '基于', '关于',
               '提出', '发展', '利用', '采用', '用于', '具有', '来自',
               '分为', '分为', '每个', '其中', '来自', '以及', '第一',
               '第二', '第三', '最后', '当前', '传统'}
    for cw in re.findall(r'[一-鿿]{3,8}', text):
        if cw not in stop_zh:
            candidates.add(cw)

    candidates = {c for c in candidates if len(c) >= 2}

    # 最终去噪：检查每个候选词是否含实词（非停用词）
    # 对纯停用词构成的短语也过滤掉
    filtered = set()
    for c in candidates:
        words = re.split(r'[\s\-_]+', c.lower())
        content = [w for w in words if len(w) >= 2 and w not in stop_en_learn]
        if len(content) >= 1 or len(c) >= 8:
            # 至少含一个实词，或足够长（如中文短语）
            filtered.add(c)
    candidates = filtered

    if not candidates:
        return 0, 0

    # 匹配已有节点，创建新节点
    new_nodes = []
    new_edges = []
    concept_ids = {}

    for concept in candidates:
        cid = safe_id(f"conversation_{concept}")
        if cid in existing_ids or cid in concept_ids:
            concept_ids[concept] = cid
            continue

        # 模糊匹配已有 label
        label_lower = concept.lower()
        fuzzy_match = None
        for e_label, e_id in existing_labels_lower.items():
            if label_lower == e_label or \
               (len(label_lower) >= 4 and len(e_label) >= 4 and
                (label_lower in e_label or e_label in label_lower)):
                fuzzy_match = e_id
                break

        if fuzzy_match:
            concept_ids[concept] = fuzzy_match
            continue

        new_nodes.append({
            'id': cid,
            'label': concept[:60],
            'group': 'conversation',
            'source': source,
            'type': 'learned',
        })
        concept_ids[concept] = cid
        existing_ids.add(cid)

    if not new_nodes and len(concept_ids) < 2:
        return 0, 0

    # 共现概念之间创建边（滑动窗口 w=3，取代全连接）
    clist = list(concept_ids.values())
    window = 3
    for i in range(len(clist)):
        for j in range(i + 1, min(i + window, len(clist))):
            a, b = clist[i], clist[j]
            dup = any((e['source'] == a and e['target'] == b) or
                      (e['source'] == b and e['target'] == a)
                      for e in edges + new_edges)
            if not dup:
                new_edges.append({
                    'source': a, 'target': b,
                    'relation': 'co_occurred_with',
                    'confidence': 'INFERRED',
                    'confidence_score': 0.55,
                    'source_location': source,
                    'weight': 0.4,
                })

    # 新节点关联已有相关节点（子串匹配）
    if new_nodes:
        new_labels = {n.get('label', '').lower(): n['id'] for n in new_nodes}
        for n in nodes:
            nlabel = n.get('label', '').lower()
            nid = n['id']
            if not nlabel or len(nlabel) < 4:
                continue
            for new_label, new_id in new_labels.items():
                if not new_label or len(new_label) < 4:
                    continue
                if new_label in nlabel or nlabel in new_label:
                    dup = any((e['source'] == new_id and e['target'] == nid) or
                              (e['source'] == nid and e['target'] == new_id)
                              for e in edges + new_edges)
                    if not dup:
                        new_edges.append({
                            'source': new_id, 'target': nid,
                            'relation': 'conceptually_related_to',
                            'confidence': 'INFERRED',
                            'confidence_score': 0.5,
                            'source_location': source,
                            'weight': 0.35,
                        })

    # 写入
    if new_nodes or new_edges:
        graph['nodes'].extend(new_nodes)
        graph['edges'].extend(new_edges)
        graph['built_at'] = datetime.now().isoformat()
        save_graph(graph)

    print(f"  -> 学习: +{len(new_nodes)} 概念, +{len(new_edges)} 连接")
    log_behavior('learn', {'nodes': len(new_nodes), 'edges': len(new_edges)},
                 score=min(len(new_nodes) / 5, 10))
    # 发射事件
    try:
        bus = _ensure_eventbus()
        if bus:
            from protoskill import Event
            bus.emit(Event('learn:complete', 'learn', {
                'source': source, 'nodes': len(new_nodes), 'edges': len(new_edges)
            }))
    except Exception:
        pass
    return len(new_nodes), len(new_edges)


# ============================================================
# 刺激级联 — 从学习/对话/动作 → 图谱生长
# ============================================================

def log_stimulus(source: str, stype: str, data: dict | None = None):
    """记录主体刺激到日志。"""
    if data is None:
        data = {}
    log = []
    if STIMULUS_LOG.exists():
        log = json.loads(STIMULUS_LOG.read_text(encoding='utf-8'))
    log.append({
        'at': datetime.now().isoformat(),
        'source': source,
        'type': stype,
        'data': data,
    })
    if len(log) > 200:
        log = log[-200:]
    STIMULUS_LOG.parent.mkdir(parents=True, exist_ok=True)
    STIMULUS_LOG.write_text(json.dumps(log, indent=2, ensure_ascii=False), encoding='utf-8')
    return len(log)


def stimulate(source: str, stim_type: str = 'action', data: dict | None = None):
    """主动刺激级联：来源 → 学习 → 日志。

    不是"我等待刺激"，而是每次有意义操作后主动调用。
    """
    if data is None:
        data = {}

    total = log_stimulus(source, stim_type, data)
    print("═══ L0 主体刺激 ═══")
    print(f"  来源: {source}")
    print(f"  类型: [{stim_type}]")
    print(f"  累积刺激: {total} 条\n")
    log_behavior('stimulate', {'source': source[:80], 'type': stim_type})

    if stim_type in ('learn', 'conversation'):
        learn(text=source, source=f'{stim_type}:{datetime.now().strftime("%H:%M")}')
    elif stim_type == 'reflect':
        # 反射 → 检查最近动作日志
        actions, breakdown = consume_action_log()
        if actions:
            print(f"  -> 检测到 {actions} 次操作（学习 {breakdown['learn']} / 文件 {breakdown['file']}），管道处理...")
    else:
        print("  -> 已记录（无深度处理）")


# ============================================================
# 召回 (Recall) — 从图谱检索知识到对话上下文
# ============================================================

def recall(topic: str, max_nodes: int = 15, depth: int = 1) -> dict | None:
    """从知识图谱中召回与话题相关的子图。

    做三件事：
    1. 模糊匹配节点（精确 → 子串 → 分词）
    2. BFS 展开邻居（构建子图）
    3. 返回结构化结果：核心概念、关系链、上下文

    Args:
        topic: 搜索话题（中文/英文）
        max_nodes: 最多召回节点数
        depth: BFS 展开深度（1 = 直接邻居）

    Returns:
        {hits, core, context, relations, domains, empty_reason} 或 None
    """
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    label_map = {n['id']: n.get('label', n['id']) for n in nodes}
    group_map = {n['id']: n.get('group', '') for n in nodes}

    # === 1. 多级模糊匹配 ===
    kw = topic.lower().strip()
    keywords = [w for w in re.split(r'[\s,，、/_\-+]+', kw) if len(w) >= 2]
    if not keywords:
        keywords = [kw]

    scored = {}  # nid → (分, 匹配词)
    for n in nodes:
        nid = n['id']
        label = n.get('label', '').lower().strip()
        source = n.get('source', '').lower()
        score = 0
        matched_words = set()

        for w in keywords:
            if len(w) <= 2 and w not in label and w not in source:
                continue
            # 精确命中 label 或 id
            if w == label or w == nid.lower():
                score += 10
                matched_words.add(w)
            # 命中 source 字段（中文名在这里）
            elif w in source:
                score += 8
                matched_words.add(w)
            # 子串
            elif len(w) >= 3 and (w in label or w in nid.lower()):
                score += 3
                matched_words.add(w)
            # label 包含关键词
            elif len(w) >= 2 and w in label:
                score += 2
                matched_words.add(w)
            # 分词反向匹配
            else:
                for token in re.split(r'[\s_\-]+', label):
                    if len(token) >= 4 and len(w) >= 4 and (token in w or w in token):
                        score += 1
                        matched_words.add(w)
                        break

        if score > 0:
            # 降权泛词
            if label in STOP_WORDS_EN:
                score *= 0.1
            if n.get('group') in ('file', 'h1', 'h2', 'h3'):
                score *= 0.5
            scored[nid] = (score, matched_words)

    # === 2. 取 top 作为种子（关键词不足时→向量 fallback）===
    ranked = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)
    seed_ids = set()
    for nid, (s, _) in ranked[:max_nodes]:
        if s >= 2:
            seed_ids.add(nid)

    if not seed_ids:
        # 关键词匹配不足 → 向量搜索（ChromaDB 优先，.npz 回退）
        emb_path = GRAPH_DIR / 'embeddings.npz'
        chroma_path = GRAPH_DIR / 'chroma_db'
        from vectors import (build_embeddings, save_embeddings, load_embeddings,
                             search, VectorStore, encode_query)

        # 确保有最新嵌入
        _vc_id2idx = _vc_embs = _vc_w2i = _vc_comps = None
        cached = load_embeddings(emb_path)
        if cached is not None:
            graph_mtime = GRAPH_JSON.stat().st_mtime if GRAPH_JSON.exists() else 0
            if emb_path.stat().st_mtime >= graph_mtime:
                _vc_id2idx, _vc_embs, _vc_w2i, _vc_comps = cached
        if _vc_id2idx is None:
            _vc_id2idx, _vc_embs, _vc_w2i, _vc_comps = build_embeddings(nodes, edges)
            save_embeddings(emb_path, _vc_id2idx, _vc_embs, _vc_w2i, _vc_comps)

        # 查询向量（优先 ChromaDB）
        vec_results = []
        _chroma_ok = False
        try:
            vs = VectorStore(chroma_path)
            if vs.count() == 0:
                vs.add(_vc_embs, nodes, _vc_id2idx)
            if vs.count() > 0:
                q_emb = encode_query(topic, _vc_w2i, _vc_comps)
                vec_results = vs.search(q_emb, top_k=8)
                _chroma_ok = True
        except Exception:
            pass

        # ChromaDB 不可用 → 用 .npz 和 in-memory search
        if not vec_results:
            vec_results = search(topic, _vc_id2idx, _vc_embs,
                                 label_map, _vc_w2i, _vc_comps, top_k=8)

        if not vec_results:
            log_behavior('recall', {'topic': topic[:60], 'hits': 0}, score=0)
            return None
        scored = {nid: (sim * 5, {topic}) for nid, sim in vec_results}
        ranked = sorted(scored.items(), key=lambda x: x[1][0], reverse=True)
        seed_ids = {nid for nid, (s, _) in ranked[:max_nodes] if s >= 2}

    if not seed_ids:
        return None

    # === 3. BFS 展开 ===
    expanded = set(seed_ids)
    edge_index = defaultdict(list)
    for i, e in enumerate(edges):
        edge_index[e['source']].append(i)
        edge_index[e['target']].append(i)

    for _ in range(depth):
        new_ids = set()
        for nid in expanded:
            for ei in edge_index.get(nid, []):
                e = edges[ei]
                other = e['target'] if e['source'] == nid else e['source']
                if other not in expanded:
                    new_ids.add(other)
        expanded.update(new_ids)
        if len(expanded) >= max_nodes * 3:
            break

    # === 4. 构建子图 ===
    sub_nodes = [n for n in nodes if n['id'] in expanded]
    sub_edges = [e for e in edges
                 if e['source'] in expanded and e['target'] in expanded]

    # 子图内节点度数
    sub_deg = Counter()
    for e in sub_edges:
        sub_deg[e['source']] += 1
        sub_deg[e['target']] += 1

    # === 5. 格式化输出 ===
    result = {'hits': [], 'core': [], 'context': [], 'relations': [], 'domains': set()}

    # 核心命中（种子节点）
    seen_labels = set()
    for nid, (score, mw) in ranked:
        if nid in seed_ids:
            n = next((x for x in sub_nodes if x['id'] == nid), None)
            if n and n.get('label', nid) not in seen_labels:
                seen_labels.add(n.get('label', nid))
                result['hits'].append({
                    'label': n.get('label', nid),
                    'group': n.get('group', ''),
                    'source': n.get('source', ''),
                    'score': round(score, 1),
                    'deg': sub_deg.get(nid, 0),
                })
                result['domains'].add(n.get('group', ''))

    # 关系链
    seen_rels = set()
    for e in sub_edges:
        rel = e.get('relation', '')
        if rel in ('co_occurred_with', 'contains'):
            continue  # 过于通用，跳过
        key = (e['source'], e['target'], rel)
        if key not in seen_rels:
            seen_rels.add(key)
            result['relations'].append({
                'source': label_map.get(e['source'], e['source'])[:40],
                'target': label_map.get(e['target'], e['target'])[:40],
                'relation': rel,
            })

    # 周边相关概念（去噪 + 去重）
    for n in sorted(sub_nodes, key=lambda x: sub_deg.get(x['id'], 0), reverse=True):
        if n['id'] in seed_ids:
            continue
        label = n.get('label', n['id'])
        if label.lower() in STOP_WORDS_EN or len(label) <= 2:
            continue
        if label in seen_labels:
            continue
        seen_labels.add(label)
        result['context'].append({
            'label': label,
            'group': n.get('group', ''),
            'deg': sub_deg.get(n['id'], 0),
        })
        if len(result['context']) >= 10:
            break

    result['domains'] = sorted(result['domains'])

    # === 6. 摘要 ===
    total_nodes = len(result['hits']) + len(result['context'])
    result['_summary'] = (
        f"从图谱中召回了「{topic}」知识子图: "
        f"{len(result['hits'])} 个匹配概念, "
        f"{len(result['relations'])} 条关系，"
        f"{len(result['context'])} 个周边节点"
    )

    log_behavior('recall', {'topic': topic[:60], 'hits': len(result['hits']),
                            'relations': len(result['relations']),
                            'context': len(result['context'])},
                 score=len(result['hits']))
    # 发射事件
    try:
        bus = _ensure_eventbus()
        if bus:
            from protoskill import Event
            bus.emit(Event('recall:complete', 'recall', {
                'topic': topic, 'hits': len(result['hits'])
            }))
    except Exception:
        pass
    return result


def recall_text(topic: str, max_nodes: int = 15, depth: int = 1) -> str | None:
    """召回并格式化为 Markdown 文本，直接注入对话。"""
    result = recall(topic, max_nodes, depth)
    if not result:
        return None

    # 过滤噪声概念（单英文词 ≤ 3 字且是停用词/泛词）
    def is_noise(label: str) -> bool:
        ll = label.lower().strip()
        if len(ll) <= 2:
            return True
        if len(ll) <= 3 and ll in STOP_WORDS_EN:
            return True
        # 单英文词 ≥4 但无信息量（首字母小写+泛词）
        ll_no_punct = re.sub(r'[^a-z]', '', ll)
        if len(ll_no_punct) >= 4 and ll_no_punct == ll and ll in STOP_WORDS_EN:
            return True
        return False

    # 判断是否有实质内容：多词短语、专名（首字母大写）、中文
    def is_meaningful(label: str) -> bool:
        if is_noise(label):
            return False
        ll = label.strip()
        if not ll:
            return False
        # 多词
        if ' ' in ll:
            return True
        # 首字母大写（可能是专名）
        if ll[0].isupper():
            return True
        # 含中文
        if any('一' <= c <= '鿿' for c in ll):
            return True
        return False

    lines = []
    lines.append(f"> **图谱知识**: {topic}")

    # 核心概念：多词/专名优先，单英文词垫底
    seen = set()
    multi_word = []
    proper_noun = []
    single_word = []
    for h in result['hits']:
        label = h.get('label', '')
        if label.lower() in seen:
            continue
        seen.add(label.lower())
        if not is_meaningful(label):
            continue
        if ' ' in label:
            multi_word.append(h)
        elif label[0].isupper():
            proper_noun.append(h)
        else:
            single_word.append(h)

    hits_clean = multi_word + proper_noun + single_word
    if hits_clean:
        lines.append("> **相关:**")
        for h in hits_clean[:5]:
            lines.append(f"> - {h['label']} [{h['group']}]")
        lines.append("")

    # 关系链
    if result['relations']:
        lines.append("> **关系:**")
        for r in result['relations'][:5]:
            lines.append(f"> - {r['source']} → {r['target']} ({r['relation']})")
        lines.append("")

    # 周边概念（去噪去重）
    seen_context = set()
    context_clean = []
    for c in result['context']:
        label = c.get('label', '')
        if label.lower() in seen_context or not is_meaningful(label):
            continue
        seen_context.add(label.lower())
        context_clean.append(c)
    if context_clean:
        lines.append("> **延伸:**")
        for c in context_clean[:4]:
            lines.append(f"> - {c['label']} [{c['group']}]")

    return '\n'.join(lines).strip()


# ============================================================
# 自我进化系统 — 行为日志 / 诊断 / 改进建议
# ============================================================
from evolution import (log_behavior, analyze_behavior, diagnose,
                       suggest_improvements, append_evolution_log)


# ============================================================
# HTML 可视化导出
# ============================================================

def export_html():
    """导出交互式知识图谱可视化。"""
    graph = load_graph()
    nodes = graph.get('nodes', [])
    edges = graph.get('edges', [])

    degree = Counter()
    for e in edges:
        degree[e['source']] += 1
        degree[e['target']] += 1
    max_deg = max(degree.values()) if degree else 1

    COLOR_PALETTE = {
        'file': ('#4a5a7a', '#6a8aba'),
        'h1': ('#7a6a5a', '#9a8a7a'),
        'h2': ('#7a6a5a', '#9a8a7a'),
        'h3': ('#7a6a5a', '#9a8a7a'),
        'concept': ('#3a7a6a', '#5aaa8a'),
        'mechanism': ('#b07a3a', '#d09a5a'),
        'method': ('#a05a6a', '#c07a8a'),
        'principle': ('#7a5a8a', '#9a7aaa'),
        'architecture': ('#3a7a8a', '#5a9aaa'),
        'capability': ('#4a8a5a', '#6aaa7a'),
        'limitation': ('#a06a5a', '#c08a7a'),
        'pattern': ('#8a6a8a', '#aa8aaa'),
        'rationale': ('#8a7a5a', '#aa9a7a'),
        'code': ('#4a7a5a', '#6aaa7a'),
        'conversation': ('#c07a3a', '#e09a5a'),
    }

    ZONE_MAP = [
        ('知识区', ['concept', 'mechanism', 'principle', 'rationale', 'pattern'], '#3a7a6a'),
        ('方法区', ['method', 'step', 'pipeline', 'protocol', 'process'], '#b07a3a'),
        ('架构区', ['architecture', 'capability', 'limitation', 'tool', 'code'], '#3a7a8a'),
        ('元认知区', ['test', 'constraint', 'check', 'metric'], '#7a5a8a'),
        ('源文件', ['file', 'h1', 'h2', 'h3'], '#4a5a7a'),
        ('对话区', ['conversation'], '#c07a3a'),
        ('其他', [], '#5a5a6a'),
    ]

    GROUP_CN = {
        'file': '源文件', 'h1': '一级标题', 'h2': '二级标题', 'h3': '三级标题',
        'concept': '概念', 'mechanism': '机制', 'method': '方法',
        'principle': '原则', 'architecture': '架构', 'capability': '能力',
        'limitation': '局限', 'pattern': '模式', 'rationale': '设计理念',
        'code': '代码', 'step': '步骤', 'pipeline': '管道', 'test': '测试',
        'constraint': '约束', 'check': '检查', 'metric': '指标',
        'tool': '工具', 'protocol': '协议', 'process': '流程',
        'conversation': '对话学习',
    }

    zone_counts = {z[0]: 0 for z in ZONE_MAP}
    for n in nodes:
        g = n.get('group', '')
        for zname, zgroups, _ in ZONE_MAP:
            if g in zgroups:
                zone_counts[zname] += 1
                break
        else:
            zone_counts['其他'] += 1
    max_zone = max(zone_counts.values()) if zone_counts else 1

    html_nodes = []
    for n in nodes:
        g = n.get('group', '')
        bg, border = COLOR_PALETTE.get(g, ('#5a5a6a', '#7a7a8a'))
        sz = 6 + (degree.get(n['id'], 0) / max_deg) * 28
        if g == 'file':
            sz = max(sz, 22)
        if g == 'conversation':
            sz = max(sz, 14)
        html_nodes.append({
            'id': n['id'], 'label': n.get('label', n['id'])[:60],
            'color': {'background': bg, 'border': border,
                      'highlight': {'background': border, 'border': '#ffffff'},
                      'hover': {'background': border, 'border': '#ffffff'}},
            'size': round(max(sz, 5), 1),
            'group': g,
            'source': n.get('source', ''),
            'by': n.get('extracted_by', ''),
            'degree': degree.get(n['id'], 0),
        })

    html_edges = []
    for e in edges:
        is_llm = e.get('type') in ('semantic', 'inferred')
        html_edges.append({
            'from': e['source'], 'to': e['target'],
            'label': e.get('relation', '')[:30],
            'dashes': is_llm,
            'width': 1.2,
            'color': {'color': 'rgba(255,255,255,0.08)',
                      'highlight': 'rgba(255,255,255,0.25)',
                      'hover': 'rgba(255,255,255,0.2)'},
            'title': f"{e.get('relation','')} [{e.get('type','structural')}]",
            'smooth': {'type': 'continuous'},
        })

    groups_used = sorted({n.get('group', '') for n in nodes if n.get('group', '')})
    groups_json = json.dumps({g: {'color': {'background': COLOR_PALETTE.get(g, ('#5a5a6a', '#7a7a8a'))[0],
                                             'border': COLOR_PALETTE.get(g, ('#5a5a6a', '#7a7a8a'))[1]}}
                              for g in groups_used})

    template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>二弟知识图谱</title>
<script src="https://unpkg.com/vis-network@9.1.9/standalone/umd/vis-network.min.js"></script>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ background:#0d0d1a; color:#c8c8d0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Noto Sans SC",sans-serif; overflow:hidden; height:100vh; }}
  #graph {{ width:100vw; height:100vh; }}
  .card {{ position:fixed; background:rgba(18,18,30,0.92); backdrop-filter:blur(16px); border:1px solid rgba(255,255,255,0.06); border-radius:12px; padding:16px; color:#b0b0c0; font-size:13px; line-height:1.5; z-index:10; }}
  #search {{ top:20px; left:20px; width:260px; z-index:20; }}
  #search input {{ width:100%; background:rgba(255,255,255,0.06); border:1px solid rgba(255,255,255,0.08); border-radius:8px; padding:8px 12px; color:#e0e0f0; font-size:13px; outline:none; }}
  #search input:focus {{ border-color:rgba(255,255,255,0.2); }}
  #search-results {{ margin-top:6px; max-height:200px; overflow-y:auto; display:none; }}
  #search-results div {{ padding:4px 8px; border-radius:4px; cursor:pointer; font-size:12px; }}
  #search-results div:hover {{ background:rgba(255,255,255,0.06); }}
  .no-match {{ color:#666; font-size:11px; padding:4px 8px; }}
  #detail {{ top:80px; right:-320px; width:300px; max-height:calc(100vh - 160px); overflow-y:auto; transition:right 0.3s cubic-bezier(0.16,1,0.3,1); padding:16px 18px; }}
  #detail.visible {{ right:24px; }}
  #detail h4 {{ font-size:15px; color:#e0e0f0; margin-bottom:4px; font-weight:500; }}
  #detail .meta {{ font-size:11px; color:#666; margin-bottom:10px; }}
  #detail .conn {{ font-size:12px; padding:3px 0; border-bottom:1px solid rgba(255,255,255,0.04); display:flex; justify-content:space-between; }}
  #detail .conn .rel {{ color:#888; }}
  #detail .conn .tgt {{ color:#b0b0c0; }}
  #stats {{ bottom:24px; right:24px; text-align:right; font-size:11px; color:#555; padding:10px 14px; }}
  #legend {{ position:fixed; top:50%; left:-220px; transform:translateY(-50%); width:200px; max-height:70vh; overflow-y:auto; font-size:11px; padding:14px; transition:left 0.3s cubic-bezier(0.16,1,0.3,1); z-index:14; }}
  #legend.open {{ left:24px; }}
  #legend .dot {{ display:inline-block; width:8px; height:8px; border-radius:50%; margin-right:6px; }}
  #legend .zone-header {{ margin-top:5px; margin-bottom:2px; color:#888; font-size:9px; letter-spacing:0.3px; }}
  .badge {{ display:inline-block; padding:0 6px; border-radius:4px; font-size:10px; margin-right:4px; background:rgba(255,255,255,0.06); color:#888; }}
  @media (max-width:640px) {{ #search {{ width:180px; }} #detail {{ width:240px; }} }}
</style>
</head>
<body>
<div id="graph"></div>
<div id="search" class="card">
  <input id="search-input" type="text" placeholder="搜索节点..." autocomplete="off">
  <div id="search-results"></div>
</div>
<div id="detail" class="card">
  <h4 id="dl-label" style="margin:0 0 4px;">Node</h4>
  <div class="meta"><span id="dl-source" class="badge">source</span></div>
  <div id="dl-connections"></div>
</div>
<div id="stats" class="card">
  <div style="display:flex;gap:16px;align-items:center;">
    <div style="text-align:center;"><div style="font-size:22px;font-weight:300;color:#e0e0f0;">{len(nodes)}</div><div style="color:#666;font-size:9px;">节点</div></div>
    <div style="width:1px;height:28px;background:rgba(255,255,255,0.06);"></div>
    <div style="text-align:center;"><div style="font-size:22px;font-weight:300;color:#e0e0f0;">{len(edges)}</div><div style="color:#666;font-size:9px;">突触</div></div>
    <div style="width:1px;height:28px;background:rgba(255,255,255,0.06);"></div>
    <div style="text-align:center;"><div style="font-size:22px;font-weight:300;color:#e0e0f0;">{round(len(edges)/max(len(nodes),1), 1)}</div><div style="color:#666;font-size:9px;">密度</div></div>
  </div>
</div>
<div style="position:fixed;top:20px;right:24px;z-index:20;display:flex;gap:4px;">
  <button onclick="network.fit({{animation:{{duration:300}}}})" style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:6px;color:#888;width:30px;height:30px;cursor:pointer;">⊞</button>
  <button onclick="document.getElementById('legend').classList.toggle('open')" style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.06);border-radius:6px;color:#888;width:30px;height:30px;cursor:pointer;">☰</button>
</div>
<div id="legend" class="card">
  {''.join(f'<div class="zone-header" style="color:#aaa;">{zname}</div>' +
    ''.join(f'<div style="padding-left:6px;"><span class="dot" style="background:{COLOR_PALETTE.get(g, ("#5a5a6a","#7a7a8a"))[0]}"></span>{GROUP_CN.get(g, g)}</div>'
      for g in zgroups if g in groups_used)
    for zname, zgroups, _ in ZONE_MAP if any(g in groups_used for g in zgroups))}
  <div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.04);font-size:10px;">
    <span style="display:inline-block;width:16px;height:0;border-top:1.5px dashed rgba(255,255,255,0.2);vertical-align:middle;margin-right:4px;"></span> 推理
    <span style="display:inline-block;width:16px;height:0;border-top:1.5px solid rgba(255,255,255,0.15);vertical-align:middle;margin-left:10px;margin-right:4px;"></span> 结构
  </div>
</div>
<script>
const nodes = new vis.DataSet({json.dumps(html_nodes)});
const edges = new vis.DataSet({json.dumps(html_edges)});
const options = {{
  physics: {{ enabled:true, solver:'forceAtlas2Based', forceAtlas2Based:{{ gravitationalConstant:-120, centralGravity:0.01, springLength:80, springConstant:0.08, damping:0.5 }}, stabilization:{{ iterations:300 }} }},
  nodes: {{ shape:'dot', borderWidth:1.2, font:{{ size:9, color:'#888', strokeWidth:0 }}, scaling:{{ min:5, max:30 }} }},
  edges: {{ font:{{ size:8, color:'#555', strokeWidth:0 }}, arrows:{{ to:{{ enabled:true, scaleFactor:0.4, type:'arrow' }} }} }},
  interaction: {{ hover:true, tooltipDelay:200, hideEdgesOnDrag:true }},
  groups: {groups_json}
}};
const network = new vis.Network(document.getElementById('graph'), {{nodes,edges}}, options);
network.once('stabilizationIterationsDone', () => network.setOptions({{physics:{{enabled:false}}}}));
network.on('click', p => {{
  if (!p.nodes.length) return;
  const n = nodes.get(p.nodes[0]);
  document.getElementById('dl-label').textContent = n.label || n.id;
  document.getElementById('dl-source').textContent = n.source || '';
  const conns = network.getConnectedNodes(p.nodes[0]);
  document.getElementById('dl-connections').innerHTML = conns.length
    ? conns.slice(0, 30).map(id => {{ const nb = nodes.get(id); return nb ? `<div class="conn"><span class="tgt">${{nb.label||nb.id}}</span></div>` : ''; }}).join('')
    : '<div style="color:#555;">无连接</div>';
  document.getElementById('detail').classList.add('visible');
}});
document.addEventListener('click', e => {{
  if (!e.target.closest('#detail')) document.getElementById('detail').classList.remove('visible');
}});
// search
document.getElementById('search-input').oninput = function() {{
  const q = this.value.trim().toLowerCase();
  if (!q) {{ document.getElementById('search-results').style.display = 'none'; return; }}
  const all = nodes.get();
  const matches = all.filter(n => (n.label||'').toLowerCase().includes(q) || n.id.includes(q));
  const el = document.getElementById('search-results');
  el.innerHTML = matches.length
    ? matches.slice(0, 20).map(n => `<div onclick="network.focus('${{n.id}}',{{scale:1.5,animation:{{duration:300}}}});document.getElementById('detail').classList.remove('visible');this.blur();el.style.display='none'">${{n.label||n.id}}</div>`).join('')
    : '<div class="no-match">无匹配</div>';
  el.style.display = 'block';
}};
</script>
</body>
</html>"""
    (GRAPH_DIR / 'graph.html').write_text(template, encoding='utf-8')
    print(f"  HTML: {len(nodes)} 节点, {len(edges)} 边")


# ============================================================
# 查询
# ============================================================

def query(keyword):
    """查询图谱：关键词匹配节点，显示关联子图。"""
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    kw = keyword.lower()
    matched = []
    for n in nodes:
        label = n.get('label', '').lower()
        nid = n['id'].lower()
        if kw in label or kw in nid:
            matched.append(n)

    if not matched:
        print(f"没有找到匹配 '{keyword}' 的节点")
        return

    matched_ids = {n['id'] for n in matched}
    print(f"\n匹配节点 ({len(matched)}):")
    for n in matched:
        print(f"  [{n.get('group', '?')}] {n.get('label', n['id'])[:60]}")

    # 子图边
    sub_edges = [e for e in edges
                 if e['source'] in matched_ids or e['target'] in matched_ids]
    if sub_edges:
        label_map = {n['id']: n.get('label', n['id']) for n in nodes}
        print(f"\n关联边 ({len(sub_edges)}):")
        for e in sub_edges[:20]:
            s = label_map.get(e['source'], e['source'])[:35]
            t = label_map.get(e['target'], e['target'])[:35]
            print(f"  {s:35s} → {t:35s} ({e.get('relation', '?')})")
        if len(sub_edges) > 20:
            print(f"  ... 还有 {len(sub_edges) - 20} 条边")


# ============================================================
# 状态
# ============================================================

def status():
    """显示当前图谱状态。"""
    graph = load_graph()
    nodes = graph['nodes']
    edges = graph['edges']

    print("═══ 知识图谱状态 ═══\n")
    print(f"节点: {len(nodes)}")
    print(f"边:   {len(edges)}")
    print(f"构建: {graph.get('built_at', 'N/A')}\n")

    groups = Counter(n.get('group', 'unknown') for n in nodes)
    print("节点分组:")
    for g, c in groups.most_common():
        print(f"  {g}: {c}")

    rels = Counter(e.get('relation', 'unknown') for e in edges)
    print("\n边关系类型:")
    for r, c in rels.most_common(10):
        print(f"  {r}: {c}")

    degree = Counter()
    for e in edges:
        degree[e['source']] += 1
        degree[e['target']] += 1
    print("\n枢纽概念 (Top 10):")
    for nid, deg in degree.most_common(10):
        label = next((n.get('label', nid) for n in nodes if n['id'] == nid), nid)
        print(f"  {label[:45]:45s} deg={deg}")


# ============================================================
# 主入口
# ============================================================

def main():
    try:
        _main_impl()
    except Exception as e:
        print(f"\n[ERR] 命令执行异常: {e}")
        import traceback
        traceback.print_exc()


def _main_impl():
    if len(sys.argv) < 2:
        print(__doc__)
        return

    cmd = sys.argv[1]

    if cmd == 'status':
        status()
    elif cmd == 'collect':
        changed, unchanged = collect()
        print(f"Changed: {len(changed)}, Unchanged: {len(unchanged)}")
        for fname, change_type in changed:
            print(f"  [{change_type}] {fname}")
    elif cmd == 'full':
        run_pipeline(start_step=1)
    elif cmd == 'pipeline':
        step = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        run_pipeline(start_step=step)
    elif cmd == 'rebuild':
        # 备份当前 graph.json
        if GRAPH_JSON.exists():
            shutil.copy2(str(GRAPH_JSON), str(GRAPH_JSON) + '.pre_rebuild')
        # 清空并全量
        save_graph({'nodes': [], 'edges': [], 'built_at': None})
        run_pipeline(start_step=1)
    elif cmd == 'query':
        kw = ' '.join(sys.argv[1:]) if len(sys.argv) > 2 else ''
        if not kw:
            kw = cmd
        # query 命令是 "python kg.py query <关键词>"
        if len(sys.argv) > 2:
            query(' '.join(sys.argv[2:]))
        else:
            print("用法: python knowledge_graph.py query <关键词>")
    elif cmd == 'distill':
        pruned, orphans = distill()
        print(f"Pruned {pruned} edges, removed {orphans} orphans")
    elif cmd == 'self':
        result = self_awareness()
        if not result:
            print("没有新动作或变更")
    elif cmd == 'invoke':
        count = invoke()
        print(f"Invoke: wrote {count} memory files")
    elif cmd == 'cross-ref':
        new = cross_reference()
        print(f"Added {new} cross-references")
    elif cmd == 'learn':
        text = ' '.join(sys.argv[2:])
        if not text:
            print("用法: python knowledge_graph.py learn <文本>")
        else:
            learn(text, source='cli')
    elif cmd == 'stimulate':
        src = sys.argv[2] if len(sys.argv) > 2 else 'cli'
        st = sys.argv[3] if len(sys.argv) > 3 else 'action'
        stimulate(src, st)
    elif cmd == 'html':
        export_html()
    elif cmd == 'clean-conversation':
        n, e = clean_conversation()
        print(f"clean-conversation: removed {n} nodes, {e} edges")
    elif cmd == 'trim-cooccurrence':
        r = trim_cooccurrence()
        print(f"trim-cooccurrence: removed {r} edges")
    elif cmd == 'recall':
        args = sys.argv[2:]
        use_vector = '--vector' in args
        topic = ' '.join(a for a in args if not a.startswith('--'))
        if not topic:
            print("用法: python knowledge_graph.py recall <话题> [--vector]")
        else:
            if use_vector:
                from vectors import build_embeddings, search
                graph = load_graph()
                id_to_idx, embs, w2i, comps = build_embeddings(graph['nodes'], graph['edges'])
                label_map = {n['id']: n.get('label', n['id']) for n in graph['nodes']}
                results = search(topic, id_to_idx, embs, label_map, w2i, comps, top_k=10)
                if results:
                    print(f">> **向量搜索**: {topic}\n")
                    for nid, sim in results:
                        label = label_map.get(nid, nid)
                        group = next((n.get('group', '') for n in graph['nodes'] if n['id'] == nid), '')
                        print(f"  - {label} [{group}] (sim={sim:.3f})")
                else:
                    print(f"向量搜索未找到与「{topic}」相关的知识")
            else:
                result = recall_text(topic)
                if result:
                    print(result)
                else:
                    print(f"图谱中未找到与「{topic}」相关的知识")
    elif cmd == 'diagnose':
        findings = diagnose()
        if findings:
            print("═══ 自我诊断报告 ═══\n")
            for issue_id, desc, severity in findings:
                bar = '█' * severity + '░' * (10 - severity)
                print(f"  [{bar}] ({severity}/10) {desc}")
            print("\n改进方案:")
            for s in suggest_improvements(findings):
                print(f"  ▶ {s}")
        else:
            print("自我诊断: 未发现问题")
    elif cmd == 'analyze':
        n = int(sys.argv[2]) if len(sys.argv) > 2 else 50
        print(analyze_behavior(n))
    elif cmd == 'evolution-log':
        entry = ' '.join(sys.argv[2:])
        if entry:
            append_evolution_log(entry)
            print("已记录到进化日志")
        else:
            log_path = EVOLUTION_LOG
            if log_path.exists():
                print(log_path.read_text(encoding='utf-8')[-2000:])
            else:
                print("进化日志为空")
    else:
        print(f"未知命令: {cmd}")
        print(__doc__)


if __name__ == '__main__':
    main()
