"""recall_enhancer — 自动补充召回结果。

监听 recall:complete 事件，如果命中太少（< 3），
自动触发生成向量 + ChromaDB 搜索补充结果。

这是一个真正的"技能"：事件驱动、可热替换、有状态。
"""

SKILL_NAME = "recall_enhancer"
SKILL_DESCRIPTION = "自动向量补充：recall 命中不足时触发 ChromaDB 搜索"
SKILL_VERSION = "0.1.0"
SKILL_TRIGGERS = ["recall:complete"]

import sys
from pathlib import Path

# 确保可导入父目录模块
SKILL_DIR = Path(__file__).resolve().parent
GRAPH_DIR = SKILL_DIR.parent
if str(GRAPH_DIR) not in sys.path:
    sys.path.insert(0, str(GRAPH_DIR))


# 技能状态（on_activate 时初始化，on_deactivate 时清理）
_history: dict[str, int] = {}


def on_activate(bus):
    """技能激活时注册事件处理器。"""
    bus.on('recall:complete', _on_recall_complete)


def on_deactivate(bus):
    """技能停用时清理。"""
    _history.clear()


def on_event(event):
    """处理事件（备选入口，非 EventBus 回调时用）。"""
    if event.type == 'recall:complete':
        return _on_recall_complete(event)
    return None


def _on_recall_complete(event):
    """当 recall 命中太少时，自动补充向量搜索结果。"""
    topic = event.data.get('topic', '')
    hits = event.data.get('hits', 0)
    if hits >= 3:
        # 命中够多，无需补充
        _history[topic] = hits
        return None

    print(f"  [skill:recall_enhancer] recall('{topic}') 仅 {hits} 命中，尝试向量补充...")

    try:
        from knowledge_graph import load_graph
        from vectors import (build_embeddings, save_embeddings, load_embeddings,
                             VectorStore, encode_query, search)

        graph = load_graph()
        nodes, edges = graph['nodes'], graph['edges']
        label_map = {n['id']: n.get('label', n['id']) for n in nodes}

        emb_path = GRAPH_DIR / 'embeddings.npz'
        chroma_path = GRAPH_DIR / 'chroma_db'

        # 确保有嵌入
        cached = load_embeddings(emb_path)
        if cached:
            _id2idx, _embs, _w2i, _comps = cached
        else:
            _id2idx, _embs, _w2i, _comps = build_embeddings(nodes, edges)
            save_embeddings(emb_path, _id2idx, _embs, _w2i, _comps)

        # 尝试 ChromaDB 搜索
        results = []
        try:
            vs = VectorStore(chroma_path)
            if vs.count() == 0:
                vs.add(_embs, nodes, _id2idx)
            q_emb = encode_query(topic, _w2i, _comps)
            results = vs.search(q_emb, top_k=8)
        except Exception:
            pass

        # 回退到 in-memory 搜索
        if not results:
            q_emb = encode_query(topic, _w2i, _comps)
            results = search(topic, _id2idx, _embs, label_map, _w2i, _comps, top_k=8)

        if results:
            _history[topic] = len(results)
            print(f"  [skill:recall_enhancer] 向量补充找到 {len(results)} 个结果")
            return {'supplement': True, 'count': len(results), 'results': results}

        print(f"  [skill:recall_enhancer] 向量补充未找到新结果")
        return {'supplement': False, 'count': 0, 'results': []}

    except Exception as e:
        print(f"  [skill:recall_enhancer] 错误: {e}")
        return None
