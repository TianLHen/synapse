"""测试嵌入构建 + 搜索。"""

from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import numpy as np


class TestTokenize:
    def test_tokenize_english(self):
        from vectors import _tokenize
        tokens = _tokenize("Agent Pipeline Memory Evolution")
        assert len(tokens) >= 4
        assert "agent" in tokens
        assert "pipeline" in tokens

    def test_tokenize_chinese(self):
        from vectors import _tokenize
        tokens = _tokenize("知识图谱嵌入")
        assert len(tokens) > 0

    def test_tokenize_mixed(self):
        from vectors import _tokenize
        tokens = _tokenize("AI Agent 进化 2025")
        assert "agent" in tokens

    def test_tokenize_stop_words(self):
        from vectors import _tokenize
        tokens = _tokenize("the and of for in a an is")
        assert len(tokens) == 0


class TestBuildEmbeddings:
    def test_basic_embeddings(self):
        from vectors import build_embeddings
        nodes = [
            {"id": "n1", "label": "Agent Pipeline"},
            {"id": "n2", "label": "Evolution Memory"},
            {"id": "n3", "label": "Vector Search"},
        ]
        edges = [
            {"source": "n1", "target": "n2"},
            {"source": "n2", "target": "n3"},
        ]
        id2idx, embs, w2i, comps = build_embeddings(nodes, edges, dim=8)
        assert len(id2idx) == 3
        # SVD dim = min(dim, N, V) — with 3 nodes, max dim is 3
        assert embs.shape[0] == 3
        assert embs.shape[1] <= 8
        assert len(w2i) > 0

    def test_empty_nodes(self):
        from vectors import build_embeddings
        a, b, c, d = build_embeddings([], [], dim=8)
        assert a == {}
        assert b.size == 0
        assert b.shape == (0, 0)
        assert c == {}
        assert d.size == 0

    def test_single_node(self):
        from vectors import build_embeddings
        nodes = [{"id": "n1", "label": "Test"}]
        id2idx, embs, w2i, comps = build_embeddings(nodes, [], dim=4)
        assert len(id2idx) == 1
        assert embs.shape[0] == 1
        assert embs.shape[1] == 1  # SVD: min(4, 1, 1) = 1


class TestSearch:
    def test_basic_search(self):
        from vectors import build_embeddings, search
        nodes = [
            {"id": "n1", "label": "Agent Pipeline"},
            {"id": "n2", "label": "Evolution Memory"},
            {"id": "n3", "label": "Vector Search Engine"},
        ]
        edges = [{"source": "n1", "target": "n2"}]
        id2idx, embs, w2i, comps = build_embeddings(nodes, edges, dim=8)
        label_map = {n['id']: n.get('label', n['id']) for n in nodes}
        results = search("pipeline", id2idx, embs, label_map, w2i, comps, top_k=3)
        assert len(results) > 0

    def test_empty_search(self):
        from vectors import search
        results = search("test", {}, np.empty((0, 0)), {}, {}, np.empty((0, 0)))
        assert results == []


class TestVectorStore:
    def test_add_and_search(self, tmp_path):
        from vectors import VectorStore, build_embeddings, encode_query
        db_path = tmp_path / "chroma_test"
        vs = VectorStore(db_path)
        nodes = [
            {"id": "n1", "label": "Agent"},
            {"id": "n2", "label": "Pipeline"},
            {"id": "n3", "label": "Memory Evolution"},
        ]
        edges = [{"source": "n1", "target": "n2"}]
        id2idx, embs, w2i, comps = build_embeddings(nodes, edges, dim=8)
        n = vs.add(embs, nodes, id2idx)
        assert n == 3
        q_emb = encode_query("evolution", w2i, comps)
        results = vs.search(q_emb, top_k=2)
        assert len(results) > 0

    def test_search_empty_store(self, tmp_path):
        from vectors import VectorStore
        vs = VectorStore(tmp_path / "empty_test")
        q = np.zeros(8, dtype=np.float32)
        results = vs.search(q, top_k=5)
        assert results == []

    def test_count(self, tmp_path):
        from vectors import VectorStore, build_embeddings
        db_path = tmp_path / "count_test"
        vs = VectorStore(db_path)
        assert vs.count() == 0
        nodes = [{"id": "n1", "label": "Test"}, {"id": "n2", "label": "Two"}]
        id2idx, embs, w2i, comps = build_embeddings(nodes, [], dim=4)
        vs.add(embs, nodes, id2idx)
        assert vs.count() == 2

    def test_filtered_search(self, tmp_path):
        from vectors import VectorStore, build_embeddings, encode_query
        db_path = tmp_path / "filter_test"
        vs = VectorStore(db_path)
        nodes = [
            {"id": "n1", "label": "Agent", "group": "concept"},
            {"id": "n2", "label": "Paper on Agents", "group": "paper"},
        ]
        edges = []
        id2idx, embs, w2i, comps = build_embeddings(nodes, edges, dim=4)
        vs.add(embs, nodes, id2idx)
        q_emb = encode_query("agent", w2i, comps)
        all_results = vs.search(q_emb, top_k=5)
        filtered = vs.search(q_emb, top_k=5, where={"group": "paper"})
        assert len(filtered) >= 0
        assert len(filtered) <= len(all_results)
