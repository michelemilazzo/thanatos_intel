// Defensive patches against legacy ERPNext sidebar crashes when apps installed
// without app_logo_url (blog, drive, builder, webshop, crm, wiki, etc.).
frappe.after_ajax(() => {
  try {
    if (frappe.ui && frappe.ui.Sidebar && frappe.ui.Sidebar.prototype) {
      const _setup = frappe.ui.Sidebar.prototype.setup;
      frappe.ui.Sidebar.prototype.setup = function (workspace_title) {
        if (!workspace_title || typeof workspace_title !== "string") return;
        return _setup.call(this, workspace_title);
      };
    }
  } catch (e) { /* noop */ }

  // Strip "/undefined" images from the sidebar dropdown so the browser
  // doesn't fire a 404 each render.
  const sanitize = () => {
    document.querySelectorAll('img[src$="/undefined"], img[src="undefined"]').forEach((img) => {
      img.removeAttribute("src");
      img.style.display = "none";
    });
  };
  sanitize();
  new MutationObserver(sanitize).observe(document.body, { childList: true, subtree: true });

  // ── Pulsante fisso "Home Thanatos" nella navbar (porta sempre al workspace) ──
  const HOME_ROUTE = "thanatos-intel";
  function goHome(e) {
    if (e) { e.preventDefault(); e.stopPropagation(); }
    try { frappe.set_route(HOME_ROUTE); } catch (err) { window.location.href = "/app/" + HOME_ROUTE; }
  }
  function ensureHomeBtn() {
    const nav = document.querySelector("header.navbar .container") || document.querySelector("header.navbar");
    if (!nav) return;
    if (document.getElementById("thanatos-home-btn")) return;
    const brand = nav.querySelector(".navbar-brand.navbar-home") || nav.querySelector(".navbar-brand");
    const a = document.createElement("a");
    a.id = "thanatos-home-btn";
    a.href = "/app/" + HOME_ROUTE;
    a.title = "Home Thanatos Intel";
    a.innerHTML = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="margin-right:6px"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg><span>Home</span>';
    a.addEventListener("click", goHome);
    if (brand && brand.parentNode) brand.parentNode.insertBefore(a, brand.nextSibling);
    else nav.insertBefore(a, nav.firstChild);
  }
  ensureHomeBtn();
  new MutationObserver(ensureHomeBtn).observe(document.body, { childList: true, subtree: true });

});
