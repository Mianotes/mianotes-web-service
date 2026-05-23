# Parser and ingestion pipeline

Mianotes converts files and URLs into Markdown through an adapter-based parser layer.

The default adapter uses Microsoft MarkItDown. Mianotes adds local source storage, web-page cleanup, OCR fallback behaviour, and background job tracking around that parser boundary.

## Supported source types

The parser can handle common source types such as:

- office documents;
- PDFs;
- images;
- audio;
- HTML;
- text formats;
- archives;
- YouTube URLs and other URLs supported by the parser stack.

The file upload endpoint currently supports these extensions:

```text
.csv
.doc
.docx
.html
.htm
.jpeg
.jpg
.m4a
.md
.markdown
.mp3
.odt
.pdf
.png
.rtf
.tif
.tiff
.txt
.wav
```

## File ingestion

For normal file uploads:

1. The API receives file bytes.
2. Mianotes stores the original file inside the note's `sources/` directory.
3. Mianotes creates a note with status `pending_parse`.
4. Mianotes creates a `parse_file` job.
5. The parser converts the source to Markdown.
6. The note is updated when parsing succeeds.

Clients should poll the job endpoint until the job reaches `succeeded`.

## URL ingestion

For web pages:

1. Mianotes downloads HTML using a browser-like user agent.
2. The raw HTML is stored as the source file.
3. `trafilatura` extracts the main readable page content.
4. Mianotes passes a cleaned HTML document to MarkItDown.
5. If extraction fails, Mianotes falls back to the raw saved HTML file.

This removes most navigation menus, headers, footers, sidebars, comments, and page chrome while preserving useful links, images, and tables.

## Image ingestion

Image files are handled differently from PDFs and office documents.

Mianotes first runs MarkItDown's image converter so the source is handled by the same parser adapter as other files. It then tries local Tesseract OCR for:

```text
.jpg
.jpeg
.png
.tif
.tiff
```

Before using Tesseract, Mianotes checks that the binary can actually run. For screenshots and UI captures, it also runs a preprocessed OCR pass that increases contrast and image size before choosing the best OCR result.

When OpenAI is configured with a multimodal model, Mianotes can use a cloud image fallback only when Tesseract cannot extract useful text.

For PDFs, office files, spreadsheets, and presentations whose normal MarkItDown
conversion returns no text, Mianotes retries MarkItDown with plugins and the
configured LLM client. This enables OCR support from packages such as
`markitdown-ocr` without adding a new parser API surface.

If a file still cannot be parsed, Mianotes saves a friendly message instead of
an empty note:

```text
Mia could not extract readable text from this file with the built-in parser.

This file likely needs OCR or visual understanding. Connect Mia to a local or cloud model with vision/OCR support, then upload the file again.
```

If an image cannot be read locally and no OpenAI image fallback is configured,
Mianotes saves:

```text
Mia could not extract readable text from this image with the built-in parser.

Images like this usually need OCR or visual understanding. Connect Mia to a local or cloud model with vision/OCR support, then upload the image again.
```

## Audio and video

Install `ffmpeg` separately if you plan to parse audio or video sources.

## Parser design rule

Keep specialist parsers behind the same adapter boundary. The API contract should not change when a new local or hosted parser is added.
