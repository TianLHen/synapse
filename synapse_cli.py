"""Synapse CLI — 命令行入口。

用法:
    synapse                   # 进入 AI agent 对话模式
    synapse status            # 图谱状态
    synapse collect           # 采集源文件
    synapse full              # 全量运行
    synapse pipeline <n>      # 从第 n 步运行
    synapse rebuild           # 重建图谱
    synapse recall <topic>    # 召回知识
    synapse query <关键词>     # 查询图谱
    synapse learn <text>      # 学习新内容
    synapse self              # 自检
    synapse distill           # 精简图谱
"""

import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
if str(_here) not in sys.path:
    sys.path.insert(0, str(_here))

from knowledge_graph import main as _main


def main():
    _main()


if __name__ == '__main__':
    main()
