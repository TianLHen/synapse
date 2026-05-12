"""python -m synapse 入口 — 转发到 knowledge_graph.main()。"""

import sys
from pathlib import Path

# 确保当前目录在 path 中（setup.py install 后不需要，开发模式需要）
_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from knowledge_graph import main

main()
