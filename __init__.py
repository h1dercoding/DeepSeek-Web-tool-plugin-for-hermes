"""DeepSeek 官方搜索 + 抓取插件（用户级）。"""

from __future__ import annotations

from .provider import DeepSeekWebSearchProvider


def register(ctx) -> None:
    """向 Hermes 注册 DeepSeek 搜索/抓取后端。"""
    ctx.register_web_search_provider(DeepSeekWebSearchProvider())
