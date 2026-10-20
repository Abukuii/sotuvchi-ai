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
