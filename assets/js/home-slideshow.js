/**
 * Home page carousel: cross-fade slides, auto-advance, prev/next.
 */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.getElementById("home-slideshow");
    if (!root || root.getAttribute("data-slideshow-ready") === "true") return;
    root.setAttribute("data-slideshow-ready", "true");

    var viewport = root.querySelector(".home-slideshow__viewport");
    var slides = root.querySelectorAll(".home-slideshow__slide");
    var prevBtn = root.querySelector("[data-home-slideshow-prev]");
    var nextBtn = root.querySelector("[data-home-slideshow-next]");
    var n = slides.length;
    if (!viewport || n === 0) return;
    /* Single static slide: markup already marks .is-active */
    if (n === 1) return;
    if (!prevBtn || !nextBtn) return;

    var intervalMs = parseInt(root.getAttribute("data-interval") || "6500", 10);
    if (intervalMs < 2000) intervalMs = 2000;

    var index = 0;
    var timer = null;
    var reducedMotion =
      window.matchMedia &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    function show(i) {
      index = ((i % n) + n) % n;
      slides.forEach(function (el, j) {
        var on = j === index;
        el.classList.toggle("is-active", on);
        el.setAttribute("aria-hidden", on ? "false" : "true");
      });
    }

    function goNext() {
      show(index + 1);
    }

    function goPrev() {
      show(index - 1);
    }

    function stopAuto() {
      if (timer !== null) {
        clearInterval(timer);
        timer = null;
      }
    }

    function startAuto() {
      if (reducedMotion) return;
      stopAuto();
      timer = window.setInterval(goNext, intervalMs);
    }

    prevBtn.addEventListener("click", function () {
      goPrev();
      startAuto();
    });
    nextBtn.addEventListener("click", function () {
      goNext();
      startAuto();
    });

    root.addEventListener("mouseenter", stopAuto);
    root.addEventListener("mouseleave", startAuto);
    root.addEventListener("focusin", stopAuto);
    root.addEventListener("focusout", function (ev) {
      if (!root.contains(ev.relatedTarget)) startAuto();
    });

    viewport.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowLeft") {
        ev.preventDefault();
        goPrev();
        startAuto();
      } else if (ev.key === "ArrowRight") {
        ev.preventDefault();
        goNext();
        startAuto();
      }
    });

    show(0);
    startAuto();
  });
})();
