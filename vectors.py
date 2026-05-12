"""基于 numpy 的语义向量搜索。

从图谱结构构建共现嵌入，不依赖外部 API。
用于 recall() 的关键词匹配 fallback。
"""

import re
from collections import defaultdict

import numpy as np

from pathlib import Path

from const import STOP_WORDS_EN


def _tokenize(text: str) -> list[str]:
    """分词：提取字母词 + 中文二元组，去停用词。"""
    tokens = []
    # 英文词（至少 2 字母）
    for w in re.findall(r'[a-zA-Z]\w+', text.lower()):
        if len(w) >= 2 and w not in STOP_WORDS_EN:
            tokens.append(w)
    # 中文：连续汉字的二元组
    for chunk in re.findall(r'[一-鿿]+', text):
        if len(chunk) >= 2:
            tokens.append(chunk)  # 整词
        for i in range(len(chunk) - 1):
            tokens.append(chunk[i:i+2])  # 二元组
    return tokens


def build_embeddings(nodes: list[dict], edges: list[dict], dim: int = 64):
    """从图谱结构构建节点嵌入。

    每个节点的向量 = 自身标签词频 × 2 + 所有邻居标签词频
    然后用 SVD 降维到 dim 维。

    Returns:
        id_to_idx: {node_id: int} 映射
        node_embs: np.ndarray (N, dim) 归一化嵌入
        vocab: {word: idx} 词表
        components: np.ndarray (dim, V) SVD 右奇异向量，用于编码查询
    """
    # 收集词表
    vocab: set[str] = set()
    label_map: dict[str, str] = {}
    for n in nodes:
        label = n.get('label', '') or ''
        label_map[n['id']] = label
        vocab.update(_tokenize(label))

    if not vocab:
        return {}, np.empty((0, 0)), {}, np.empty((0, 0))

    word_to_idx = {w: i for i, w in enumerate(vocab)}
    V = len(vocab)
    N = len(nodes)

    # 邻域
    neighbors: dict[str, set[str]] = defaultdict(set)
    for e in edges:
        neighbors[e['source']].add(e['target'])
        neighbors[e['target']].add(e['source'])

    # 构建词频矩阵 (N × V)
    matrix = np.zeros((N, V), dtype=np.float32)
    for i, n in enumerate(nodes):
        nid = n['id']
        for w in _tokenize(label_map.get(nid, '')):
            if w in word_to_idx:
                matrix[i, word_to_idx[w]] += 2.0  # 自身加权
        for nbr_id in neighbors.get(nid, set()):
            for w in _tokenize(label_map.get(nbr_id, '')):
                if w in word_to_idx:
                    matrix[i, word_to_idx[w]] += 1.0

    # L2 归一化
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1
    matrix = matrix / norms

    # SVD 降维
    U, S, Vt = np.linalg.svd(matrix, full_matrices=False)
    k = min(dim, N, V)
    node_embs = U[:, :k] * S[:k]

    id_to_idx = {n['id']: i for i, n in enumerate(nodes)}
    return id_to_idx, node_embs, word_to_idx, Vt[:k]


def encode_query(query: str, word_to_idx: dict, components: np.ndarray) -> np.ndarray:
    """将查询编码到嵌入空间。

    1. 分词 → 词袋向量
    2. 投影到 SVD 空间: q_emb = q_vec @ components.T
    3. L2 归一化
    """
    V = len(word_to_idx)
    q_vec = np.zeros(V, dtype=np.float32)
    for w in _tokenize(query):
        if w in word_to_idx:
            q_vec[word_to_idx[w]] += 1.0
    norm = np.linalg.norm(q_vec)
    if norm == 0:
        return np.zeros(components.shape[0], dtype=np.float32)
    q_vec = q_vec / norm
    q_emb = q_vec @ components.T
    q_norm = np.linalg.norm(q_emb)
    if q_norm > 0:
        q_emb = q_emb / q_norm
    return q_emb


def search(query: str, id_to_idx: dict, node_embs: np.ndarray,
           label_map: dict[str, str], word_to_idx: dict, components: np.ndarray,
           top_k: int = 10, min_sim: float = 0.1) -> list[tuple[str, float]]:
    """搜索语义最相似的节点。

    Returns:
        [(node_id, similarity), ...] 按相似度降序
    """
    if not id_to_idx or node_embs.size == 0:
        return []

    q_emb = encode_query(query, word_to_idx, components)
    if np.linalg.norm(q_emb) == 0:
        return []

    # 余弦相似度（向量已归一化，dot = cos）
    sims = node_embs @ q_emb

    # 收集结果
    idx_to_id = {v: k for k, v in id_to_idx.items()}
    results = []
    for idx in np.argsort(-sims):
        sim = float(sims[idx])
        if sim < min_sim:
            break
        nid = idx_to_id[idx]
        # 不要返回无意义的短标签
        label = label_map.get(nid, '')
        if len(label) <= 2:
            continue
        results.append((nid, sim))
        if len(results) >= top_k:
            break

    return results


def hybrid_search(query: str, keyword_scored: dict, id_to_idx: dict,
                  node_embs: np.ndarray, label_map: dict[str, str],
                  word_to_idx: dict, components: np.ndarray,
                  top_k: int = 10, alpha: float = 0.4) -> list[tuple[str, float]]:
    """混合关键词 + 向量搜索。

    score = alpha * vector_sim + (1 - alpha) * keyword_score

    Args:
        keyword_scored: {nid: (keyword_score, matched_words)}
        alpha: 向量相似度权重
    """
    if not id_to_idx or node_embs.size == 0:
        return []

    q_emb = encode_query(query, word_to_idx, components)
    if np.linalg.norm(q_emb) == 0:
        return []

    sims = node_embs @ q_emb
    idx_to_id = {v: k for k, v in id_to_idx.items()}

    # 归一化关键词分数到 [0, 1]
    kw_scores = {}
    if keyword_scored:
        max_kw = max(s for s, _ in keyword_scored.values()) or 1
        for nid, (s, _) in keyword_scored.items():
            kw_scores[nid] = s / max_kw

    results = []
    for idx in np.argsort(-sims)[:top_k * 3]:
        nid = idx_to_id[idx]
        vec_sim = float(sims[idx])
        if vec_sim < 0.05:
            break
        kw_score = kw_scores.get(nid, 0)
        combined = alpha * vec_sim + (1 - alpha) * kw_score
        results.append((nid, combined))

    results.sort(key=lambda x: x[1], reverse=True)
    return results[:top_k]


class VectorStore:
    """ChromaDB 封装的向量存储。

    替代 .npz 文件缓存，支持元数据过滤和持久化。

    用法:
        vs = VectorStore(GRAPH_DIR / 'chroma_db')
        vs.add(node_embs, nodes, id_to_idx)
        results = vs.search(query_emb, top_k=10, filter={'group': 'agent'})
    """

    def __init__(self, path: str | Path):
        self.path = str(path)
        self._client = None
        self._collection = None

    def _ensure(self):
        if self._client is None:
            import chromadb
            self._client = chromadb.PersistentClient(self.path)
            self._collection = self._client.get_or_create_collection(
                'graph_embeddings',
                metadata={'hnsw:space': 'cosine'},
            )

    @property
    def collection(self):
        self._ensure()
        return self._collection

    @property
    def client(self):
        self._ensure()
        return self._client

    def add(self, node_embs: np.ndarray, nodes: list[dict],
            id_to_idx: dict[str, int]) -> int:
        """将节点嵌入存入 ChromaDB。

        Args:
            node_embs: (N, dim) 归一化嵌入
            nodes: 节点列表，每个必须有 'id'
            id_to_idx: {node_id: idx} 映射

        Returns:
            存入的向量数
        """
        self.collection  # ensure
        if node_embs.size == 0:
            return 0

        ids = []
        embeddings = []
        metadatas = []
        documents = []

        for n in nodes:
            nid = n['id']
            idx = id_to_idx.get(nid)
            if idx is None or idx >= len(node_embs):
                continue
            ids.append(nid)
            embeddings.append(node_embs[idx].tolist())
            metadatas.append({
                'group': n.get('group', ''),
                'source': n.get('source', '')[:200],
            })
            documents.append(n.get('label', nid))

        # 清空并重写
        try:
            self.collection.delete(where={})
        except Exception:
            pass  # 空集合首次 delete 可能报错
        if ids:
            self.collection.add(ids=ids, embeddings=embeddings,
                                metadatas=metadatas, documents=documents)
        return len(ids)

    def search(self, query_emb: np.ndarray, top_k: int = 10,
               where: dict | None = None) -> list[tuple[str, float]]:
        """向量搜索，支持元数据过滤。

        Returns:
            [(node_id, similarity), ...]
        """
        if np.linalg.norm(query_emb) == 0 or query_emb.ndim == 0:
            return []
        q = query_emb.reshape(1, -1).tolist()
        try:
            results = self.collection.query(
                query_embeddings=q,
                n_results=top_k,
                where=where,
            )
        except Exception:
            return []

        ids = results.get('ids', [[]])[0]
        dists = results.get('distances', [[]])[0]
        # ChromaDB 余弦距离 = 1 - cos_sim
        return [(nid, float(1 - d)) for nid, d in zip(ids, dists) if float(1 - d) >= 0.05]

    def count(self) -> int:
        try:
            return self.collection.count()
        except Exception:
            return 0

    def delete(self, ids: list[str] | None = None):
        """删除指定 id 的向量，不传则清空。"""
        if ids:
            self.collection.delete(ids=ids)
        else:
            try:
                self.collection.delete(where={})
            except Exception:
                pass

    def close(self):
        self._client = None
        self._collection = None


def save_embeddings(path, id_to_idx, node_embs, word_to_idx, components):
    """持久化嵌入到 .npz 文件。"""
    if not id_to_idx:
        return False
    import numpy as np
    id_keys = list(id_to_idx.keys())
    id_vals = np.array([id_to_idx[k] for k in id_keys], dtype=np.int32)
    w_keys = list(word_to_idx.keys())
    w_vals = np.array([word_to_idx[k] for k in w_keys], dtype=np.int32)
    np.savez_compressed(
        path,
        id_keys=np.array(id_keys, dtype=object),
        id_vals=id_vals,
        node_embs=node_embs,
        w_keys=np.array(w_keys, dtype=object),
        w_vals=w_vals,
        components=components,
    )
    return True


def load_embeddings(path):
    """从 .npz 恢复嵌入。返回 (id_to_idx, node_embs, word_to_idx, components) 或 None。"""
    if not path.exists():
        return None
    try:
        import numpy as np
        data = np.load(path, allow_pickle=True)
        id_to_idx = {str(k): int(v) for k, v in zip(data['id_keys'], data['id_vals'])}
        word_to_idx = {str(k): int(v) for k, v in zip(data['w_keys'], data['w_vals'])}
        return id_to_idx, data['node_embs'], word_to_idx, data['components']
    except Exception:
        return None
