"""Synapse — 事件驱动的智能知识图谱引擎。

安装:
    pip install -e .           # 开发模式
    pip install -r requirements.txt  # 安装所有依赖

用法:
    synapse status             # 图谱状态
    synapse recall <topic>     # 召回知识
    synapse full               # 全量运行
"""

from setuptools import setup

setup(
    name="synapse",
    version="0.1.0",
    description="事件驱动的智能知识图谱引擎",
    long_description=__doc__,
    long_description_content_type="text/markdown",
    author="四弟",
    python_requires=">=3.10",
    py_modules=[
        "knowledge_graph",
        "llm",
        "vectors",
        "sandbox",
        "protoskill",
        "evolution",
        "const",
        "synapse_cli",
        "synapse_agent",
        "tools",
    ],
    packages=[
        "skills",
    ],
    package_dir={
        "skills": "skills",
    },
    include_package_data=True,
    install_requires=[
        "numpy>=1.24.0",
        "chromadb>=1.5.0",
    ],
    extras_require={
        "anthropic": ["anthropic>=0.30.0"],
        "google": ["google-genai>=1.0.0"],
        "bedrock": ["boto3>=1.34.0"],
        "cohere": ["cohere>=5.0.0"],
        "all": [
            "httpx>=0.27.0",
            "anthropic>=0.30.0",
            "google-genai>=1.0.0",
            "boto3>=1.34.0",
            "cohere>=5.0.0",
        ],
        "dev": [
            "pytest>=8.0.0",
            "pytest-cov>=5.0.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "synapse=synapse_cli:main",
        ],
    },
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Operating System :: Microsoft :: Windows",
        "Topic :: Database :: Front-Ends",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
)
