/**
 * Vision Extractor — shared authentication utilities.
 *
 * Call requireAuth() at the top of every protected page.
 * Call initUserDisplay() to populate the header with real session data.
 * Call signOut() from the settings or nav sign-out button.
 * Call initNav() once per page to wire all nav links.
 *
 * Depends on: config.js → supabase-client.js → auth.js (load order).
 */

/* -------------------------------------------------------------------------- */
/*  Page paths                                                                 */
/* -------------------------------------------------------------------------- */
const VE_PAGES = {
  "sign-in":        "../sign_in_vision_extractor/code.html",
  "overview":       "../overview_vision_extractor/code.html",
  "extract-images": "../extract_images_vision_extractor/code.html",
  "reports":        "../reports_vision_extractor/code.html",
  "search-reports": "../search_reports_vision_extractor/code.html",
  "ask-your-images":"../ask_your_images_vision_extractor/code.html",
  "settings":       "../settings_vision_extractor/code.html",
};

const VE_SIGN_IN  = VE_PAGES["sign-in"];
const VE_OVERVIEW = VE_PAGES["overview"];


/* -------------------------------------------------------------------------- */
/*  requireAuth                                                                */
/* -------------------------------------------------------------------------- */

/**
 * Redirect unauthenticated users to sign-in.
 * Returns the current session object on success, or null if redirecting.
 */
async function requireAuth() {
  if (!window.veSupabase) {
    window.location.href = VE_SIGN_IN;
    return null;
  }
  const { data, error } = await window.veSupabase.auth.getSession();
  if (error || !data.session) {
    window.location.href = VE_SIGN_IN;
    return null;
  }
  return data.session;
}


/* -------------------------------------------------------------------------- */
/*  initNav                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Wire every nav link that carries a data-path attribute.
 * The Stitch-generated pages use data-path="overview", data-path="reports"
 * etc. on their <a> elements. This function sets each link's real href.
 *
 * Call once per page — idempotent, safe to call multiple times.
 */
function initNav() {
  document.querySelectorAll("a[data-path]").forEach(function (link) {
    const key = link.getAttribute("data-path");
    if (VE_PAGES[key]) {
      link.href = VE_PAGES[key];
    }
  });
}


/* -------------------------------------------------------------------------- */
/*  initUserDisplay                                                            */
/* -------------------------------------------------------------------------- */

/**
 * Populate visible user fields in the page header from the live session.
 * Targets elements with IDs: ve-user-name, ve-user-email, ve-workspace-label.
 */
function initUserDisplay(session) {
  if (!session) return;
  const user = session.user;
  const displayName =
    (user.user_metadata && (user.user_metadata.full_name || user.user_metadata.name)) ||
    user.email.split("@")[0];

  document.querySelectorAll("#ve-user-name, .ve-user-name")
    .forEach(el => { el.textContent = displayName; });
  document.querySelectorAll("#ve-user-email, .ve-user-email, #ve-user-email-nav")
    .forEach(el => { el.textContent = user.email; });
  document.querySelectorAll("#ve-workspace-label, .ve-workspace-label")
    .forEach(el => { el.textContent = "Workspace / " + displayName; });
  // Populate avatar initials
  var initial = displayName.charAt(0).toUpperCase();
  document.querySelectorAll("#ve-user-avatar")
    .forEach(function(el) { el.textContent = initial; });
}


/* -------------------------------------------------------------------------- */
/*  signOut                                                                    */
/* -------------------------------------------------------------------------- */

/**
 * Sign the current user out via Supabase and redirect to sign-in.
 */
async function signOut() {
  if (window.veSupabase) {
    await window.veSupabase.auth.signOut();
  }
  window.location.href = VE_SIGN_IN;
}


/* -------------------------------------------------------------------------- */
/*  initPage — convenience wrapper                                             */
/* -------------------------------------------------------------------------- */

/**
 * Combined guard + nav wiring for protected pages.
 * Returns the session or null (if redirecting).
 *
 *   const session = await initPage();
 *   if (!session) return;
 *   // page-specific code here
 */
async function initPage() {
  initNav();                     // set hrefs immediately (sync)
  var session = await requireAuth();    // then check session
  if (session) {
    initUserDisplay(session);      // populate name, email, avatar initials
    initProfileDropdown(session);  // wire the profile dropdown with real session
  }
  return session;
}


/* -------------------------------------------------------------------------- */
/*  initProfileDropdown                                                        */
/* -------------------------------------------------------------------------- */

/**
 * Convert the decorative expand_more span into a real dropdown button.
 * The dropdown contains: email display, Settings link, Sign Out.
 *
 * Safe to call multiple times — idempotent (checks for existing dropdown).
 * Must be called after the session is known so the email can be populated.
 */
function initProfileDropdown(session) {
  // Prevent double-init
  if (document.getElementById("ve-profile-dropdown")) return;

  // Find the profile area wrapper (contains ve-user-avatar + expand_more span)
  var avatar = document.getElementById("ve-user-avatar");
  if (!avatar) return;

  var wrapper = avatar.parentElement;
  if (!wrapper) return;

  // Replace the static expand_more span with a proper button
  var oldSpan = wrapper.querySelector("span.material-symbols-outlined");
  if (oldSpan) oldSpan.remove();

  var toggleBtn = document.createElement("button");
  toggleBtn.id = "ve-profile-toggle";
  toggleBtn.type = "button";
  toggleBtn.className = "p-0.5 rounded-lg text-on-surface-variant hover:text-on-surface hover:bg-surface-container transition-colors hidden md:flex items-center";
  toggleBtn.setAttribute("aria-label", "Open profile menu");
  toggleBtn.setAttribute("aria-expanded", "false");
  toggleBtn.setAttribute("aria-haspopup", "true");
  toggleBtn.innerHTML = '<span class="material-symbols-outlined text-[16px]">expand_more</span>';
  wrapper.appendChild(toggleBtn);

  // Build the dropdown
  var email   = (session && session.user && session.user.email) || "";
  var dropdown = document.createElement("div");
  dropdown.id = "ve-profile-dropdown";
  dropdown.className = [
    "hidden", "absolute", "right-0", "top-full", "mt-2", "z-[60]",
    "min-w-[200px]", "rounded-xl", "bg-surface-container-lowest",
    "shadow-xl", "border", "border-outline-variant/30",
    "flex", "flex-col", "overflow-hidden"
  ].join(" ");
  dropdown.setAttribute("role", "menu");
  dropdown.innerHTML =
    '<div class="px-4 py-3 border-b border-outline-variant/20">' +
      '<p class="font-body-sm text-body-sm text-on-surface-variant">Signed in as</p>' +
      '<p class="font-body-sm text-body-sm text-on-surface font-medium truncate">' + email + '</p>' +
    '</div>' +
    '<a class="flex items-center gap-2 px-4 py-2.5 font-body-sm text-body-sm text-on-surface hover:bg-surface-container transition-colors" ' +
       'href="' + VE_PAGES["settings"] + '" role="menuitem">' +
      '<span class="material-symbols-outlined text-[16px] text-on-surface-variant">settings</span>Settings' +
    '</a>' +
    '<button class="flex items-center gap-2 px-4 py-2.5 font-body-sm text-body-sm text-error hover:bg-error-container/30 transition-colors w-full text-left" ' +
            'id="ve-signout-dropdown-btn" role="menuitem" type="button">' +
      '<span class="material-symbols-outlined text-[16px]">logout</span>Sign Out' +
    '</button>';

  // The wrapper needs position:relative for the dropdown to anchor correctly
  wrapper.style.position = "relative";
  wrapper.appendChild(dropdown);

  // Wire the sign-out button
  var signoutBtn = document.getElementById("ve-signout-dropdown-btn");
  if (signoutBtn) {
    signoutBtn.addEventListener("click", async function() {
      closeDropdown();
      await signOut();
    });
  }

  function openDropdown() {
    dropdown.classList.remove("hidden");
    toggleBtn.setAttribute("aria-expanded", "true");
  }

  function closeDropdown() {
    dropdown.classList.add("hidden");
    toggleBtn.setAttribute("aria-expanded", "false");
  }

  function toggleDropdown() {
    if (dropdown.classList.contains("hidden")) { openDropdown(); } else { closeDropdown(); }
  }

  // Toggle on button click
  toggleBtn.addEventListener("click", function(e) {
    e.stopPropagation();
    toggleDropdown();
  });

  // Also make the avatar clickable
  avatar.style.cursor = "pointer";
  avatar.addEventListener("click", function(e) {
    e.stopPropagation();
    toggleDropdown();
  });

  // Close on outside click
  document.addEventListener("click", function(e) {
    if (!wrapper.contains(e.target)) closeDropdown();
  });

  // Close on Escape
  document.addEventListener("keydown", function(e) {
    if (e.key === "Escape") closeDropdown();
  });

  // Keyboard: move focus inside dropdown with arrow keys
  toggleBtn.addEventListener("keydown", function(e) {
    if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      openDropdown();
      var firstItem = dropdown.querySelector("a, button");
      if (firstItem) firstItem.focus();
    }
  });
}
