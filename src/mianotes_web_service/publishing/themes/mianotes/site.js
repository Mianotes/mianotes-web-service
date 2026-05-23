const folderSequence = (DOCS.groups || []).map((group) =>
  (group.items || []).filter((item) => !item.trailing)
);
const articleSequence = folderSequence.flat();

function normalizePath(path) {
  return String(path || "").replace(/^\.\//, "").replace(/^output\//, "");
}

function currentVersion() {
  const pathParts = decodeURIComponent(window.location.pathname).split("/").filter(Boolean);
  const versions = SITE_NAVIGATION?.navigation || [];
  const match = versions.find((item) => pathParts.includes(item.key));
  return match?.key || SITE_NAVIGATION?.latest || "";
}

function currentRelativePath() {
  const pathParts = decodeURIComponent(window.location.pathname).split("/").filter(Boolean);
  const version = currentVersion();
  const versionIndex = pathParts.indexOf(version);
  if (versionIndex >= 0) {
    return normalizePath(pathParts.slice(versionIndex + 1).join("/") || "index.html");
  }
  return normalizePath(pathParts.slice(-2).join("/") || "index.html");
}

function rootPrefix() {
  const rel = currentRelativePath();
  const depth = Math.max(0, rel.split("/").length - 1);
  return "../".repeat(depth);
}

function outputRootPrefix() {
  return `${rootPrefix()}../`;
}

function hrefFor(path) {
  return rootPrefix() + normalizePath(path);
}

function versionHrefFor(item) {
  return outputRootPrefix() + normalizePath(item.path);
}

function firstArticlePath() {
  return articleSequence[0]?.path || "index.html";
}

function iconSearch() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="11" cy="11" r="7"></circle><path d="m20 20-3.5-3.5"></path></svg>`;
}

function iconDocument() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H7a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V7z"></path><path d="M14 2v5h5"></path><path d="M9 13h6"></path><path d="M9 17h6"></path><path d="M9 9h1"></path></svg>`;
}

function iconCopy() {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>`;
}

function htmlEscape(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#039;"
  }[char]));
}

function renderHeader() {
  const header = document.querySelector("[data-header]");
  if (!header) return;

  const configuredLinks = Array.isArray(SITE_CONFIGURATION?.headerLinks)
    ? SITE_CONFIGURATION.headerLinks
    : [];
  const externalLinks = configuredLinks.map((item) => `
    <a href="${htmlEscape(item.url)}" target="_blank" rel="noreferrer">${htmlEscape(item.title)}</a>
  `).join("");
  const versionLinks = (SITE_NAVIGATION?.navigation || []).map((item) => {
    const active = currentVersion() === item.key;
    return `<a class="${active ? "active" : ""}" href="${versionHrefFor(item)}">${htmlEscape(item.label)}</a>`;
  }).join("");
  const brand = htmlEscape(SITE_CONFIGURATION?.brand || "mianotes");

  header.innerHTML = `
    <div class="topbar">
      <a class="brand" href="${hrefFor(firstArticlePath())}" aria-label="${brand} documentation home">
        <span class="brand-word">${brand}</span>
      </a>
      <div class="search-wrap">
        <label class="search-field" for="site-search">
          ${iconSearch()}
          <input id="site-search" type="search" autocomplete="off" placeholder="Search..." aria-label="Search documentation">
          <span class="search-key">⌘K</span>
        </label>
        <div class="search-panel" id="search-panel" hidden></div>
      </div>
    </div>
    <nav class="primary-nav" aria-label="Primary">
      ${externalLinks}
      ${versionLinks}
    </nav>
  `;
}

function renderSidebar() {
  const sidebar = document.querySelector("[data-sidebar]");
  if (!sidebar) return;
  const current = currentRelativePath();
  sidebar.innerHTML = (DOCS.groups || []).map((group) => `
    <section class="sidebar-group" aria-label="${htmlEscape(group.title)}">
      <h2 class="sidebar-heading">${htmlEscape(group.title)}</h2>
      ${(group.items || []).map((item) => {
        const active = !item.trailing && normalizePath(item.path) === current;
        return `<a class="sidebar-link ${active ? "active" : ""}" href="${hrefFor(item.path)}"><span>${htmlEscape(item.title)}</span>${item.trailing ? '<span class="chevron">›</span>' : ""}</a>`;
      }).join("")}
    </section>
  `).join("");
}

function findArticle(path) {
  const normalized = normalizePath(path);
  for (let groupIndex = 0; groupIndex < folderSequence.length; groupIndex += 1) {
    const folder = folderSequence[groupIndex];
    const itemIndex = folder.findIndex((item) => normalizePath(item.path) === normalized);
    if (itemIndex !== -1) {
      return { groupIndex, itemIndex, item: folder[itemIndex] };
    }
  }
  return null;
}

function adjacentArticles() {
  const found = findArticle(currentRelativePath());
  if (!found) return { prev: null, next: null };
  const folder = folderSequence[found.groupIndex];
  let prev = null;
  let next = null;

  if (found.itemIndex === 0) {
    const previousFolder = folderSequence[found.groupIndex - 1];
    prev = previousFolder ? previousFolder[0] : null;
  } else {
    prev = folder[found.itemIndex - 1];
  }

  if (found.itemIndex === folder.length - 1) {
    const nextFolder = folderSequence[found.groupIndex + 1];
    next = nextFolder ? nextFolder[0] : null;
  } else {
    next = folder[found.itemIndex + 1];
  }

  return { prev, next };
}

function renderArticleFooter() {
  const footer = document.querySelector("[data-article-footer]");
  if (!footer) return;
  const { prev, next } = adjacentArticles();
  footer.innerHTML = `
    <div>${prev ? `<a class="page-link prev" href="${hrefFor(prev.path)}"><span class="arrow">‹</span><span>${htmlEscape(prev.title)}</span></a>` : ""}</div>
    <div>${next ? `<a class="page-link next" href="${hrefFor(next.path)}"><span>${htmlEscape(next.title)}</span><span class="arrow">›</span></a>` : ""}</div>
  `;
}

function excerpt(text, query) {
  const compact = String(text || "").replace(/\s+/g, " ").trim();
  const lower = compact.toLowerCase();
  const q = query.toLowerCase();
  const index = lower.indexOf(q);
  const start = Math.max(0, index - 28);
  const slice = compact.slice(start, start + 154);
  return `${start > 0 ? "..." : ""}${slice}${start + 154 < compact.length ? "..." : ""}`;
}

function resultScore(item, query) {
  const q = query.toLowerCase();
  const title = String(item.title || "").toLowerCase();
  const folder = String(item.folder || "").toLowerCase();
  const section = String(item.section || "").toLowerCase();
  const text = String(item.text || "").toLowerCase();
  let score = 0;
  if (title.includes(q)) score += 8;
  if (folder.includes(q) || section.includes(q)) score += 4;
  if (text.includes(q)) score += 2;
  for (const word of q.split(/\s+/).filter(Boolean)) {
    if (title.includes(word)) score += 4;
    if (text.includes(word)) score += 1;
  }
  return score;
}

function renderSearchResults(query) {
  const panel = document.getElementById("search-panel");
  if (!panel) return;
  const trimmed = query.trim();
  if (trimmed.length < 3) {
    panel.hidden = true;
    panel.innerHTML = "";
    return;
  }

  const results = SEARCH_INDEX
    .map((item) => ({ item, score: resultScore(item, trimmed) }))
    .filter((entry) => entry.score > 0)
    .sort((a, b) => b.score - a.score)
    .slice(0, 6)
    .map((entry) => entry.item);

  panel.hidden = false;
  if (!results.length) {
    panel.innerHTML = `<div class="search-empty">No articles found for “${htmlEscape(trimmed)}”.</div>`;
    return;
  }

  panel.innerHTML = results.map((item) => `
    <a class="result" href="${hrefFor(item.path)}">
      <span class="result-icon">${iconDocument()}</span>
      <span>
        <span class="result-path">${htmlEscape(item.section)} › ${htmlEscape(item.folder)}</span>
        <span class="result-title">${htmlEscape(item.title)}</span>
        <span class="result-excerpt">${htmlEscape(excerpt(item.text, trimmed))}</span>
      </span>
    </a>
  `).join("");
}

function bindSearch() {
  const input = document.getElementById("site-search");
  const panel = document.getElementById("search-panel");
  if (!input || !panel) return;

  input.addEventListener("input", () => renderSearchResults(input.value));
  input.addEventListener("focus", () => renderSearchResults(input.value));

  document.addEventListener("keydown", (event) => {
    if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
      event.preventDefault();
      input.focus();
      input.select();
    }
    if (event.key === "Escape") {
      panel.hidden = true;
      input.blur();
    }
  });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".search-wrap")) {
      panel.hidden = true;
    }
  });
}

function bindCopyButtons() {
  for (const codeCard of document.querySelectorAll(".code-card")) {
    const pre = codeCard.querySelector("pre");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "copy-button";
    button.setAttribute("aria-label", "Copy code");
    button.innerHTML = iconCopy();
    button.addEventListener("click", async () => {
      const text = pre ? pre.innerText : "";
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        const range = document.createRange();
        range.selectNodeContents(pre);
        const selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
      }
    });
    codeCard.append(button);
  }
}

renderHeader();
renderSidebar();
renderArticleFooter();
bindSearch();
bindCopyButtons();
