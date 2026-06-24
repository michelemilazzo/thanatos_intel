// Login chrome Thanatos (scoped al sito, non mmos_brand):
// - rietichetta MMOS ID; aggiunge azioni Home + Registrati organizzate, mobile-first.
(function () {
  if (!/^\/login/.test(location.pathname)) return;

  function relabelMmosId() {
    var btn = document.querySelector("a.btn-frappe");
    if (btn && !btn.dataset.mmosid) {
      btn.dataset.mmosid = "1";
      btn.textContent = "🔐 Accedi con MMOS ID";
      btn.style.fontWeight = "600";
    }
  }

  function injectStyle() {
    if (document.getElementById("thx-login-style")) return;
    var st = document.createElement("style");
    st.id = "thx-login-style";
    st.textContent =
      ".thx-login-actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:18px;}" +
      ".thx-login-actions a{flex:1 1 140px;text-align:center;padding:11px 14px;border-radius:8px;" +
      "font-size:13px;font-weight:600;text-decoration:none;transition:all .15s;box-sizing:border-box;}" +
      ".thx-btn-home{border:1px solid #d4d4d8;color:#52525b;background:#fff;}" +
      ".thx-btn-home:hover{border-color:#C8A96E;color:#9c7c3c;}" +
      ".thx-btn-signup{background:#C8A96E;color:#1a1f3a;border:1px solid #C8A96E;}" +
      ".thx-btn-signup:hover{background:#b8975a;}" +
      ".thx-login-hint{margin-top:14px;text-align:center;font-size:12.5px;color:#8a8a8a;}" +
      "@media(max-width:480px){.thx-login-actions a{flex:1 1 100%;}}";
    document.head.appendChild(st);
  }

  function inject() {
    relabelMmosId();
    injectStyle();
    if (document.getElementById("thx-login-actions")) return;
    var card =
      document.querySelector(".page-card-actions") ||
      document.querySelector(".for-login .page-card") ||
      document.querySelector(".login-content") ||
      document.querySelector("form");
    if (!card) return;
    var hint = document.createElement("div");
    hint.className = "thx-login-hint";
    hint.innerHTML = "Non hai ancora un account?";
    var wrap = document.createElement("div");
    wrap.id = "thx-login-actions";
    wrap.className = "thx-login-actions";
    wrap.innerHTML =
      '<a class="thx-btn-home" href="/">&larr; Home</a>' +
      '<a class="thx-btn-signup" href="/registrati">Registrati &rsaquo;</a>';
    card.parentNode.insertBefore(wrap, card.nextSibling);
    card.parentNode.insertBefore(hint, wrap);
  }

  if (document.readyState !== "loading") setTimeout(inject, 250);
  else
    document.addEventListener("DOMContentLoaded", function () {
      setTimeout(inject, 250);
    });
})();
