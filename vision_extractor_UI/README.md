# Vision Extractor — Frontend

Vanilla HTML/CSS/JavaScript frontend for the Vision Data Extractor backend.

## One-time setup

1. **Fill in your Supabase credentials** in `shared/config.js`:

   ```js
   window.VE_CONFIG = {
     SUPABASE_URL:      "https://xxxxxxxxxxxx.supabase.co",
     SUPABASE_ANON_KEY: "your_anon_or_publishable_key_here",
     API_BASE_URL:      "http://127.0.0.1:8000",
   };
   ```

   Find these at: Supabase Dashboard → your project → **Settings → API**:
   - `SUPABASE_URL` = "Project URL"
   - `SUPABASE_ANON_KEY` = "anon / public" key (safe to use in browsers)

   **Never put** `SUPABASE_JWT_SECRET`, service-role keys, or `OPENROUTER_API_KEY` here.

2. **Add `shared/config.js` to `.gitignore`** if it contains real values:
   ```
   vision_extractor_UI/shared/config.js
   ```
   A `config.js.example` with placeholder values is safe to commit.

## Running locally

Open **two** terminals from the project root.

### Terminal 1 — FastAPI backend (port 8000)
```powershell
cd "Vision Data Extractor"
.\venv\Scripts\uvicorn.exe api.server:app --reload --port 8000
```

### Terminal 2 — Frontend static server (port 5500)
```powershell
cd "Vision Data Extractor\vision_extractor_UI"
python -m http.server 5500
```

Then open: http://localhost:5500/sign_in_vision_extractor/code.html

The backend CORS list already includes `http://localhost:5500` and
`http://127.0.0.1:5500`. If you use a different port, add it to
`ALLOWED_ORIGINS` in your backend `.env`.

## Enabling real authentication

1. Start both servers as above.
2. In `.env` (backend), set:
   ```
   SUPABASE_URL=https://xxxxxxxxxxxx.supabase.co
   SUPABASE_JWT_SECRET=<your jwt secret>   # for legacy HS256 tokens
   AUTH_ENABLED=true
   ```
3. Restart the backend.
4. Open the sign-in page, sign in with a real Supabase account.

## Page navigation

| Page | File |
|------|------|
| Sign In | `sign_in_vision_extractor/code.html` |
| Overview | `overview_vision_extractor/code.html` |
| Extract Images | `extract_images_vision_extractor/code.html` |
| Reports | `reports_vision_extractor/code.html` |
| Search Reports | `search_reports_vision_extractor/code.html` |
| Ask Your Images | `ask_your_images_vision_extractor/code.html` |
| Settings | `settings_vision_extractor/code.html` |

## Shared modules

| File | Purpose |
|------|---------|
| `shared/config.js` | Public Supabase URL + anon key + API base URL |
| `shared/supabase-client.js` | Supabase JS v2 client singleton |
| `shared/auth.js` | `requireAuth()`, `initUserDisplay()`, `signOut()`, `initNav()` |
| `shared/api-client.js` | `veAPI.get/post/upload()` with Bearer token injection |
