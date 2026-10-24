/**
 * Vision Extractor — Supabase client singleton.
 *
 * Loaded after config.js. Exposes window.veSupabase.
 * Uses the official Supabase JS v2 UMD build from the CDN.
 *
 * CDN: https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2.49.4/dist/umd/supabase.min.js
 * Pinned to 2.49.4 — do not use an unversioned URL.
 */

(function () {
  "use strict";

  function isConfigured() {
    const cfg = window.VE_CONFIG;
    return (
      cfg &&
      cfg.SUPABASE_URL &&
      cfg.SUPABASE_URL !== "REPLACE_WITH_YOUR_SUPABASE_URL" &&
      cfg.SUPABASE_ANON_KEY &&
      cfg.SUPABASE_ANON_KEY !== "REPLACE_WITH_YOUR_SUPABASE_ANON_KEY"
    );
  }

  if (!isConfigured()) {
    console.error(
      "[VE] Supabase is not configured. " +
      "Open vision_extractor_UI/shared/config.js and fill in " +
      "SUPABASE_URL and SUPABASE_ANON_KEY."
    );
    window.veSupabase = null;
    return;
  }

  if (!window.supabase) {
    console.error(
      "[VE] Supabase JS library not loaded. " +
      "Ensure the CDN <script> tag appears before supabase-client.js."
    );
    window.veSupabase = null;
    return;
  }

  try {
    window.veSupabase = window.supabase.createClient(
      window.VE_CONFIG.SUPABASE_URL,
      window.VE_CONFIG.SUPABASE_ANON_KEY,
      {
        auth: {
          persistSession: true,
          autoRefreshToken: true,
          detectSessionInUrl: true,
        },
      }
    );
  } catch (err) {
    console.error("[VE] Failed to create Supabase client:", err);
    window.veSupabase = null;
  }
})();
