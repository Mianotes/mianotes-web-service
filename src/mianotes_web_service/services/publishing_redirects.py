from __future__ import annotations

import html

from mianotes_web_service.services.publishing_theme import GENERATOR_META_TAG

MIANOTES_MARK_SVG = (
    '<svg viewBox="0 0 25 25" aria-hidden="true" focusable="false">'
    "<defs>"
    '<linearGradient id="mianotes-redirect-a" x1="3.2" x2="11.1" y1="4.8" y2="20.6" gradientUnits="userSpaceOnUse">'
    '<stop stop-color="#ff1495"/><stop offset="1" stop-color="#7b1bff"/>'
    "</linearGradient>"
    '<linearGradient id="mianotes-redirect-b" x1="10.1" x2="18.1" y1="4.8" y2="20.6" gradientUnits="userSpaceOnUse">'
    '<stop stop-color="#ff42d2"/><stop offset="1" stop-color="#2239ff"/>'
    "</linearGradient>"
    '<linearGradient id="mianotes-redirect-c" x1="17.1" x2="24.8" y1="4.8" y2="20.6" gradientUnits="userSpaceOnUse">'
    '<stop stop-color="#15c7ff"/><stop offset="1" stop-color="#0a35be"/>'
    "</linearGradient>"
    "</defs>"
    '<path fill="url(#mianotes-redirect-a)" d="M3.2 4.5 10.6 12v10.2L3.2 15.1z"/>'
    '<path fill="url(#mianotes-redirect-b)" d="M10.1 4.5 17.6 12v10.2l-7.5-7.1z"/>'
    '<path fill="url(#mianotes-redirect-c)" d="M17.1 4.5 24.5 12v10.2l-7.4-7.1z"/>'
    "</svg>"
)

REDIRECT_STYLE = """
    <style>
      html,
      body {
        min-height: 100%;
        margin: 0;
      }

      body {
        display: grid;
        place-items: center;
        background: #ffffff;
        color: #4e505a;
        font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }

      .redirect-loader {
        display: grid;
        place-items: center;
        gap: 14px;
        padding: 32px;
        text-align: center;
      }

      .redirect-loader svg {
        width: 46px;
        height: 46px;
        animation: mia-logo-pulse 1.2s ease-in-out infinite;
      }

      .redirect-loader p {
        margin: 0;
        font-size: 14px;
        font-weight: 500;
      }

      .redirect-loader a {
        color: inherit;
        font-size: 13px;
      }

      @keyframes mia-logo-pulse {
        0%,
        100% {
          opacity: 0.72;
          transform: scale(0.98);
        }

        50% {
          opacity: 1;
          transform: scale(1);
        }
      }
    </style>
"""


def redirect_document(
    *,
    title: str,
    redirect_script: str,
    fallback_href: str,
    fallback_label: str = "Open documentation",
) -> str:
    escaped_title = html.escape(title)
    escaped_fallback_href = html.escape(fallback_href)
    escaped_fallback_label = html.escape(fallback_label)
    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "  <head>\n"
        '    <meta charset="utf-8">\n'
        '    <meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"    {GENERATOR_META_TAG}\n"
        f"    <title>{escaped_title}</title>\n"
        f"{REDIRECT_STYLE}"
        "  </head>\n"
        "  <body>\n"
        '    <main class="redirect-loader" aria-live="polite">\n'
        f"      {MIANOTES_MARK_SVG}\n"
        "      <p>Loading documentation...</p>\n"
        f'      <a href="{escaped_fallback_href}">{escaped_fallback_label}</a>\n'
        "    </main>\n"
        "    <script>\n"
        f"{redirect_script}"
        "    </script>\n"
        "  </body>\n"
        "</html>\n"
    )
