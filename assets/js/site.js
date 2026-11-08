/* ==========================================================================
   What the pages do, on every page:

   - the light/dark theme toggle (the theme itself is set before the page
     paints, by the script in _includes/head.html);
   - the header: items that do not fit move into the overflow menu behind the
     ☰ button, and an entry with children opens a submenu;
   - the sidebar's link list, folded behind a "Links" button on small screens;
   - the footer, which sits at the bottom of the window on a short page.

   Plain JavaScript, loaded with `defer`.
   ========================================================================== */

(function () {
  "use strict";

  var root = document.documentElement;

  /* ------------------------------------------------------------------------
     Theme
     ------------------------------------------------------------------------ */

  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");

  function storedTheme() {
    try {
      var t = localStorage.getItem("theme");
      return t === "dark" || t === "light" ? t : null;
    } catch (e) {
      return null;
    }
  }

  function setTheme(dark) {
    if (dark) root.setAttribute("data-theme", "dark");
    else root.removeAttribute("data-theme");
  }

  var themeToggle = document.querySelector(".theme-toggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", function () {
      var dark = root.getAttribute("data-theme") !== "dark";
      setTheme(dark);
      try {
        localStorage.setItem("theme", dark ? "dark" : "light");
      } catch (e) { /* private mode: the choice lasts for this page only */ }
    });
  }

  /* Until the reader picks a theme, follow the system's as it changes. */
  function followSystem(e) {
    if (!storedTheme()) setTheme(e.matches);
  }
  if (systemDark.addEventListener) systemDark.addEventListener("change", followSystem);
  else if (systemDark.addListener) systemDark.addListener(followSystem);

  /* ------------------------------------------------------------------------
     Header: the overflow menu ("priority+" navigation)

     The bar shows as many items as fit, from the left; the rest move, from
     the right, into .hidden-links behind the toggle button. Items marked
     .persist (the lab name, the language switch, the theme toggle) never
     move. `breaks` records how wide the bar was when each item left, so an
     item comes back once there is that much room again.
     ------------------------------------------------------------------------ */

  var nav = document.getElementById("site-nav");
  var masthead = document.querySelector(".masthead");
  var sidebar = document.querySelector(".sidebar");
  var linksButton = document.querySelector(".author__urls-wrapper button");

  /* Width of the content box: the box less its padding and border. */
  function contentWidth(el) {
    var cs = getComputedStyle(el);
    return parseFloat(cs.width) -
      parseFloat(cs.paddingLeft) - parseFloat(cs.paddingRight) -
      parseFloat(cs.borderLeftWidth) - parseFloat(cs.borderRightWidth);
  }

  function isShown(el) {
    return !!(el && (el.offsetWidth || el.offsetHeight || el.getClientRects().length));
  }

  if (nav) {
    var navToggle = nav.querySelector(".greedy-nav__toggle");
    var visible = nav.querySelector(".visible-links");
    var hidden = nav.querySelector(".hidden-links");
    var breaks = [];

    var movable = function () {
      return visible.querySelectorAll(":scope > li:not(.persist)");
    };

    /* Room for the bar: the whole nav, less the toggle and a margin while the
       toggle is showing. */
    var available = function () {
      return navToggle.classList.contains("hidden") ?
        contentWidth(nav) : contentWidth(nav) - contentWidth(navToggle) - 30;
    };

    var closeOverflow = function () {
      navToggle.classList.remove("close");
      navToggle.setAttribute("aria-expanded", "false");
      hidden.classList.add("hidden");
    };

    var updateNav = function () {
      var space = available();

      if (contentWidth(visible) > space) {
        /* Too wide: move items out, last first, until the bar fits. */
        var items = movable();
        while (contentWidth(visible) > space && items.length > 0) {
          breaks.push(contentWidth(visible));
          hidden.insertBefore(items[items.length - 1], hidden.firstChild);
          space = available();
          navToggle.classList.remove("hidden");
          items = movable();
        }
      } else {
        /* Room to spare: bring items back, in order, ahead of the language
           switch and the theme toggle at the end of the bar. */
        var tail = visible.querySelector(":scope > li.tail");
        while (breaks.length > 0 && space > breaks[breaks.length - 1]) {
          visible.insertBefore(hidden.firstElementChild, tail);
          breaks.pop();
        }
        if (breaks.length < 1) {
          navToggle.classList.add("hidden");
          closeOverflow();
        }
      }

      /* The masthead is fixed, so the page starts below it. Its height
         changes as the bar's font size and contents do. */
      var mastheadHeight = parseFloat(getComputedStyle(masthead).height);
      document.body.style.paddingTop = mastheadHeight + "px";
      root.style.setProperty("--masthead-height", mastheadHeight + "px");
      if (sidebar) {
        sidebar.style.paddingTop = isShown(linksButton) ? "" : mastheadHeight + "px";
      }
    };

    navToggle.addEventListener("click", function () {
      var open = hidden.classList.toggle("hidden") === false;
      navToggle.classList.toggle("close", open);
      navToggle.setAttribute("aria-expanded", open ? "true" : "false");
    });

    /* The toggle starts hidden so it never flashes on a wide screen; the
       first measurement is made as if it were showing. */
    navToggle.classList.remove("hidden");
    updateNav();
    window.addEventListener("resize", updateNav);
  }

  /* ------------------------------------------------------------------------
     Header: submenus

     An entry with children (Research) opens a menu instead of going
     somewhere. The class on its <li> is the single source of truth for
     open/closed, hover included: letting CSS :hover open it as well would
     leave the class and the screen disagreeing after a click. Listeners sit
     on the <li> itself, which the overflow menu moves but never re-creates.
     ------------------------------------------------------------------------ */

  var groups = nav ? nav.querySelectorAll(".masthead__menu-item--group") : [];

  if (groups.length) {
    /* Hover is for a mouse. On a touch screen the first tap would both open
       the menu and count as hovering, and the menu would stay stuck open. */
    var canHover = window.matchMedia("(hover: hover) and (pointer: fine)");

    var toggleOf = function (li) {
      return li.querySelector(".masthead__group-toggle");
    };

    var setOpen = function (li, open) {
      li.classList.toggle("is-open", open);
      toggleOf(li).setAttribute("aria-expanded", open ? "true" : "false");
    };

    var closeAll = function (except) {
      Array.prototype.forEach.call(groups, function (li) {
        if (li !== except) setOpen(li, false);
      });
    };

    /* In the overflow menu the submenu is a plain indented list, so opening it
       on hover would make the menu jump around under the pointer. */
    var inBar = function (li) {
      return li.parentElement === nav.querySelector(".visible-links");
    };

    Array.prototype.forEach.call(groups, function (li) {
      li.addEventListener("mouseenter", function () {
        if (canHover.matches && inBar(li)) { closeAll(li); setOpen(li, true); }
      });
      li.addEventListener("mouseleave", function () {
        if (canHover.matches && inBar(li)) setOpen(li, false);
      });

      toggleOf(li).addEventListener("click", function (e) {
        /* With a mouse the menu is already open by the time the pointer
           reaches the entry, so a click must not shut it. `detail` is 0 for
           a click made with Enter or Space, which still toggles. */
        if (canHover.matches && e.detail > 0 && inBar(li) && li.classList.contains("is-open")) return;
        var willOpen = !li.classList.contains("is-open");
        closeAll(li);
        setOpen(li, willOpen);
      });

      /* Leaving the menu with Tab closes it; relatedTarget is where focus went. */
      li.addEventListener("focusout", function (e) {
        if (!li.contains(e.relatedTarget)) setOpen(li, false);
      });

      li.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && li.classList.contains("is-open")) {
          setOpen(li, false);
          toggleOf(li).focus();
        }
      });
    });

    document.addEventListener("click", function (e) {
      if (!nav.contains(e.target) || e.target.closest(".masthead__submenu a")) closeAll(null);
    });
  }

  /* ------------------------------------------------------------------------
     Sidebar: the link list behind the "Links" button on small screens
     ------------------------------------------------------------------------ */

  if (linksButton) {
    var linkList = document.getElementById(linksButton.getAttribute("aria-controls"));
    linksButton.addEventListener("click", function () {
      var open = linkList.classList.toggle("is-open");
      linksButton.setAttribute("aria-expanded", open ? "true" : "false");
    });
  }

  /* ------------------------------------------------------------------------
     Footer: on a page shorter than the window it sits at the bottom
     (it is positioned absolutely; the body keeps room for it)
     ------------------------------------------------------------------------ */

  var footer = document.querySelector(".page__footer");
  if (footer) {
    var bumpFooter = function () {
      var cs = getComputedStyle(footer);
      document.body.style.marginBottom =
        parseFloat(cs.height) + parseFloat(cs.marginTop) + parseFloat(cs.marginBottom) + "px";
    };
    bumpFooter();
    /* Its height changes as its text reflows, its top margin with the font size. */
    if (window.ResizeObserver) new ResizeObserver(bumpFooter).observe(footer);
    window.addEventListener("resize", bumpFooter);
  }
})();
