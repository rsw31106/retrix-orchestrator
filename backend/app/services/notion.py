"""
Notion integration service.
- Fetch page content as markdown
- Detect changes via content hash
- Convert Notion blocks → plain text for PM consumption
"""
import hashlib
import re
from typing import Optional

from notion_client import AsyncClient

from app.core.config import get_settings


def _get_notion_token() -> str:
    """Read Notion API key from DB settings first, fall back to env."""
    try:
        from app.core.database import SessionLocal
        from app.models.models import SystemSetting
        db = SessionLocal()
        try:
            row = db.query(SystemSetting).filter(SystemSetting.key == "notion_api_key").first()
            if row and row.value:
                return row.value
        finally:
            db.close()
    except Exception:
        pass
    settings = get_settings()
    return settings.notion_api_key


def _get_client() -> AsyncClient:
    token = _get_notion_token()
    if not token:
        raise ValueError("NOTION_API_KEY is not configured. Set it in Settings > Notion Integration.")
    return AsyncClient(auth=token)


def extract_page_id(url_or_id: str) -> str:
    """Accept full Notion URL or bare page ID and return the 32-char page ID."""
    # Strip query params / fragments
    clean = url_or_id.split("?")[0].split("#")[0].rstrip("/")
    # Last path segment may contain the ID after a dash: "Page-Title-<id>"
    segment = clean.split("/")[-1]
    # Remove dashes and extract 32-char hex block
    raw = segment.replace("-", "")
    match = re.search(r"[0-9a-f]{32}", raw)
    if match:
        return match.group(0)
    # Fallback: assume it's already a UUID-style id
    return url_or_id.strip()


def _block_to_text(block: dict) -> str:
    """Convert a single Notion block to plain text."""
    btype = block.get("type", "")
    data = block.get(btype, {})
    rich_texts = data.get("rich_text", [])
    text = "".join(rt.get("plain_text", "") for rt in rich_texts)

    prefix_map = {
        "heading_1": "# ",
        "heading_2": "## ",
        "heading_3": "### ",
        "bulleted_list_item": "- ",
        "numbered_list_item": "1. ",
        "to_do": "- [ ] ",
        "toggle": "> ",
        "quote": "> ",
        "code": "```\n",
    }
    suffix_map = {
        "code": "\n```",
    }

    prefix = prefix_map.get(btype, "")
    suffix = suffix_map.get(btype, "")
    if text or prefix:
        return f"{prefix}{text}{suffix}"
    return ""


async def fetch_page_as_markdown(page_id: str) -> tuple[str, str]:
    """
    Returns (title, markdown_content) for the given Notion page.
    Recursively fetches child blocks.
    """
    client = _get_client()

    # Get page metadata (title)
    page = await client.pages.retrieve(page_id=page_id)
    title = ""
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            rich_texts = prop.get("title", [])
            title = "".join(rt.get("plain_text", "") for rt in rich_texts)
            break

    # Get all blocks recursively
    lines = []
    await _collect_blocks(client, page_id, lines, depth=0)
    content = "\n".join(lines)
    return title, content


async def _collect_blocks(client: AsyncClient, block_id: str, lines: list, depth: int, _visited: set = None):
    if _visited is None:
        _visited = set()
    if block_id in _visited:
        return  # prevent infinite loops from circular page links
    _visited.add(block_id)

    indent = "  " * depth
    cursor = None
    while True:
        kwargs = {"block_id": block_id, "page_size": 100}
        if cursor:
            kwargs["start_cursor"] = cursor
        resp = await client.blocks.children.list(**kwargs)
        for block in resp.get("results", []):
            btype = block.get("type", "")

            # Child page — fetch its full content recursively
            if btype == "child_page":
                child_title = block.get("child_page", {}).get("title", "Untitled")
                lines.append(f"{indent}## {child_title}")
                await _collect_blocks(client, block["id"], lines, depth + 1, _visited)
                continue

            # Child database — just note its title, skip content
            if btype == "child_database":
                db_title = block.get("child_database", {}).get("title", "Database")
                lines.append(f"{indent}> [Database: {db_title}]")
                continue

            text = _block_to_text(block)
            if text:
                lines.append(f"{indent}{text}")
            # Recurse into inline children (toggles, indented lists, etc.)
            if block.get("has_children") and btype not in ("child_page", "child_database"):
                await _collect_blocks(client, block["id"], lines, depth + 1, _visited)
        if not resp.get("has_more"):
            break
        cursor = resp.get("next_cursor")


def compute_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()[:16]


async def get_page_title(page_id: str) -> str:
    """Lightweight fetch — title only."""
    client = _get_client()
    page = await client.pages.retrieve(page_id=page_id)
    props = page.get("properties", {})
    for prop in props.values():
        if prop.get("type") == "title":
            return "".join(rt.get("plain_text", "") for rt in prop.get("title", []))
    return page_id
