"""共享 fixture — 测试用的迷你图。"""

import json
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def mini_graph():
    """5 节点 6 边的小图，用于快速测试。"""
    return {
        "nodes": [
            {"id": "n1", "label": "Agent", "group": "concept"},
            {"id": "n2", "label": "Pipeline", "group": "concept"},
            {"id": "n3", "label": "Memory", "group": "concept"},
            {"id": "n4", "label": "Evolution", "group": "process"},
            {"id": "n5", "label": "Embedding 向量", "group": "tech"},
        ],
        "edges": [
            {"source": "n1", "target": "n2", "relation": "uses"},
            {"source": "n1", "target": "n3", "relation": "has"},
            {"source": "n2", "target": "n3", "relation": "feeds"},
            {"source": "n3", "target": "n4", "relation": "enables"},
            {"source": "n4", "target": "n5", "relation": "produces"},
            {"source": "n1", "target": "n5", "relation": "co_occurred_with"},
        ],
    }


@pytest.fixture
def temp_dir(tmp_path):
    """临时工作目录。"""
    d = tmp_path / "graph_test"
    d.mkdir()
    return d


@pytest.fixture
def graph_file(temp_dir, mini_graph):
    """在临时目录创建 graph.json。"""
    path = temp_dir / "graph.json"
    path.write_text(json.dumps(mini_graph, ensure_ascii=False), encoding='utf-8')
    return path
