"""Small sidebar-edge toggle (not fixed at top of page)."""

import streamlit.components.v1 as components

_TOGGLE_HTML = """
<script>
(function () {
  const doc = window.parent.document;
  const ID = "resolveai-sidebar-toggle";

  doc.getElementById(ID)?.remove();

  const style = doc.createElement("style");
  style.id = "resolveai-sidebar-toggle-style";
  doc.getElementById("resolveai-sidebar-toggle-style")?.remove();
  style.textContent = `
    #${ID} {
      position: fixed !important;
      z-index: 10000000 !important;
      width: 30px !important;
      height: 30px !important;
      border-radius: 8px !important;
      border: 1px solid rgba(167, 139, 250, 0.4) !important;
      background: rgba(22, 22, 38, 0.96) !important;
      color: #e9d5ff !important;
      font-size: 14px !important;
      line-height: 1 !important;
      cursor: pointer !important;
      display: flex !important;
      align-items: center !important;
      justify-content: center !important;
      box-shadow: 0 4px 12px rgba(0, 0, 0, 0.35) !important;
      padding: 0 !important;
      margin: 0 !important;
      transition: left 0.2s ease, top 0.2s ease, background 0.2s ease !important;
    }
    #${ID}:hover {
      background: rgba(124, 58, 237, 0.85) !important;
      color: #fff !important;
    }
    [data-testid="stExpandSidebarButton"],
    [data-testid="stSidebarCollapseButton"] {
      opacity: 0 !important;
      pointer-events: none !important;
      width: 1px !important;
      height: 1px !important;
      overflow: hidden !important;
      position: absolute !important;
    }
  `;
  doc.head.appendChild(style);

  const btn = doc.createElement("button");
  btn.id = ID;
  btn.type = "button";
  btn.setAttribute("aria-label", "Toggle sidebar");

  function nativeToggle() {
    const selectors = [
      '[data-testid="stExpandSidebarButton"]',
      '[data-testid="stSidebarCollapseButton"] button',
      '[data-testid="stSidebarCollapseButton"]',
    ];
    for (const sel of selectors) {
      const el = doc.querySelector(sel);
      if (el) { el.click(); return true; }
    }
    return false;
  }

  function sidebarExpanded() {
    const sb = doc.querySelector('section[data-testid="stSidebar"]');
    return sb && sb.getAttribute("aria-expanded") !== "false";
  }

  function positionToggle() {
    const sb = doc.querySelector('section[data-testid="stSidebar"]');
    if (!sb) return;
    const r = sb.getBoundingClientRect();
    const open = sidebarExpanded();
    if (open && r.width > 80) {
      btn.style.left = Math.max(8, r.right - 38) + "px";
      btn.style.top = Math.max(12, r.top + 14) + "px";
      btn.innerHTML = "&#10005;";
      btn.title = "Close sidebar";
    } else {
      btn.style.left = "6px";
      btn.style.top = "72px";
      btn.innerHTML = "&#9776;";
      btn.title = "Open sidebar";
    }
  }

  btn.addEventListener("click", function (e) {
    e.preventDefault();
    e.stopPropagation();
    nativeToggle();
    setTimeout(positionToggle, 150);
    setTimeout(positionToggle, 450);
  });

  doc.body.appendChild(btn);
  positionToggle();
  window.addEventListener("resize", positionToggle);
  const obs = new MutationObserver(positionToggle);
  obs.observe(doc.body, {
    subtree: true,
    attributes: true,
    attributeFilter: ["aria-expanded", "style", "class"],
  });
  setInterval(positionToggle, 600);
})();
</script>
"""


def inject_sidebar_toggle() -> None:
    components.html(_TOGGLE_HTML, height=0)
