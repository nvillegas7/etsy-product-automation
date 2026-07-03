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
})();
