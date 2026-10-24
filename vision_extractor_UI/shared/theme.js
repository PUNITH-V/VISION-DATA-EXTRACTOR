/**
 * Vision Extractor — theme persistence.
 *
 * Applies before paint (loaded in <head>) so there is no flash.
 * Persists to localStorage key "ve-theme" → "light" | "dark" | "system".
 *
 * Dark mode implementation:
 *   Tailwind's darkMode:"class" requires the `dark` class on <html>.
 *   The Stitch design token palette only defines light-mode colors.
 *   To make dark mode visually effective we inject a <style> block with
 *   CSS variable overrides scoped to html.dark, replacing the surface,
 *   on-surface, and container tokens with a dark palette that is
 *   consistent with the existing brand colors.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "ve-theme";
  var html = document.documentElement;

  // ── Dark-mode CSS overrides ──────────────────────────────────────────────
  // These use the same Tailwind arbitrary-value approach: we override
  // CSS custom properties that our inline Tailwind config references by
  // injecting a <style> block.  Because Tailwind's CDN build generates
  // utility classes at runtime using the config values, we also inject
  // a small set of direct CSS rules that target bg-surface, text-on-surface
  // etc. via the Tailwind-generated class names.
  var DARK_CSS = [
    "html.dark { color-scheme: dark; }",
    /* Page / app backgrounds */
    "html.dark body, html.dark .bg-surface { background-color: #0f172a !important; color: #e2e8f0 !important; }",
    "html.dark .bg-surface-container-lowest { background-color: #1e293b !important; }",
    "html.dark .bg-surface-container-low { background-color: #1e293b !important; }",
    "html.dark .bg-surface-container { background-color: #334155 !important; }",
    "html.dark .bg-surface-container-high { background-color: #334155 !important; }",
    "html.dark .bg-surface-container-highest { background-color: #475569 !important; }",
    "html.dark .bg-surface-dim { background-color: #0f172a !important; }",
    "html.dark .bg-surface-bright { background-color: #1e293b !important; }",
    /* Text */
    "html.dark .text-on-surface { color: #e2e8f0 !important; }",
    "html.dark .text-on-surface-variant { color: #94a3b8 !important; }",
    "html.dark .text-outline { color: #64748b !important; }",
    "html.dark .text-outline-variant { color: #334155 !important; }",
    "html.dark .text-on-secondary-container { color: #94a3b8 !important; }",
    /* Header and nav */
    "html.dark header.fixed { background-color: rgba(15,23,42,0.95) !important; }",
    "html.dark nav { background-color: #1e293b !important; }",
    "html.dark .bg-surface\\/95 { background-color: rgba(15,23,42,0.95) !important; }",
    /* Cards and containers used in nav/header */
    "html.dark .bg-surface-container-low\\/60 { background-color: rgba(30,41,59,0.6) !important; }",
    "html.dark .bg-secondary-container\\/60 { background-color: rgba(51,65,85,0.6) !important; }",
    "html.dark .bg-secondary-container { background-color: #1e3a5f !important; }",
    "html.dark .text-on-secondary-container { color: #93c5fd !important; }",
    /* Inputs */
    "html.dark input, html.dark textarea, html.dark select { background-color: #1e293b !important; color: #e2e8f0 !important; border-color: #334155 !important; }",
    "html.dark input::placeholder, html.dark textarea::placeholder { color: #64748b !important; }",
    /* Modals */
    "html.dark .fixed.inset-0 { background-color: rgba(0,0,0,0.7) !important; }",
    /* Footer */
    "html.dark footer { background-color: #1e293b !important; }",
    "html.dark footer .text-on-surface-variant { color: #64748b !important; }",
    /* Tables */
    "html.dark tbody tr:hover { background-color: rgba(30,41,59,0.4) !important; }",
    "html.dark thead tr { background-color: rgba(30,41,59,0.7) !important; }",
    /* Pre/code blocks */
    "html.dark pre { background-color: #0f172a !important; color: #e2e8f0 !important; }",
    /* Scrollbar (keep hidden but ensure no light flash) */
    "html.dark ::-webkit-scrollbar { display: none; }"
  ].join("\n");

  var _styleInjected = false;

  function injectDarkStyles() {
    if (_styleInjected) return;
    _styleInjected = true;
    var s = document.createElement("style");
    s.id = "ve-dark-theme";
    s.textContent = DARK_CSS;
    document.head.appendChild(s);
  }

  // ── Core helpers ─────────────────────────────────────────────────────────

  function resolveTheme(pref) {
    if (pref === "system") {
      return (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches)
        ? "dark" : "light";
    }
    return pref === "dark" ? "dark" : "light";
  }

  function saved() {
    try { return localStorage.getItem(STORAGE_KEY) || "light"; } catch (_) { return "light"; }
  }

  function apply(pref) {
    var theme = resolveTheme(pref);
    if (theme === "dark") {
      injectDarkStyles();
      html.classList.remove("light");
      html.classList.add("dark");
    } else {
      html.classList.remove("dark");
      html.classList.add("light");
    }
  }

  function set(pref) {
    try { localStorage.setItem(STORAGE_KEY, pref); } catch (_) {}
    apply(pref);
    updateButtonLabels();
    updateRadios(pref);
  }

  function toggle() {
    var cur = saved();
    set(cur === "dark" ? "light" : "dark");
  }

  // ── UI sync helpers ───────────────────────────────────────────────────────

  function updateButtonLabels() {
    var isDark = html.classList.contains("dark");
    document.querySelectorAll("#theme-toggle-btn, [data-ve-theme-toggle]")
      .forEach(function(btn) {
        btn.setAttribute("aria-label",
          isDark ? "Switch to light mode" : "Switch to dark mode");
      });
  }

  function updateRadios(pref) {
    document.querySelectorAll("input[name='theme-mode']").forEach(function(r) {
      r.checked = (r.value === pref);
    });
  }

  function initToggleButtons() {
    document.querySelectorAll("#theme-toggle-btn, [data-ve-theme-toggle]")
      .forEach(function(btn) {
        btn.removeAttribute("onclick");
        btn.addEventListener("click", function() { toggle(); });
      });
  }

  function initRadios() {
    var currentPref = saved();
    updateRadios(currentPref);
    document.querySelectorAll("input[name='theme-mode']").forEach(function(r) {
      r.addEventListener("change", function(e) {
        var val = e.target.value;  // "light" | "dark" | "system"
        set(val);
      });
    });
    // React to OS preference changes when "system" is selected
    if (window.matchMedia) {
      window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", function() {
        if (saved() === "system") apply("system");
      });
    }
  }

  // ── Bootstrap ─────────────────────────────────────────────────────────────

  // Apply saved preference immediately (before paint).
  apply(saved());

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function() {
      initToggleButtons();
      initRadios();
      updateButtonLabels();
    });
  } else {
    initToggleButtons();
    initRadios();
    updateButtonLabels();
  }

  // Expose public API.
  window.veTheme = {
    set: set,
    toggle: toggle,
    current: function() { return saved(); }
  };
})();
