from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, unquote, urlparse, parse_qs

import httpx
from bs4 import BeautifulSoup

from voider.tools.base import Tool, ToolResult


class WebSearchTool(Tool):
    name = "web_search"
    description = "Search the web via DuckDuckGo. Returns a list of {title, url, snippet}."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "default": 8},
        },
        "required": ["query"],
    }

    def permission_target(self, arguments: dict[str, Any]) -> str:
        return "*"

    def permission_summary(self, arguments: dict[str, Any]) -> str:
        return f"Web search: {arguments.get('query', '')!r}"

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        query = str(arguments.get("query", "")).strip()
        if not query:
            return ToolResult(ok=False, content="query is required")
        max_results = int(arguments.get("max_results", 8))

        url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 voider/0.0.1",
        }
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            html = r.text

        soup = BeautifulSoup(html, "html.parser")
        results = []
        for res in soup.select("div.result")[: max_results * 2]:
            a = res.select_one("a.result__a")
            snippet_el = res.select_one(".result__snippet")
            if not a:
                continue
            href = a.get("href", "")
            real = _unwrap_ddg(href)
            results.append(
                {
                    "title": a.get_text(strip=True),
                    "url": real,
                    "snippet": snippet_el.get_text(" ", strip=True) if snippet_el else "",
                }
            )
            if len(results) >= max_results:
                break

        if not results:
            return ToolResult(ok=True, content="(no results)")
        lines = [f"{i+1}. {r['title']}\n   {r['url']}\n   {r['snippet']}" for i, r in enumerate(results)]
        return ToolResult(ok=True, content="\n".join(lines), data={"results": results})


def _unwrap_ddg(href: str) -> str:
    parsed = urlparse(href)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        qs = parse_qs(parsed.query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href
