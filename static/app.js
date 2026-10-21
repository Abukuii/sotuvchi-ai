// Kichik yordamchi skript (inline handlerlar o'rniga: qat'iy Content-Security-Policy uchun)
document.addEventListener("submit", function (event) {
  var message = event.target.dataset ? event.target.dataset.confirm : null;
  if (message && !window.confirm(message)) {
    event.preventDefault();
  }
});
document.addEventListener("change", function (event) {
  var el = event.target;
  if (el.matches && el.matches("[data-autosubmit]") && el.form) {
    el.form.submit();
  }
});

// Yon panel: kompyuterda yig'iladi/kengayadi (holat eslab qolinadi), telefonda chiqib turadigan menyu
(function () {
  var body = document.body;
  if (!body.classList.contains("has-sidebar")) return;
  var KEY = "sidebar-collapsed";
  var mobile = window.matchMedia("(max-width: 860px)");
  var scrim = document.querySelector(".scrim");
  var toggle = document.querySelector("[data-sidebar-toggle]");
  var opener = document.querySelector("[data-sidebar-open]");

  function read() { try { return window.localStorage.getItem(KEY) === "1"; } catch (e) { return false; } }
  function save(value) { try { window.localStorage.setItem(KEY, value ? "1" : "0"); } catch (e) { /* xotira yopiq bo'lishi mumkin */ } }

  function setCollapsed(value, persist) {
    body.classList.toggle("sb-collapsed", value);
    if (toggle) {
      toggle.setAttribute("aria-expanded", value ? "false" : "true");
      toggle.setAttribute("aria-label", value ? "Menyuni kengaytirish" : "Menyuni yig'ish");
    }
    if (persist) save(value);
  }
  function setOpen(value) {
    body.classList.toggle("sb-open", value);
    if (scrim) scrim.hidden = !value;
    if (opener) opener.setAttribute("aria-expanded", value ? "true" : "false");
  }

  body.classList.add("no-anim");
  setCollapsed(!mobile.matches && read(), false);
  window.requestAnimationFrame(function () { body.classList.remove("no-anim"); });

  document.addEventListener("click", function (event) {
    var t = event.target.closest ? event.target.closest("[data-sidebar-toggle],[data-sidebar-open],[data-sidebar-close],.sb-nav a") : null;
    if (!t) return;
    if (t.matches("[data-sidebar-toggle]")) {
      if (mobile.matches) setOpen(false); else setCollapsed(!body.classList.contains("sb-collapsed"), true);
    } else if (t.matches("[data-sidebar-open]")) {
      setOpen(true);
    } else {
      setOpen(false);
    }
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && body.classList.contains("sb-open")) { setOpen(false); if (opener) opener.focus(); }
  });
  var onChange = function () { setOpen(false); setCollapsed(!mobile.matches && read(), false); };
  if (mobile.addEventListener) mobile.addEventListener("change", onChange); else mobile.addListener(onChange);
})();
