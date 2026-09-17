/* ==========================================================================
   Header submenus

   One entry in the header (Research) opens a menu instead of going somewhere.
   The markup is in _includes/masthead.html; this file decides when it is open.

   Two constraints shaped it:

   - greedy-nav moves whole <li> elements between .visible-links and
     .hidden-links as the window resizes. Listeners bound to the <li> survive
     the move, because the element itself is moved rather than re-created, so
     the handlers are bound once at load and never re-bound.
   - The class on the <li> is the single source of truth for open/closed, hover
     included. Letting CSS :hover open the menu as well would leave the class
     and what is on screen disagreeing after a click.
   ========================================================================== */

(function () {
  var nav = document.getElementById("site-nav");
  if (!nav) return;

  var groups = nav.querySelectorAll(".masthead__menu-item--group");
  if (!groups.length) return;

  /* Hover is for a mouse. On a touch screen the first tap would both open the
     menu and count as hovering, and the menu would stay stuck open. */
  var canHover = window.matchMedia("(hover: hover) and (pointer: fine)");

  function toggleOf(li) {
    return li.querySelector(".masthead__group-toggle");
  }

  function setOpen(li, open) {
    li.classList.toggle("is-open", open);
    var t = toggleOf(li);
    if (t) t.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeAll(except) {
    Array.prototype.forEach.call(groups, function (li) {
      if (li !== except) setOpen(li, false);
    });
  }

  function groupOf(node) {
    return node && node.closest ? node.closest(".masthead__menu-item--group") : null;
  }

  /* In the overflow panel the menu is a plain indented list, so opening it on
     hover would make the panel jump around under the pointer. */
  function inHeaderBar(li) {
    return !!li.parentElement && li.parentElement.classList.contains("visible-links");
  }

  Array.prototype.forEach.call(groups, function (li) {
    li.addEventListener("mouseenter", function () {
      if (canHover.matches && inHeaderBar(li)) { closeAll(li); setOpen(li, true); }
    });
    li.addEventListener("mouseleave", function () {
      if (canHover.matches && inHeaderBar(li)) setOpen(li, false);
    });
  });

  nav.addEventListener("click", function (e) {
    var toggle = e.target.closest && e.target.closest(".masthead__group-toggle");
    if (toggle) {
      e.preventDefault();
      var li = groupOf(toggle);
      /* With a mouse the menu is already open by the time the pointer reaches
         the parent, so treating the click as a toggle would shut what the
         reader just opened. Leave it alone and let moving away close it.
         `detail` is 0 for a click synthesised from Enter or Space, which is
         how a keyboard user opens it, so that still toggles. */
      if (canHover.matches && e.detail > 0 && li.classList.contains("is-open")) return;
      var willOpen = !li.classList.contains("is-open");
      closeAll(li);
      setOpen(li, willOpen);
      return;
    }
    /* A link inside the menu: let it navigate, but do not leave the menu open
       behind it if the page does not actually change. */
    if (e.target.closest && e.target.closest(".masthead__submenu a")) closeAll(null);
  });

  nav.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var open = groupOf(e.target);
      if (open && open.classList.contains("is-open")) {
        setOpen(open, false);
        var t = toggleOf(open);
        if (t) t.focus();
      }
      return;
    }
    var toggle = e.target.closest && e.target.closest(".masthead__group-toggle");
    if (toggle && (e.key === "Enter" || e.key === " " || e.key === "Spacebar")) {
      e.preventDefault();  /* Space would otherwise scroll the page */
      toggle.click();
    }
  });

  /* Leaving the menu by Tab closes it; `relatedTarget` is where focus landed. */
  nav.addEventListener("focusout", function (e) {
    var li = groupOf(e.target);
    if (li && !li.contains(e.relatedTarget)) setOpen(li, false);
  });

  document.addEventListener("click", function (e) {
    if (!nav.contains(e.target)) closeAll(null);
  });
})();
