from __future__ import annotations

import html
import json
import re
from pathlib import Path

from fastapi import HTTPException, status

from mianotes_web_service.db.models import Note
from mianotes_web_service.services.paths import WorkspacePaths, current_workspace_paths
from mianotes_web_service.services.publishing_navigation import published_note_path
from mianotes_web_service.services.publishing_theme import GENERATOR_META_TAG
from mianotes_web_service.services.storage import markdown_note_body


def write_note_pages(
    notes: list[Note],
    *,
    version_dir: Path,
    config: dict[str, object],
    include_folder: bool,
    paths: WorkspacePaths | None = None,
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    workspace_paths = paths or current_workspace_paths()
    note_pages: list[dict[str, object]] = []
    search_index: list[dict[str, object]] = []
    for note in notes:
        source_path = workspace_paths.note_file_path(note)
        if not source_path.exists():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f'Cannot publish "{note.title}" because its Markdown file no longer exists '
                    "in the filesystem."
                ),
            )
        body = without_duplicate_title_heading(
            markdown_note_body(source_path.read_text(encoding="utf-8")),
            note.title,
        )
        relative_path = Path(published_note_path(note, include_folder=include_folder))
        page_path = version_dir / relative_path
        page_path.parent.mkdir(parents=True, exist_ok=True)
        page_path.write_text(
            render_published_page(
                note=note,
                config=config,
                relative_path=relative_path,
                content_html=markdown_to_html(body),
            ),
            encoding="utf-8",
        )
        path = relative_path.as_posix()
        note_pages.append(
            {
                "title": note.title,
                "path": path,
                "folder": note.folder.name,
            }
        )
        search_index.append(
            {
                "section": note.folder.name,
                "folder": note.folder.name,
                "title": note.title,
                "path": path,
                "text": compact_text(body),
            }
        )
    return note_pages, search_index


def render_published_page(
    *,
    note: Note,
    config: dict[str, object],
    relative_path: Path,
    content_html: str,
) -> str:
    depth = len(relative_path.parts) - 1
    version_prefix = "../" * depth
    root_prefix = "../" * (depth + 1)
    brand = str(config.get("brand") or "mianotes")
    footer_html = str(config.get("footerHtml") or "")
    return html_shell(
        title=f"{note.title} | {brand}",
        stylesheet=f"{version_prefix}styles.css" if version_prefix else "styles.css",
        navigation_script=f"{root_prefix}navigation.js",
        search_script=f"{version_prefix}search.js" if version_prefix else "search.js",
        site_script=f"{version_prefix}site.js" if version_prefix else "site.js",
        body=(
            "<header data-header></header>\n"
            '<main class="layout">\n'
            '  <aside class="sidebar" data-sidebar></aside>\n'
            '  <section class="article-wrap">\n'
            '    <article class="article">\n'
            f'      <p class="eyebrow">{html.escape(note.folder.name)}</p>\n'
            f"      <h1>{html.escape(note.title)}</h1>\n"
            f"      {content_html}\n"
            '      <nav class="article-footer" data-article-footer></nav>\n'
            f'      <footer class="site-footer">{footer_html}</footer>\n'
            "    </article>\n"
            "  </section>\n"
            '  <aside class="page-toc" data-page-toc></aside>\n'
            "</main>\n"
        ),
    )


def write_version_index(
    *,
    version_dir: Path,
    config: dict[str, object],
    note_pages: list[dict[str, object]],
) -> None:
    brand = html.escape(str(config.get("brand") or "mianotes"))
    first_path = str(note_pages[0]["path"]) if note_pages else ""
    if first_path:
        body = f'<a href="./{html.escape(first_path)}">Open documentation</a>'
        refresh = f'    <meta http-equiv="refresh" content="0; url=./{html.escape(first_path)}">\n'
    else:
        body = "<p>No notes were published.</p>"
        refresh = ""
    (version_dir / "index.html").write_text(
        (
            "<!doctype html>\n"
            '<html lang="en">\n'
            "  <head>\n"
            '    <meta charset="utf-8">\n'
            '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
            f"    {GENERATOR_META_TAG}\n"
            f"{refresh}"
            f"    <title>{brand} documentation</title>\n"
            "  </head>\n"
            f"  <body>{body}</body>\n"
            "</html>\n"
        ),
        encoding="utf-8",
    )


def html_shell(
    *,
    title: str,
    stylesheet: str,
    navigation_script: str,
    search_script: str,
    site_script: str,
    body: str,
) -> str:
    escaped_title = html.escape(title)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"    {GENERATOR_META_TAG}\n"
        f"    <title>{escaped_title}</title>\n"
        f'    <link rel="stylesheet" href="{html.escape(stylesheet)}">\n'
        f'    <script src="{html.escape(navigation_script)}" defer></script>\n'
        f'    <script src="{html.escape(search_script)}" defer></script>\n'
        f'    <script src="{html.escape(site_script)}" defer></script>\n'
        "  </head>\n"
        f"  <body>\n{body}  </body>\n"
        "</html>\n"
    )


def compact_text(markdown: str) -> str:
    text = re.sub(r"```.*?```", " ", markdown, flags=re.DOTALL)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", " ", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_`~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def json_for_script(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2).replace("</", "<\\/")


def markdown_to_html(markdown: str) -> str:
    blocks: list[str] = []
    paragraph: list[str] = []
    list_items: list[str] = []
    in_code = False
    code_lines: list[str] = []
    code_language = ""
    lines = markdown.splitlines()
    index = 0

    def flush_paragraph() -> None:
        if paragraph:
            blocks.append(f"<p>{inline_markdown(' '.join(paragraph))}</p>")
            paragraph.clear()

    def flush_list() -> None:
        if list_items:
            blocks.append(f"<ul>{''.join(list_items)}</ul>")
            list_items.clear()

    while index < len(lines):
        line = lines[index]
        stripped = line.strip()
        if stripped.startswith("```"):
            if in_code:
                blocks.append(code_block_to_html(chr(10).join(code_lines), code_language))
                in_code = False
                code_lines.clear()
                code_language = ""
            else:
                flush_paragraph()
                flush_list()
                in_code = True
                code_language = stripped.removeprefix("```").strip()
            index += 1
            continue
        if in_code:
            code_lines.append(line)
            index += 1
            continue
        if not stripped:
            flush_paragraph()
            flush_list()
            index += 1
            continue
        if is_table_start(lines, index):
            flush_paragraph()
            flush_list()
            table_lines = [line]
            index += 2
            while index < len(lines) and is_table_row(lines[index]):
                table_lines.append(lines[index])
                index += 1
            blocks.append(table_to_html(table_lines))
            continue
        if is_admonition_start(stripped):
            flush_paragraph()
            flush_list()
            admonition_lines = [line]
            index += 1
            while index < len(lines) and lines[index].strip().startswith(">"):
                admonition_lines.append(lines[index])
                index += 1
            blocks.append(admonition_to_html(admonition_lines))
            continue
        if is_directive_admonition_start(stripped):
            flush_paragraph()
            flush_list()
            admonition_lines = [line]
            index += 1
            while index < len(lines) and lines[index].strip() != ":::":
                admonition_lines.append(lines[index])
                index += 1
            if index < len(lines) and lines[index].strip() == ":::":
                index += 1
            blocks.append(directive_admonition_to_html(admonition_lines))
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            blocks.append(f"<h{level}>{inline_markdown(heading.group(2))}</h{level}>")
            index += 1
            continue
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            flush_paragraph()
            list_items.append(f"<li>{inline_markdown(bullet.group(1))}</li>")
            index += 1
            continue
        paragraph.append(stripped)
        index += 1

    flush_paragraph()
    flush_list()
    if in_code:
        blocks.append(code_block_to_html(chr(10).join(code_lines), code_language))
    return "\n".join(blocks)


def without_duplicate_title_heading(markdown: str, title: str) -> str:
    lines = markdown.splitlines()
    first_content_index = next(
        (index for index, line in enumerate(lines) if line.strip()),
        None,
    )
    if first_content_index is None:
        return markdown.strip()

    match = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", lines[first_content_index].strip())
    if not match:
        return markdown.strip()
    if normalised_heading_text(match.group(1)) != normalised_heading_text(title):
        return markdown.strip()
    return "\n".join(lines[first_content_index + 1 :]).strip()


def normalised_heading_text(value: str) -> str:
    text = re.sub(r"`([^`]+)`", r"\1", value)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"[*_~]+", "", text)
    return re.sub(r"\s+", " ", text).strip().casefold()


def is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and is_table_row(lines[index])
        and is_table_separator(lines[index + 1])
    )


def is_table_row(line: str) -> bool:
    stripped = line.strip()
    return "|" in stripped and stripped.startswith("|") and stripped.endswith("|")


def is_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not is_table_row(stripped):
        return False
    cells = table_cells(stripped)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def table_cells(line: str) -> list[str]:
    stripped = line.strip()
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]

    cells: list[str] = []
    cell: list[str] = []
    index = 0
    while index < len(stripped):
        char = stripped[index]
        if char == "\\" and index + 1 < len(stripped) and stripped[index + 1] == "|":
            cell.append("|")
            index += 2
            continue
        if char == "|":
            cells.append("".join(cell).strip())
            cell.clear()
            index += 1
            continue
        cell.append(char)
        index += 1
    cells.append("".join(cell).strip())
    return cells


def table_to_html(lines: list[str]) -> str:
    header_cells = table_cells(lines[0])
    body_rows = [table_cells(line) for line in lines[1:]]
    column_count = max(len(header_cells), *(len(row) for row in body_rows), 1)

    def padded(cells: list[str]) -> list[str]:
        return cells + [""] * (column_count - len(cells))

    header_html = "".join(f"<th>{inline_markdown(cell)}</th>" for cell in padded(header_cells))
    body_html = "".join(
        "<tr>" + "".join(f"<td>{inline_markdown(cell)}</td>" for cell in padded(row)) + "</tr>"
        for row in body_rows
    )
    columns_html = "".join("<col>" for _ in range(column_count))
    return (
        '<table class="doc-table">'
        f"<colgroup>{columns_html}</colgroup>"
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{body_html}</tbody>"
        "</table>"
    )


def code_block_to_html(code: str, language: str = "") -> str:
    language_class = f' class="language-{html.escape(language)}"' if language else ""
    return (
        '<div class="code-card">'
        f"<pre><code{language_class}>{highlight_code(code)}</code></pre>"
        "</div>"
    )


def highlight_code(code: str) -> str:
    escaped = html.escape(code)
    escaped = re.sub(
        r"(&quot;[^&]*&quot;)(\s*:)",
        r'<span class="tok-key">\1</span>\2',
        escaped,
    )
    escaped = re.sub(
        r"(:\s*)(&quot;[^&]*&quot;)",
        r'\1<span class="tok-string">\2</span>',
        escaped,
    )
    return escaped


def is_admonition_start(stripped: str) -> bool:
    return bool(re.match(r"^>\s*\[!(NOTE|TIP|INFO|IMPORTANT|WARNING|CAUTION|DANGER)\]", stripped, re.I))


def is_directive_admonition_start(stripped: str) -> bool:
    return bool(
        re.match(
            r"^:::\s*(NOTE|TIP|IMPORTANT|WARNING|CAUTION|DANGER|INFO)\b",
            stripped,
            re.I,
        )
    )


def admonition_to_html(lines: list[str]) -> str:
    first = lines[0].strip()
    match = re.match(
        r"^>\s*\[!(?P<kind>NOTE|TIP|INFO|IMPORTANT|WARNING|CAUTION|DANGER)\]\s*(?P<title>.*)$",
        first,
        re.I,
    )
    kind = normalise_admonition_kind((match.group("kind") if match else "note").lower())
    title = (match.group("title") if match else "").strip()
    body_lines = [strip_blockquote_marker(line) for line in lines[1:]]
    body = markdown_to_html("\n".join(body_lines).strip()) if body_lines else ""
    return render_admonition(kind=kind, title=title, body=body)


def directive_admonition_to_html(lines: list[str]) -> str:
    first = lines[0].strip()
    match = re.match(
        r"^:::\s*(?P<kind>NOTE|TIP|IMPORTANT|WARNING|CAUTION|DANGER|INFO)\b\s*(?P<title>.*)$",
        first,
        re.I,
    )
    kind = normalise_admonition_kind((match.group("kind") if match else "note").lower())
    title = directive_admonition_title((match.group("title") if match else "").strip())
    body = markdown_to_html("\n".join(lines[1:]).strip()) if len(lines) > 1 else ""
    return render_admonition(kind=kind, title=title, body=body)


def render_admonition(*, kind: str, title: str, body: str) -> str:
    title_html = ""
    if title:
        title_html = (
            '<div class="admonition-title"><span class="admonition-icon" aria-hidden="true"></span>'
            f"<strong>{inline_markdown(title)}</strong></div>"
        )
    return (
        f'<aside class="admonition admonition-{html.escape(kind)}">'
        f"{title_html}"
        f'<div class="admonition-body">{body}</div>'
        "</aside>"
    )


def normalise_admonition_kind(kind: str) -> str:
    return {
        "important": "info",
    }.get(kind, kind)


def directive_admonition_title(raw_title: str) -> str:
    title = raw_title.strip()
    if title.startswith("[") and "]" in title:
        title = title[1:title.index("]")].strip()
    if title.startswith("{"):
        title = ""
    return title


def strip_blockquote_marker(line: str) -> str:
    return re.sub(r"^>\s?", "", line)


def inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        r'<a class="inline-link" href="\2">\1</a>',
        escaped,
    )
    return escaped
