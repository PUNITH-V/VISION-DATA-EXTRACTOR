/**
 * Vision Extractor — frontend public configuration.
 *
 * Fill in your Supabase project values before running the app.
 * These are PUBLIC/publishable values — safe to include in browser code.
 * NEVER put SUPABASE_JWT_SECRET, service-role keys, or OpenRouter keys here.
 *
 * Find these in:
 *   Supabase Dashboard → your project → Settings → API
 *   - "Project URL"  → SUPABASE_URL
 *   - "anon / public" key  → SUPABASE_ANON_KEY
 *
 * CORS: The FastAPI backend defaults to http://127.0.0.1:5500
 * Run the frontend with: python -m http.server 5500
 * (from inside vision_extractor_UI/ directory)
 */
window.VE_CONFIG = {
  SUPABASE_URL: "https://jtsxuebbkhbdhfgvxgpa.supabase.co",
  SUPABASE_ANON_KEY: "sb_publishable_vupwt--Lmv72CFI9YBVvJg_Z0xoIgen",
  API_BASE_URL: "https://overnight-dvds-comfortable-facilitate.trycloudflare.com",
};
