/**
 * Vision Extractor — FastAPI client.
 *
 * Retrieves the real Supabase access token and attaches it as
 * Authorization: Bearer <token> on every protected request.
 *
 * Depends on: config.js → supabase-client.js → api-client.js
 *
 * Usage:
 *   const health  = await veAPI.get("/api/health");
 *   const reports = await veAPI.get("/api/reports");           // auth required
 *   const result  = await veAPI.post("/api/search", { query, top_k });
 *   const saved   = await veAPI.upload("/api/extractions", formData);
 */

const veAPI = (function () {
  "use strict";

  function baseURL() {
    return (window.VE_CONFIG && window.VE_CONFIG.API_BASE_URL) ||
      "http://127.0.0.1:8000";
  }

  /** Obtain the current access token from the live Supabase session. */
  async function getAccessToken() {
    if (!window.veSupabase) return null;
    const { data } = await window.veSupabase.auth.getSession();
    return data.session ? data.session.access_token : null;
  }

  /**
   * Core fetch wrapper.
   * Returns { ok, status, data } — never throws on HTTP errors.
   * data is null on network failure.
   */
  async function request(method, path, body, isFormData) {
    const token = await getAccessToken();
    const headers = {};

    if (token) {
      headers["Authorization"] = "Bearer " + token;
    }
    if (!isFormData && body !== undefined) {
      headers["Content-Type"] = "application/json";
    }

    const init = { method, headers };
    if (body !== undefined) {
      init.body = isFormData ? body : JSON.stringify(body);
    }

    let response;
    try {
      response = await fetch(baseURL() + path, init);
    } catch (networkErr) {
      console.error("[veAPI] Network error:", networkErr);
      return { ok: false, status: 0, data: null, error: "Network error — is the backend running?" };
    }

    let data = null;
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      try { data = await response.json(); } catch (_) {}
    }

    if (!response.ok) {
      const detail = (data && data.detail) ? data.detail : `HTTP ${response.status}`;
      // 401 means session expired — redirect to sign-in
      if (response.status === 401) {
        console.warn("[veAPI] 401 received — session may be expired.");
        window.location.href = VE_PAGES
          ? VE_PAGES.signIn
          : "../sign_in_vision_extractor/code.html";
        return { ok: false, status: 401, data: null, error: detail };
      }
      return { ok: false, status: response.status, data, error: detail };
    }

    return { ok: true, status: response.status, data, error: null };
  }

  return {
    /** GET request (public or authenticated). */
    get: function (path) {
      return request("GET", path);
    },

    /** POST request with JSON body. */
    post: function (path, body) {
      return request("POST", path, body, false);
    },

    /** DELETE request (authenticated, no body). */
    delete: function (path) {
      return request("DELETE", path);
    },

    /** POST request with FormData (file upload). */
    upload: function (path, formData) {
      return request("POST", path, formData, true);
    },
  };
})();
