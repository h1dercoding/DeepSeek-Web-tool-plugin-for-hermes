"""DeepSeek 官方搜索/抓取 —— 用户插件（web-search backend）。

两个能力都实现：
- search  -> POST https://api.deepseek.com/v1/tools/search
- extract -> POST https://api.deepseek.com/v1/tools/fetch

复用 DEEPSEEK_API_KEY（与模型调用同一个 key），可用 DEEPSEEK_SEARCH_BASE_URL 覆盖 Base URL。

v1.1（2026-10-21）升级：
- search 结果带上官方元数据 authority(0-4) / rerank_score(0-3) / date / site_name
- 低质量结果过滤：权威度低于门槛、或相关性分数低于门槛的结果剔除（保底保留 2 条）
- 摘要按 DEEPSEEK_SEARCH_SUMMARY_CHARS（默认 700）截断，避免单条结果灌满上下文

config:
    web:
      search_backend: "deepseek"
      extract_backend: "deepseek"

可选调优（.env）：
    DEEPSEEK_SEARCH_MIN_AUTHORITY   = 0     # 丢弃权威度低于此值的结果（0 = 不按权威度过滤，-1 未知保留）
    DEEPSEEK_SEARCH_MIN_SCORE       = 0.6   # 丢弃 rerank_score 低于此值的结果
    DEEPSEEK_SEARCH_SUMMARY_CHARS   = 700   # 每条摘要最多保留字符数（0 = 不截断）
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import httpx

from agent.web_search_provider import WebSearchProvider, get_provider_env

logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = "https://api.deepseek.com"

# 官方检索质量门槛：authority 0-4（3+ 高权威，-1 未知），rerank_score 0-3（1.5+ 高质量）
DEFAULT_MIN_AUTHORITY = 0
DEFAULT_MIN_SCORE = 0.6
DEFAULT_SUMMARY_CHARS = 700


def _base_url() -> str:
    return (get_provider_env("DEEPSEEK_SEARCH_BASE_URL") or DEFAULT_BASE_URL).rstrip("/")


def _env_int(name: str, default: int) -> int:
    raw = get_provider_env(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(float(str(raw).strip()))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    raw = get_provider_env(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return float(str(raw).strip())
    except (TypeError, ValueError):
        return default


def _clip(text: str, limit: int) -> str:
    text = (text or "").strip()
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + " …"


def _quality_tag(item: Dict[str, Any]) -> str:
    """把官方元数据压成一行人读的标签。"""
    parts: List[str] = []
    authority = item.get("authority")
    if isinstance(authority, (int, float)) and authority >= 0:
        parts.append(f"权威{int(authority)}/4")
    score = item.get("rerank_score")
    if isinstance(score, (int, float)):
        parts.append(f"相关{float(score):.2f}")
    date = item.get("date")
    if isinstance(date, str) and len(date) >= 10:
        parts.append(date[:10])
    site = item.get("site_name")
    if isinstance(site, str) and site.strip():
        parts.append(site.strip())
    return " · ".join(parts)


def _post(endpoint: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    api_key = get_provider_env("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError("DEEPSEEK_API_KEY 未配置，DeepSeek 搜索需要它")

    url = f"{_base_url()}/v1/tools/{endpoint}"
    logger.info("DeepSeek %s -> %s", endpoint, url)
    resp = httpx.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()


class DeepSeekWebSearchProvider(WebSearchProvider):
    """DeepSeek 自研搜索引擎 + 网页抓取。"""

    @property
    def name(self) -> str:
        return "deepseek"

    @property
    def display_name(self) -> str:
        return "DeepSeek Search/Fetch"

    def is_available(self) -> bool:
        return bool(get_provider_env("DEEPSEEK_API_KEY"))

    def supports_search(self) -> bool:
        return True

    def supports_extract(self) -> bool:
        return True

    def search(self, query: str, limit: int = 5) -> Dict[str, Any]:
        try:
            count = max(1, min(int(limit or 5), 50))
            raw = _post(
                "search",
                {"query": query, "count": count, "need_content": False},
            )
            results = raw.get("results") or []

            min_authority = _env_int("DEEPSEEK_SEARCH_MIN_AUTHORITY", DEFAULT_MIN_AUTHORITY)
            min_score = _env_float("DEEPSEEK_SEARCH_MIN_SCORE", DEFAULT_MIN_SCORE)
            summary_chars = _env_int("DEEPSEEK_SEARCH_SUMMARY_CHARS", DEFAULT_SUMMARY_CHARS)

            kept: List[Dict[str, Any]] = []
            dropped = 0
            for item in results:
                authority = item.get("authority")
                score = item.get("rerank_score")
                bad_authority = (
                    isinstance(authority, (int, float))
                    and 0 <= authority < min_authority
                )
                bad_score = isinstance(score, (int, float)) and score < min_score
                if bad_authority or bad_score:
                    dropped += 1
                    continue
                kept.append(item)

            # 别把结果过滤空：宁可返回低分也要留两条给上层判断
            if len(kept) < min(2, len(results)):
                kept = list(results)
                dropped = 0

            web = []
            for i, item in enumerate(kept):
                body = item.get("summary") or item.get("snippet") or ""
                body = _clip(body, summary_chars)
                tag = _quality_tag(item)
                description = f"[{tag}]\n{body}" if tag else body
                web.append(
                    {
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "description": description,
                        "position": i + 1,
                        # 额外字段便于本地调试/自定义消费（标准工具链会忽略）
                        "authority": item.get("authority"),
                        "rerank_score": item.get("rerank_score"),
                        "date": item.get("date"),
                        "site_name": item.get("site_name"),
                    }
                )

            meta = {"returned": len(web), "dropped_low_quality": dropped}
            return {"success": True, "data": {"web": web, "meta": meta}}
        except Exception as exc:  # noqa: BLE001
            logger.warning("DeepSeek search error: %s", exc)
            return {"success": False, "error": f"DeepSeek search failed: {exc}"}

    def extract(self, urls: List[str], **kwargs: Any) -> List[Dict[str, Any]]:
        """逐条抓取（DeepSeek Fetch 一次只接受一个 URL）。"""
        docs: List[Dict[str, Any]] = []
        for url in urls:
            try:
                raw = _post("fetch", {"url": url})
                content = raw.get("content", "") or ""
                title = raw.get("title", "") or ""
                entry: Dict[str, Any] = {
                    "url": url,
                    "title": title,
                    "content": content,
                    "raw_content": content,
                    "metadata": {"sourceURL": url, "title": title},
                }
                if not content:
                    entry["error"] = "empty content"
                docs.append(entry)
            except Exception as exc:  # noqa: BLE001
                logger.warning("DeepSeek fetch error for %s: %s", url, exc)
                docs.append(
                    {
                        "url": url,
                        "title": "",
                        "content": "",
                        "error": f"DeepSeek fetch failed: {exc}",
                        "metadata": {"sourceURL": url},
                    }
                )
        return docs

    def get_setup_schema(self) -> Dict[str, Any]:
        return {
            "name": "DeepSeek Search/Fetch",
            "badge": "paid",
            "tag": "官方搜索引擎 + 网页正文抓取，复用 DeepSeek API key",
            "env_vars": [
                {
                    "key": "DEEPSEEK_API_KEY",
                    "prompt": "DeepSeek API key（与模型调用共用）",
                    "url": "https://platform.deepseek.com/api_keys",
                },
            ],
        }
