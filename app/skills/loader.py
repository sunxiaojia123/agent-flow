"""SKILL.md parser — extracts YAML frontmatter, company info, API definitions."""

import re
import yaml
import json
from pathlib import Path
from app.skills.models import Skill, ApiEndpoint, ApiParam


def parse_skill(filepath: str | Path) -> Skill:
    """Parse a SKILL.md file into a Skill object."""
    filepath = Path(filepath)
    content = filepath.read_text(encoding="utf-8")

    # Split frontmatter and body
    frontmatter, body = _split_frontmatter(content)
    meta = yaml.safe_load(frontmatter) if frontmatter else {}

    skill = Skill(
        name=meta.get("name", filepath.parent.name),
        display_name=meta.get("display_name", ""),
        description=meta.get("description", ""),
        category=meta.get("category", "supplier"),
        version=meta.get("version", "1.0"),
        body=body,
    )

    # Parse sections
    skill.company_info = _parse_company_info(body)
    skill.apis = _parse_apis(body)
    skill.execution_guide = _parse_execution_guide(body)

    return skill


def _split_frontmatter(content: str) -> tuple[str, str]:
    """Split YAML frontmatter from markdown body."""
    if not content.startswith("---"):
        return "", content
    parts = content.split("---", 2)
    if len(parts) < 3:
        return "", content
    return parts[1].strip(), parts[2].strip()


def _parse_company_info(body: str) -> dict:
    """Parse company info section (lines under '## 公司信息' or '## 用户信息')."""
    info = {}
    section = _extract_section(body, ["## 公司信息", "## 用户信息"])
    if not section:
        return info
    for line in section.strip().split("\n"):
        line = line.strip()
        # Strip leading bullet: "- " or "* "
        if line.startswith("- "):
            line = line[2:]
        elif line.startswith("* "):
            line = line[2:]
        # Match "key: value" or "key：value" (after bullet removed)
        match = re.match(r"\**\s*(.+?)\**\s*[：:]\s*(.+)", line)
        if match:
            key = match.group(1).strip().strip("*").strip()
            val = match.group(2).strip()
            info[key] = val
    return info


def _parse_apis(body: str) -> list[ApiEndpoint]:
    """Parse API endpoint definitions under '## API 接口'."""
    apis = []
    api_section = _extract_section(body, ["## API 接口"])
    if not api_section:
        return apis

    # Split by ### blocks
    blocks = re.split(r"\n(?=### )", api_section)
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        # Extract API name from ### header
        header_match = re.match(r"###\s+(.+)", block)
        if not header_match:
            continue
        api_name = header_match.group(1).strip()

        # Parse fields
        desc = _extract_field(block, "描述")
        method = _extract_field(block, "方法") or "GET"
        path = _extract_field(block, "路径") or ""

        # Parse params as list
        params = _parse_params(block)
        mock_response = _parse_mock_response(block)

        apis.append(ApiEndpoint(
            name=api_name,
            description=desc,
            method=method,
            path=path,
            params=params,
            mock_response=mock_response,
        ))

    return apis


def _parse_params(block: str) -> list[ApiParam]:
    """Parse parameter list from API block."""
    params = []
    # Find the params section (after '参数:' line)
    param_match = re.search(r"[-*]\s*\*{0,2}参数\*{0,2}\s*[：:]?\s*\n(.*?)(?=\n[-*]\s*\*{0,2}|```json|\Z)", block, re.DOTALL)
    if not param_match:
        return params

    param_lines = param_match.group(1).strip()
    for line in param_lines.split("\n"):
        line = line.strip()
        if not line.startswith("- "):
            continue
        line = line[2:]
        # pattern: "name: type (必填/可选) - description"
        match = re.match(r"(.+?)\s*[：:]\s*(\S+)\s*(?:\(([^)]+)\))?\s*[-—]?\s*(.*)", line)
        if match:
            pname = match.group(1).strip()
            ptype = match.group(2).strip()
            preq_str = match.group(3) or ""
            pdesc = match.group(4).strip() if match.lastindex and match.lastindex >= 4 else ""
            params.append(ApiParam(
                name=pname,
                type=ptype,
                required="必填" in preq_str,
                description=pdesc,
            ))
    return params


def _parse_mock_response(block: str) -> dict:
    """Extract mock JSON response from API block."""
    # Find ```json ... ``` block (the first JSON code block in the API definition)
    pattern = r"```json\s*\n(.*?)```"
    match = re.search(pattern, block, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            return {}
    return {}


def _parse_execution_guide(body: str) -> str:
    """Extract execution guide section."""
    guide = _extract_section(body, ["## 执行说明"])
    return guide.strip() if guide else ""


def _extract_section(body: str, headers: list[str]) -> str | None:
    """Extract a section by header name. Returns content until next ## or end."""
    for h in headers:
        pattern = rf"{re.escape(h)}\s*\n(.*?)(?=\n##\s|\Z)"
        match = re.search(pattern, body, re.DOTALL)
        if match:
            return match.group(1).strip()
    return None


def _extract_field(block: str, field_name: str) -> str:
    """Extract a single field value like '- **描述**: ...'"""
    pattern = rf"[-*]\s*\**{field_name}\**[：:\s]+(.+)"
    match = re.search(pattern, block)
    if match:
        return match.group(1).strip()
    return ""
