from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from voider.tools.base import Tool, ToolResult


class WebFetchTool(Tool):
    name = "web_fetch"
    description = "Fetch a URL and return its main text content (HTML stripped to readable text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string"},
            "max_chars": {"type": "integer", "default": 8000},
        },
        "required": ["url"],
    }

    def permission_target(self, arguments: dict[str, Any]) -> str:
        url = str(arguments.get("url", ""))
        host = urlparse(url).hostname or "*"
        return host.lower()

    def permission_summary(self, arguments: dict[str, Any]) -> str:
        return f"Fetch URL: {arguments.get('url', '')}"

    async def run(self, arguments: dict[str, Any]) -> ToolResult:
        url = str(arguments.get("url", "")).strip()
        max_chars = int(arguments.get("max_chars", 8000))
        if not url:
            return ToolResult(ok=False, content="url is required")
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return ToolResult(ok=False, content="only http(s) URLs allowed")

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 voider/0.0.1",
        }
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "")
            body = r.text

        if "html" in ctype.lower() or body.lstrip().startswith("<"):
            soup = BeautifulSoup(body, "html.parser")
            for tag in soup(["script", "style", "noscript", "header", "footer", "nav", "aside"]):
                tag.decompose()
            text = soup.get_text("\n", strip=True)
        else:
            text = body

        if len(text) > max_chars:
            text = text[:max_chars] + f"\n\n[truncated at {max_chars} chars]"
        return ToolResult(ok=True, content=text, data={"url": url, "host": parsed.hostname})
