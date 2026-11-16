// Exam countdown. Display only: the server owns the deadline and scores late attempts.
// At 0:00 it submits the page's form with go=submit (save the current answer, then score).
(function () {
  var el = document.getElementById("timer");
  if (!el) return;
  var end = Date.now() + Number(el.dataset.remaining) * 1000;
  var form = document.getElementById(el.dataset.form);
  var pad = function (n) { return String(n).padStart(2, "0"); };

  function tick() {
    var left = Math.max(0, Math.ceil((end - Date.now()) / 1000));
    var h = Math.floor(left / 3600), m = Math.floor(left % 3600 / 60), s = left % 60;
    el.textContent = (h ? h + ":" + pad(m) : m) + ":" + pad(s);
    if (left <= 60) el.classList.add("low");
    if (left === 0) {
      clearInterval(timer);
      if (form) {
        var go = document.createElement("input");
        go.type = "hidden"; go.name = "go"; go.value = "submit";
        form.appendChild(go);
        form.submit();
      }
    }
  }
  var timer = setInterval(tick, 1000);
  tick();
})();
