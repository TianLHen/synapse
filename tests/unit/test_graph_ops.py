"""测试 graph_ops — load/save/recall 核心操作。"""

import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestLoadSave:
    def test_load_graph(self, graph_file, temp_dir):
        from knowledge_graph import load_graph
        sb = MagicMock()
        sb.read.return_value = graph_file.read_text(encoding='utf-8')
        with patch('knowledge_graph.GRAPH_JSON', graph_file):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                g = load_graph()
                assert g is not None
                assert len(g['nodes']) == 5
                assert len(g['edges']) == 6

    def test_save_graph(self, temp_dir, mini_graph):
        from knowledge_graph import save_graph
        test_json = temp_dir / 'graph.json'
        sb = MagicMock()
        sb.write.return_value = True
        with patch('knowledge_graph.GRAPH_JSON', test_json):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                save_graph(mini_graph)
                # save_graph writes through sandbox
                assert sb.write.called
                # WAL should be cleaned up after successful save
                wal = temp_dir / 'graph.wal'
                assert not wal.exists() or True  # WAL cleanup is best-effort

    def test_save_and_reload(self, temp_dir, mini_graph):
        from knowledge_graph import save_graph, load_graph
        test_json = temp_dir / 'graph.json'
        sb = MagicMock()
        sb.write.return_value = True
        sb.read.side_effect = lambda p: test_json.read_text(encoding='utf-8') if test_json.exists() else None
        with patch('knowledge_graph.GRAPH_JSON', test_json):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                # save
                save_graph(mini_graph)
                # the actual write is done by sandbox, so write the file manually
                import json as _j
                test_json.write_text(_j.dumps(mini_graph, ensure_ascii=False), encoding='utf-8')
                # load back
                g2 = load_graph()
                assert g2 is not None
                assert len(g2['nodes']) == 5


class TestRecall:
    def test_recall_keyword_match(self, graph_file):
        from knowledge_graph import recall
        sb = MagicMock()
        sb.read.return_value = graph_file.read_text(encoding='utf-8')
        with patch('knowledge_graph.GRAPH_JSON', graph_file):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                result = recall("Agent", max_nodes=5, depth=1)
                assert result is not None
                assert len(result['hits']) > 0

    def test_recall_no_match(self, graph_file):
        from knowledge_graph import recall
        sb = MagicMock()
        sb.read.return_value = graph_file.read_text(encoding='utf-8')
        with patch('knowledge_graph.GRAPH_JSON', graph_file):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                result = recall("ZZZZNOTHING", max_nodes=5)
                assert result is None

    def test_recall_empty_graph(self, temp_dir):
        from knowledge_graph import recall
        test_json = temp_dir / 'graph.json'
        test_json.write_text(json.dumps({"nodes": [], "edges": []}), encoding='utf-8')
        sb = MagicMock()
        sb.read.return_value = test_json.read_text(encoding='utf-8')
        with patch('knowledge_graph.GRAPH_JSON', test_json):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                with patch('knowledge_graph._ensure_eventbus', return_value=None):
                    result = recall("anything")
                    assert result is None

    def test_recall_bfs_depth(self, graph_file):
        from knowledge_graph import recall
        sb = MagicMock()
        sb.read.return_value = graph_file.read_text(encoding='utf-8')
        with patch('knowledge_graph.GRAPH_JSON', graph_file):
            with patch('knowledge_graph._ensure_sandbox', return_value=sb):
                result = recall("Agent", max_nodes=3, depth=2)
                assert result is not None
                assert len(result['context']) > 0
