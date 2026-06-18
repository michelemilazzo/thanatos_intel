// Login chrome Thanatos (scoped al sito, non mmos_brand):
// - link "Crea un account" -> /registrati (pagina con i tipi account)
// Il bottone "MMOS ID" lo rende Frappe nativamente dal Social Login Key.
(function () {
  if (!/^\/login/.test(location.pathname)) return;

  function relabelMmosId() {
    // Il Social Login Key "frappe" punta all'IdP MMOS (id.onekeyco.com):
    // rietichetta il bottone "Login with Frappe" -> "Accedi con MMOS ID".
    var btn = document.querySelector("a.btn-frappe");
    if (btn && !btn.dataset.mmosid) {
      btn.dataset.mmosid = "1";
      btn.textContent = "🔐 Accedi con MMOS ID";
      btn.style.fontWeight = "600";
    }
  }

  function inject() {
    relabelMmosId();
    if (document.getElementById("thx-signup-link")) return;
    var card =
      document.querySelector(".page-card-actions") ||
      document.querySelector(".for-login .page-card") ||
      document.querySelector(".login-content") ||
      document.querySelector("form");
    if (!card) return;
    var wrap = document.createElement("div");
    wrap.id = "thx-signup-link";
    wrap.style.cssText =
      "margin-top:14px;text-align:center;font-size:13px;color:#777;";
    wrap.innerHTML =
      'Non hai un account? ' +
      '<a href="/registrati" style="color:#C8A96E;font-weight:700;text-decoration:none">' +
      'Crea un account &rsaquo;</a>';
    card.parentNode.insertBefore(wrap, card.nextSibling);
  }

  if (document.readyState !== "loading") setTimeout(inject, 250);
  else
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(inject, 250);
    });
})();
