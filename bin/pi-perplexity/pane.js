(() => {
  const op = String(window.__PIP_OP || "read");
  const promptText = String(window.__PIP_TEXT || "");

  const absUrl = () => location.href;
  const titleOf = () => {
    const h = document.querySelector("h1");
    const t = (h && h.innerText.trim()) || document.title || "Perplexity";
    return t.replace(/\s+/g, " ").trim();
  };

  const editors = () =>
    [...document.querySelectorAll(
      'textarea, [contenteditable="true"], [role="textbox"], div[data-lexical-editor="true"]'
    )];

  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 8 && r.height > 8 && st.visibility !== "hidden" && st.display !== "none";
  };

  const composer = () => {
    const ranked = editors()
      .filter(visible)
      .sort((a, b) => b.getBoundingClientRect().bottom - a.getBoundingClientRect().bottom);
    return ranked[0] || null;
  };

  const setComposer = (el, text) => {
    el.focus();
    if (el.tagName === "TEXTAREA" || el.tagName === "INPUT") {
      const proto = el.tagName === "TEXTAREA"
        ? window.HTMLTextAreaElement.prototype
        : window.HTMLInputElement.prototype;
      const desc = Object.getOwnPropertyDescriptor(proto, "value");
      if (desc && desc.set) desc.set.call(el, text);
      else el.value = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      return true;
    }
    try {
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
      return true;
    } catch (_e) {
      el.textContent = text;
      el.dispatchEvent(new InputEvent("input", { bubbles: true, data: text, inputType: "insertText" }));
      return true;
    }
  };

  const submitNear = (el) => {
    const root = el.closest("form") || el.parentElement || document;
    const buttons = [...root.querySelectorAll("button, [role='button']")];
    const hit = buttons.find((b) => {
      const label = ((b.getAttribute("aria-label") || "") + " " + (b.innerText || "")).toLowerCase();
      return /submit|send|ask|search|arrow|enter/.test(label) && visible(b) && !b.disabled;
    });
    if (hit) {
      hit.click();
      return "clicked";
    }
    el.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    el.dispatchEvent(new KeyboardEvent("keyup", { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    return "enter";
  };

  const asMarkdown = () => {
    const main = document.querySelector("main") || document.body;
    const clone = main.cloneNode(true);
    clone.querySelectorAll("nav, footer, script, style, svg, [role='navigation']").forEach((n) => n.remove());
    const lines = [];
    lines.push("# " + titleOf());
    lines.push("");
    lines.push("- url: " + absUrl());
    lines.push("- captured: " + new Date().toISOString());
    lines.push("");
    const blocks = [...clone.querySelectorAll("article, [data-testid], p, li, h1, h2, h3, pre")];
    const seen = new Set();
    const push = (prefix, text) => {
      const t = text.replace(/\s+/g, " ").trim();
      if (!t || t.length < 2 || seen.has(t)) return;
      seen.add(t);
      lines.push(prefix + t);
    };
    if (blocks.length) {
      for (const el of blocks) {
        const t = (el.innerText || "").trim();
        if (!t) continue;
        if (/^H[1-3]$/.test(el.tagName)) push("## ", t);
        else if (el.tagName === "PRE") {
          lines.push("");
          lines.push("```");
          lines.push(el.innerText.replace(/\s+$/g, ""));
          lines.push("```");
          lines.push("");
        } else if (el.tagName === "LI") push("- ", t);
        else push("", t);
      }
    } else {
      lines.push((clone.innerText || "").trim());
    }
    return lines.join("\n").replace(/\n{3,}/g, "\n\n");
  };

  if (op === "probe") {
    const ed = editors().filter(visible).map((el) => ({
      tag: el.tagName,
      role: el.getAttribute("role"),
      label: (el.getAttribute("aria-label") || el.getAttribute("placeholder") || "").slice(0, 80),
    }));
    return JSON.stringify({
      ok: true,
      url: absUrl(),
      title: titleOf(),
      editors: ed.slice(0, 8),
      textLen: ((document.querySelector("main") || document.body).innerText || "").length,
    });
  }

  if (op === "read" || op === "md") {
    return JSON.stringify({
      ok: true,
      url: absUrl(),
      title: titleOf(),
      markdown: asMarkdown(),
    });
  }

  if (op === "fill") {
    const el = composer();
    if (!el) return JSON.stringify({ ok: false, error: "no composer in this pane" });
    setComposer(el, promptText);
    return JSON.stringify({
      ok: true,
      url: absUrl(),
      title: titleOf(),
      submitted: false,
      dry: true,
      chars: promptText.length,
    });
  }

  if (op === "steer") {
    if (!promptText) return JSON.stringify({ ok: false, error: "empty steer text" });
    const el = composer();
    if (!el) return JSON.stringify({ ok: false, error: "no composer in this pane" });
    setComposer(el, promptText);
    const how = submitNear(el);
    return JSON.stringify({
      ok: true,
      url: absUrl(),
      title: titleOf(),
      submitted: how,
      chars: promptText.length,
    });
  }

  return JSON.stringify({ ok: false, error: "unknown op " + op });
})();
