// Kichik yordamchi skript (inline handlerlar o'rniga: qat'iy Content-Security-Policy uchun)
document.addEventListener("submit", function (event) {
  var submitter = event.submitter && event.submitter.dataset ? event.submitter.dataset.confirm : null;  // tugmaning o'z so'rovi
  var message = submitter || (event.target.dataset ? event.target.dataset.confirm : null);
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

// Jonli yangilanish: sahifani qayta yuklamasdan yangi buyurtmalar va holat o'zgarishlarini ko'rsatadi
(function () {
  var shell = document.querySelector(".shell[data-live-url]");
  if (!shell || !window.fetch) return;
  var url = shell.dataset.liveUrl;
  var after = parseInt(shell.dataset.liveAfter || "0", 10) || 0;
  var token = shell.dataset.liveToken || "";
  var baseTitle = document.title.replace(/^\(\d+\)\s*/, "");
  var delay = 5000;
  var timer = null;
  var stopped = false;
  var area = document.querySelector("[data-live-area]");
  var toasts = document.getElementById("toasts");

  function setBadge(count) {
    var link = document.querySelector(".sb-nav a[title='Buyurtmalar']");
    if (!link) return;
    var badge = link.querySelector(".count");
    if (count > 0) {
      if (!badge) {
        badge = document.createElement("span");
        badge.className = "count";
        badge.title = "Yangi buyurtmalar";
        link.appendChild(badge);
      }
      badge.textContent = String(count);
    } else if (badge) {
      badge.remove();
    }
    document.title = count > 0 ? "(" + count + ") " + baseTitle : baseTitle;
  }

  function toast(order) {
    if (!toasts) return;
    var a = document.createElement("a");
    a.className = "toast";
    a.href = order.url;
    var strong = document.createElement("strong");
    strong.textContent = "Yangi buyurtma #" + order.id;
    var span = document.createElement("span");
    span.textContent = order.name + " · " + String(order.total).replace(/\B(?=(\d{3})+(?!\d))/g, " ") + " so'm";
    a.appendChild(strong);
    a.appendChild(span);
    toasts.appendChild(a);
    window.setTimeout(function () { a.classList.add("out"); window.setTimeout(function () { a.remove(); }, 400); }, 9000);
    while (toasts.children.length > 4) toasts.firstChild.remove();
  }

  function busy() {
    var el = document.activeElement;
    return !!(area && el && area.contains(el) && el.matches("input, select, textarea"));
  }

  function refreshArea() {
    if (!area || busy()) return Promise.resolve(false);
    return fetch(window.location.href, { credentials: "same-origin", headers: { "X-Requested-With": "live" } })
      .then(function (r) { return r.ok && !r.redirected ? r.text() : null; })
      .then(function (html) {
        if (!html) return false;
        var fresh = new DOMParser().parseFromString(html, "text/html").querySelector("[data-live-area]");
        if (!fresh) return false;
        area.innerHTML = fresh.innerHTML;
        return true;
      })
      .catch(function () { return false; });
  }

  function tick() {
    if (stopped) return;
    if (document.hidden) { schedule(); return; }
    fetch(url + "?after=" + after, { credentials: "same-origin", headers: { "X-Requested-With": "live", "Accept": "application/json" } })
      .then(function (r) {
        if (r.redirected || r.status === 401 || r.status === 403) { stopped = true; return null; }  // seans tugagan
        if (!r.ok) throw new Error("http " + r.status);
        return r.json();
      })
      .then(function (data) {
        if (!data) return;
        delay = 5000;
        data.fresh.forEach(toast);
        if (data.last_id > after) after = data.last_id;
        setBadge(data.new);
        if (data.token !== token) {
          refreshArea().then(function (ok) { if (ok || !area) token = data.token; });  // band bo'lsa keyingi safar qayta uriniladi
        }
      })
      .catch(function () { delay = Math.min(delay * 2, 60000); })
      .then(schedule);
  }

  function schedule() {
    if (stopped) return;
    window.clearTimeout(timer);
    timer = window.setTimeout(tick, delay);
  }

  document.addEventListener("visibilitychange", function () { if (!document.hidden) { window.clearTimeout(timer); tick(); } });
  schedule();
})();
