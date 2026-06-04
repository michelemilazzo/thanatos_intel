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
});
