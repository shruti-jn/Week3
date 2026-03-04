# Step 13 — Deploy: Railway (backend) + Vercel (frontend)

Do these **in order**. Commands you run locally are in code blocks.

The key ordering constraint: Railway needs the Vercel URL for CORS, but Vercel
needs the Railway URL for API calls. Solution: deploy Railway first with a wildcard
CORS origin, then deploy Vercel, then lock down CORS to the real Vercel URL.

---

## 1. Push your deployment branch

Make sure `dev` is pushed (Railway auto-deploys on push to `dev`):

```bash
cd /Users/shruti/Week3
git push -u origin dev
```

---

## 2. Railway — Backend

### 2a. Fix Root Directory (one-time dashboard step)

The build is currently failing because Railway is reading from the repo root instead
of `backend/`. Fix this in the dashboard:

1. Go to your Railway project → Week3 service → **Settings → Source**
2. Click **"Add Root Directory"**
3. Type: `backend`
4. Save — this triggers a redeploy

Railway will now find `backend/railway.toml` and use the Dockerfile builder.

### 2b. Set environment variables

In Railway → Week3 service → **Variables**, add all of these:

| Variable | Value |
|----------|-------|
| `OPENAI_API_KEY` | `sk-...` |
| `PINECONE_API_KEY` | your Pinecone key |
| `PINECONE_INDEX_NAME` | `legacylens` |
| `GITHUB_CLIENT_ID` | from your GitHub OAuth App |
| `GITHUB_CLIENT_SECRET` | from your GitHub OAuth App |
| `NEXTAUTH_SECRET` | run `openssl rand -base64 32` to generate |
| `ALLOWED_ORIGINS` | `["*"]` ← temporary, locked down in step 4 |
| `ENVIRONMENT` | `production` |
| `RATE_LIMIT_PER_MINUTE` | `20` |
| `RETRIEVAL_TOP_K` | `10` |
| `SIMILARITY_THRESHOLD` | `0.75` |

### 2c. Get your Railway URL

After a successful deploy, Railway shows the public URL in the service panel.
Format: `https://week3-production-xxxx.up.railway.app`

You can also find it at: Settings → Networking → Public Networking → Generate Domain.

### 2d. Verify backend is alive

```bash
curl -s https://YOUR-RAILWAY-URL.up.railway.app/health
# Expect: {"status":"ok","service":"legacylens-api"}
```

---

## 3. Vercel — Frontend

### 3a. Import project

- Go to [vercel.com](https://vercel.com) → **Add New → Project → Import** your GitHub repo.

### 3b. Configure build

- **Root Directory**: click Edit → set to `frontend`
- **Framework Preset**: Next.js (auto-detected)
- **Build Command**: `npm run build` (default)
- **Output Directory**: default (`.next`)

### 3c. Add environment variables

In Vercel → Settings → Environment Variables:

| Name | Value | Environment |
|------|-------|-------------|
| `NEXT_PUBLIC_API_URL` | `https://YOUR-RAILWAY-URL.up.railway.app` | Production |
| `NEXTAUTH_URL` | `https://YOUR_VERCEL_APP.vercel.app` ← set after first deploy | Production |
| `NEXTAUTH_SECRET` | Same value as Railway | Production |
| `GITHUB_CLIENT_ID` | From GitHub OAuth App | Production |
| `GITHUB_CLIENT_SECRET` | From GitHub OAuth App | Production |
| `NEXT_TELEMETRY_DISABLED` | `1` | All |

Note: `NEXTAUTH_URL` must be set to the actual Vercel URL. You can set it to a
placeholder for the first deploy, then update it once Vercel gives you the URL.

### 3d. Deploy

Click **Deploy**. Vercel runs `npm ci && npm run build` from `frontend/`.

### 3e. Set NEXTAUTH_URL after first deploy

- After deploy, copy the production URL (e.g. `https://legacylens.vercel.app`).
- In Vercel → Settings → Environment Variables → update `NEXTAUTH_URL` to that URL.
- **Redeploy** (Deployments → Redeploy) so Next.js picks up the new value.

### 3f. GitHub OAuth callback URL

In [GitHub → Settings → Developer settings → OAuth Apps](https://github.com/settings/developers),
open your OAuth App and add:

**Authorization callback URL**: `https://YOUR_VERCEL_APP.vercel.app/api/auth/callback/github`

---

## 4. Lock down Railway CORS

Now that you have the real Vercel URL, replace the wildcard CORS:

In Railway → Week3 service → **Variables**, update:

```
ALLOWED_ORIGINS = ["https://YOUR_VERCEL_APP.vercel.app"]
```

Railway auto-redeploys when you save a variable. Wait for the deploy to complete.

---

## 5. Verify (Phase 1 deploy criteria)

- [ ] Backend: `curl https://YOUR-RAILWAY-URL.up.railway.app/health` returns `{"status":"ok",...}`
- [ ] Frontend: `https://YOUR_VERCEL_APP.vercel.app` loads without errors
- [ ] GitHub OAuth: clicking "Sign in with GitHub" completes and returns to the app
- [ ] Query: submit a search — request reaches Railway and returns results (or a proper error)
- [ ] CORS: no `Access-Control-Allow-Origin` errors in browser console

Step 13 is done when all five checks pass.
