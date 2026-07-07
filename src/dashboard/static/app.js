// Product Studio — minimal client-side behavior (toast dismissal only).
(function () {
  "use strict";

  document.querySelectorAll(".toast-close").forEach(function (button) {
    button.addEventListener("click", function () {
      button.closest(".toast").remove();
    });
  });

  // Auto-dismiss success/info toasts after 6 seconds; keep errors visible.
  window.setTimeout(function () {
    document
      .querySelectorAll(".toast-success, .toast-info")
      .forEach(function (toast) {
        toast.style.transition = "opacity 0.4s ease";
        toast.style.opacity = "0";
        window.setTimeout(function () {
          toast.remove();
        }, 400);
      });
  }, 6000);

  // --- Generation shadow: poll while a run is in flight, reload when done ---
  (function () {
    var status = document.getElementById("gen-status");
    if (!status || status.dataset.generating !== "true") return;
    var ticks = 0;
    var timer = window.setInterval(function () {
      ticks += 1;
      if (ticks > 80) { window.clearInterval(timer); return; } // ~4 min safety
      fetch("/api/status", { headers: { Accept: "application/json" } })
        .then(function (r) { return r.json(); })
        .then(function (s) {
          if (!s.generating) {
            window.clearInterval(timer);
            window.location.reload();
          }
        })
        .catch(function () {});
    }, 3000);
  })();

  // --- Keyboard shortcuts for fast reviewing on the product grid ---
  (function () {
    var cards = Array.prototype.slice.call(
      document.querySelectorAll(".grid .card:not(.card-shadow)")
    );
    if (!cards.length) return;
    var i = -1;

    function focus(next) {
      if (i >= 0 && cards[i]) cards[i].classList.remove("card-focus");
      i = Math.max(0, Math.min(cards.length - 1, next));
      cards[i].classList.add("card-focus");
      cards[i].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    document.addEventListener("keydown", function (e) {
      var t = e.target;
      if (t && (t.matches("input, textarea, select") || t.isContentEditable)) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      var card = i >= 0 ? cards[i] : null;
      switch (e.key) {
        case "j": focus(i + 1); e.preventDefault(); break;
        case "k": focus(i < 0 ? 0 : i - 1); e.preventDefault(); break;
        case "o":
        case "Enter": {
          if (!card) { focus(0); break; }
          var link = card.querySelector(".card-title a") || card.querySelector("a.thumb");
          if (link) link.click();
          break;
        }
        case "a": {
          if (!card) break;
          var ok = card.querySelector("form[action*='/approve'] button");
          if (ok) ok.click();
          break;
        }
        case "r": {
          if (!card) break;
          var rej = card.querySelector(".card-reject-link");
          if (rej) rej.click();
          break;
        }
      }
    });
  })();
})();
