"""Scrape tool: fetch a URL and return its text content."""

from __future__ import annotations


def register(mcp, *, get_display_manager, get_confinement, get_state_manager=None, get_guard=None):
    """Register the Scrape tool."""

    @mcp.tool(
        name="Scrape",
        description=(
            "Fetch a URL and return up to 50,000 characters of its text content. "
            "HTML tags are stripped; plain text is returned."
        ),
    )
    def scrape(url: str) -> str:
        guard = get_guard() if get_guard is not None else None
        if guard:
            err = guard.check("Scrape")
            if err:
                return err

        import urllib.request
        import html
        import re

        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    )
                },
            )
            with urllib.request.urlopen(req, timeout=30) as response:
                charset = "utf-8"
                content_type = response.headers.get("Content-Type", "")
                if "charset=" in content_type:
                    charset = content_type.split("charset=")[-1].split(";")[0].strip()

                raw = response.read(1_000_000)  # read up to 1MB
                text = raw.decode(charset, errors="replace")

        except Exception as e:
            return f"Error fetching '{url}': {e}"

        # Strip HTML tags
        text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.IGNORECASE | re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = html.unescape(text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text[:50_000]
