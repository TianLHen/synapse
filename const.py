"""知识图谱配置：路径常量 + 合并停用词。

从 knowledge_graph.py 提取，避免重复定义和散落各处的魔数字符串。
"""
from pathlib import Path

# === 工作路径 ===
GRAPH_DIR = Path.home() / "brain" / "graph"
INPUT_DIR = GRAPH_DIR / "input"
SEMANTIC_DIR = GRAPH_DIR / "semantic"
GRAPH_JSON = GRAPH_DIR / "graph.json"
CHANGELOG = GRAPH_DIR / "changelog.md"
HASH_FILE = GRAPH_DIR / ".file_hashes.json"
WORKSPACE_DIR = GRAPH_DIR / "workspace"

# === 记忆系统输出 ===
MEMORY_DIR = Path.home() / ".claude" / "projects" / "C--Users-lenovo" / "memory"

# === 自我进化系统路径 ===
BEHAVIOR_LOG = WORKSPACE_DIR / ".behavior_log.json"
EVOLUTION_LOG = GRAPH_DIR / "evolution_log.md"
SELF_PROFILE = WORKSPACE_DIR / "self_profile.json"

# === 刺激/动作日志 ===
STIMULUS_LOG = WORKSPACE_DIR / ".stimulus_log.json"
ACTION_LOG = WORKSPACE_DIR / ".action_log"

# === 源文件映射 ===
SOURCE_FILES = {
    "ability-map.md": Path.home() / "brain" / "notes" / "ability-map.md",
    "ai-agent-self-evolution-landscape.md": Path.home() / "brain" / "notes" / "ai-agent-self-evolution-landscape.md",
    "hermes-self-evolution-architecture.md": Path.home() / "brain" / "notes" / "hermes-self-evolution-architecture.md",
    "community-project-internalization.md": Path.home() / "brain" / "notes" / "community-project-internalization.md",
    "autonomous-operation-mode.md": Path.home() / "brain" / "notes" / "autonomous-operation-mode.md",
    "my-brain-architecture.md": Path.home() / "brain" / "notes" / "my-brain-architecture.md",
    "absorb-and-evolve.md": Path.home() / ".claude" / "skills" / "absorb-and-evolve" / "SKILL.md",
    "research-collector.md": Path.home() / ".claude" / "skills" / "research-collector" / "SKILL.md",
    "skill-extractor.md": Path.home() / ".claude" / "skills" / "skill-extractor" / "SKILL.md",
    "skill-self-test.md": Path.home() / ".claude" / "skills" / "skill-self-test" / "SKILL.md",
    "omc-reference.md": Path.home() / ".claude" / "skills" / "omc-reference" / "SKILL.md",
}

# === 合并停用词表 ===
# 从 learn()/recall()/invoke()/clean_conversation() 四个地方的重复列表合并而来。
# 函数特有的覆盖写在各自的局部覆盖变量中。

STOP_WORDS_EN: set[str] = {
    # 基础英语功能词
    'the', 'a', 'an', 'and', 'or', 'of', 'in', 'to', 'for',
    'with', 'on', 'at', 'by', 'is', 'it', 'as', 'be', 'this',
    'that', 'are', 'was', 'were', 'been', 'have', 'has', 'had',
    'not', 'no', 'but', 'from', 'they', 'we', 'you', 'all',
    'can', 'will', 'would', 'could', 'should', 'may', 'also',
    # 常用泛词（低信息量）
    'very', 'just', 'about', 'than', 'then', 'what', 'which',
    'more', 'some', 'these', 'them', 'into', 'over', 'such',
    'each', 'well', 'here', 'there', 'their', 'does', 'did',
    'way', 'use', 'used', 'using', 'via', 'key', 'based',
    'note', 'section', 'new', 'two', 'one', 'data', 'model',
    # 从 clean_conversation / noise_labels 合并
    'when', 'where', 'they', 'per', 'set', 'part', 'get',
    'between', 'across', 'without', 'within', 'much', 'most',
    'few', 'any', 'every', 'still', 'even', 'once', 'never',
    'yet', 'thus', 'hence', 'often', 'always', 'must', 'might',
    'shall', 'both', 'same', 'first', 'second', 'third', 'last',
    'next', 'other', 'many', 'because', 'after', 'before',
    'during', 'through', 'its', 'his', 'her', 'our',
    # 领域泛词
    'serve', 'serves', 'served',
    'foundation', 'foundations',
    'graph', 'graphs',
}

# learn() 特有的停用词（提取时更严格的过滤用）
STOP_LEARN_EXTRA: set[str] = {
    'do', 'does', 'done', 'doing', 'make', 'makes', 'made',
    'making', 'take', 'takes', 'took', 'taken', 'taking',
    'get', 'gets', 'got', 'gotten', 'getting', 'give', 'gives',
    'gave', 'given', 'giving', 'need', 'needs', 'needed',
    'want', 'wants', 'wanted', 'know', 'knows', 'knew',
    'known', 'think', 'thinks', 'thought', 'seeing', 'seems',
    'say', 'says', 'said', 'see', 'sees', 'saw', 'seen',
    'come', 'comes', 'came', 'coming', 'go', 'goes', 'went',
    'gone', 'going', 'look', 'looks', 'looked', 'looking',
    'work', 'works', 'worked', 'working', 'like', 'likes',
    'also', 'well', 'even',
}
