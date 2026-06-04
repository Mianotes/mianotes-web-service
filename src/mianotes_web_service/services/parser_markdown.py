from __future__ import annotations

import re
import textwrap

IMAGE_DESCRIPTION_HEADING = "# Description:"
FENCED_CODE_BLOCK_PATTERN = re.compile(r"(```.*?```|~~~.*?~~~)", re.DOTALL)
MARKITDOWN_OCR_BLOCK_PATTERN = re.compile(
    r"\*?\[Image OCR\]\s*"
    r"```(?:markdown|md|text)?\s*\n"
    r"(?P<body>.*?)"
    r"\n```\s*"
    r"\[End OCR\]\*?",
    re.IGNORECASE | re.DOTALL,
)
MARKITDOWN_OCR_MARKER_LINE_PATTERN = re.compile(
    r"^\*?\[(?:Image OCR|End OCR)\]\*?\s*\n?",
    re.IGNORECASE | re.MULTILINE,
)
HTML_VOID_TAG_PATTERN = re.compile(
    r"<(?P<tag>area|base|br|col|embed|hr|img|input|link|meta|param|source|track|wbr)"
    r"(?P<attrs>\s[^<>]*?)?\s*/?>",
    re.IGNORECASE,
)
HTML_TAG_NAMES = frozenset(
    {
        "a",
        "abbr",
        "address",
        "article",
        "aside",
        "b",
        "base",
        "blockquote",
        "br",
        "caption",
        "cite",
        "code",
        "col",
        "colgroup",
        "dd",
        "del",
        "details",
        "div",
        "dl",
        "dt",
        "em",
        "figcaption",
        "figure",
        "footer",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "header",
        "hr",
        "i",
        "iframe",
        "img",
        "input",
        "ins",
        "kbd",
        "li",
        "link",
        "main",
        "mark",
        "meta",
        "nav",
        "object",
        "ol",
        "p",
        "param",
        "pre",
        "q",
        "s",
        "samp",
        "section",
        "small",
        "source",
        "span",
        "strong",
        "sub",
        "summary",
        "sup",
        "table",
        "tbody",
        "td",
        "tfoot",
        "th",
        "thead",
        "track",
        "tr",
        "u",
        "ul",
        "var",
    }
)
HTML_TAG_PATTERN = re.compile(
    r"</?(?P<tag>[A-Za-z][A-Za-z0-9-]*)(?=[\s>/])[^<>]*?>"
)
AUTOLINK_PATTERN = re.compile(
    r"<(?:[A-Za-z][A-Za-z0-9+.-]{1,31}:[^\s<>]*|"
    r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+)>"
)
ACCIDENTAL_TEXT_DIRECTIVE_PATTERN = re.compile(r"(?<![\\:]):(?=[A-Za-z])")
STANDALONE_PAGE_HEADING_PATTERN = re.compile(r"^#{0,6}\s*Page\s+\d+\s*$", re.IGNORECASE)


def normalise_image_markdown(text: str) -> str | None:
    if IMAGE_DESCRIPTION_HEADING not in text:
        return None
    description = text.split(IMAGE_DESCRIPTION_HEADING, 1)[1].strip()
    description = strip_outer_markdown_fence(description)
    return description or None


def strip_outer_markdown_fence(text: str) -> str:
    match = re.fullmatch(
        r"```(?:markdown|md|text)?\s*\n(?P<body>.*?)\n```",
        text.strip(),
        re.DOTALL,
    )
    if match is None:
        return text.strip()
    return match.group("body").strip()


def normalise_ocr_text(text: str) -> str:
    text = strip_outer_markdown_fence(text)
    text = textwrap.dedent(text).strip()
    lines = [line.rstrip() for line in text.splitlines()]
    if not lines:
        return ""

    indented_lines = [line for line in lines if line.startswith(("    ", "\t"))]
    non_empty_lines = [line for line in lines if line.strip()]
    if non_empty_lines and len(indented_lines) / len(non_empty_lines) >= 0.5:
        lines = [line.lstrip() if line.strip() else line for line in lines]

    return "\n".join(lines).strip()


def normalise_document_ocr_markdown(text: str) -> str:
    def replace_block(match: re.Match[str]) -> str:
        return f"\n\n{strip_outer_markdown_fence(match.group('body'))}\n\n"

    cleaned, replacements = MARKITDOWN_OCR_BLOCK_PATTERN.subn(replace_block, text)
    cleaned, marker_replacements = MARKITDOWN_OCR_MARKER_LINE_PATTERN.subn("", cleaned)
    if replacements == 0 and marker_replacements == 0:
        return text

    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def remove_standalone_page_headings(text: str) -> str:
    parts = FENCED_CODE_BLOCK_PATTERN.split(text)
    removed_count = 0
    for index, part in enumerate(parts):
        if index % 2 == 0:
            lines = []
            for line in part.splitlines():
                if STANDALONE_PAGE_HEADING_PATTERN.fullmatch(line.strip()):
                    removed_count += 1
                    continue
                lines.append(line)
            parts[index] = "\n".join(lines)
    if removed_count == 0:
        return text
    return re.sub(r"\n{3,}", "\n\n", "".join(parts)).strip()


def normalise_html_void_tags(text: str) -> str:
    def replace_tag(match: re.Match[str]) -> str:
        attrs = (match.group("attrs") or "").rstrip()
        return f"<{match.group('tag').lower()}{attrs} />"

    parts = FENCED_CODE_BLOCK_PATTERN.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = HTML_VOID_TAG_PATTERN.sub(replace_tag, part)
    return "".join(parts)


def escape_mdx_unsafe_angle_brackets(text: str) -> str:
    parts = FENCED_CODE_BLOCK_PATTERN.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = _escape_mdx_unsafe_angle_brackets_in_markdown(part)
    return "".join(parts)


def escape_mdx_unsafe_directives(text: str) -> str:
    parts = FENCED_CODE_BLOCK_PATTERN.split(text)
    for index, part in enumerate(parts):
        if index % 2 == 0:
            parts[index] = ACCIDENTAL_TEXT_DIRECTIVE_PATTERN.sub(r"\\:", part)
    return "".join(parts)


def _escape_mdx_unsafe_angle_brackets_in_markdown(text: str) -> str:
    output: list[str] = []
    index = 0
    while index < len(text):
        if text[index] != "<":
            output.append(text[index])
            index += 1
            continue

        autolink = AUTOLINK_PATTERN.match(text, index)
        if autolink is not None:
            output.append(autolink.group(0))
            index = autolink.end()
            continue

        html_tag = HTML_TAG_PATTERN.match(text, index)
        if html_tag is not None:
            tag = html_tag.group("tag").lower()
            if tag in HTML_TAG_NAMES:
                output.append(html_tag.group(0))
            else:
                output.append(_escape_angle_brackets(html_tag.group(0)))
            index = html_tag.end()
            continue

        output.append("&lt;")
        index += 1

    return "".join(output)


def _escape_angle_brackets(text: str) -> str:
    return text.replace("<", "&lt;").replace(">", "&gt;")


def normalise_parsed_markdown(text: str) -> str:
    return escape_mdx_unsafe_directives(
        escape_mdx_unsafe_angle_brackets(
            normalise_html_void_tags(normalise_document_ocr_markdown(text))
        )
    )
