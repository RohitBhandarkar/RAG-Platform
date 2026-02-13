# Webapp ↔ GCP Backend: Connect and Deploy to Vercel

This guide covers (1) allowing the webapp to connect to the FastAPI backend on a GCP VM, and (2) using the webapp once it’s deployed on Vercel.

---

## 1. GCP: Allow the webapp to connect

The backend runs on the VM (e.g. port **8080**). The browser will call it from your webapp origin (localhost or Vercel). You need: **CORS** on the backend and **network access** to the VM.

### 1.1 CORS (backend)

The backend uses `CORS_ORIGINS` to decide which origins are allowed. Set it on the VM (e.g. in the deploy workflow or in the container env) so it includes your webapp URL(s).

**Option A – GitHub Actions (recommended)**  
The deploy workflow already passes `FRONTEND_URL` and `CORS_ORIGINS` from GitHub secrets into the backend container. In your repo → **Settings** → **Secrets and variables** → **Actions**, add:

- **`CORS_ORIGINS`**: `https://your-app.vercel.app,http://localhost:3000` (use your real Vercel URL; add `http://localhost:3000` for local dev).
- **`FRONTEND_URL`** (optional): `https://your-app.vercel.app`.

Redeploy the backend after adding or changing these secrets.

**Option B – Manually on the VM**  
If you start the backend container by hand:

```bash
docker run -d \
  ...
  -e CORS_ORIGINS="https://your-app.vercel.app,http://localhost:3000" \
  ...
```

**Config behavior**

- `CORS_ORIGINS`: comma-separated list of allowed origins (e.g. `https://my-app.vercel.app`, `http://localhost:3000`).
- If `CORS_ORIGINS` is not set or empty, the backend uses `FRONTEND_URL` (default `http://localhost:3000`).

So: set `CORS_ORIGINS` (and optionally `FRONTEND_URL`) so the backend allows your Vercel origin and, if you want, localhost.

### 1.2 Firewall (GCP VM)

The VM must accept inbound traffic on the port the backend listens on (e.g. **8080**).

1. In **Google Cloud Console** → **VPC network** → **Firewall** (or **Compute Engine** → **VM** → **Network**).
2. Create or edit a firewall rule:
   - **Ingress**.
   - **Targets**: e.g. “All instances in the network” or the tag of your backend VM.
   - **Source IP ranges**: e.g. `0.0.0.0/0` (any; for a demo/POC). For production you could restrict to Vercel IPs or use a load balancer.
   - **Protocols and ports**: **tcp:8080** (or the port your backend uses).
3. Save.

If the VM has no firewall blocking 8080 (e.g. default “allow all” in a test project), you may not need to change anything. If the webapp cannot reach the API, check this first.

### 1.3 Backend URL the webapp will use

- **From your machine**: `http://<VM_EXTERNAL_IP>:8080` (or `https://...` if you put a reverse proxy in front).
- **From Vercel**: same URL. The browser (user’s device) calls the VM; only the **origin** of the page (Vercel domain) must be in `CORS_ORIGINS`.

So the webapp’s “Backend URL” (or `NEXT_PUBLIC_API_URL`) should be that base URL, e.g. `http://34.123.45.67:8080`. If the VM’s external IP changes after stop/start, reserve a **static external IP** for the VM and use that in the URL.

---

## 2. Vercel: After you deploy the webapp

### 2.1 Environment variables (Vercel)

In the Vercel project → **Settings** → **Environment variables**, set at least:

- **Clerk**:  
  `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY`  
  (and optionally `NEXT_PUBLIC_ALLOWED_CLERK_EMAIL` for single-account).
- **Backend URL** (optional):  
  `NEXT_PUBLIC_API_URL` = `http://<VM_EXTERNAL_IP>:8080`  
  If you leave this unset, users can set the Backend URL **inside the app** after login (stored in the browser). That’s often easier when the VM IP changes.

Redeploy after changing env vars.

### 2.2 User flow: setting the backend URL

Because the VM IP can change:

1. User signs in to the webapp (on Vercel).
2. In the top bar they see **Backend URL**.
3. They set it to the current backend base URL (e.g. `http://<current-vm-ip>:8080`) and click **Save**.
4. The app then uses that URL for all API calls. No redeploy needed when the IP changes; only the backend must have CORS for the Vercel origin.

### 2.3 CORS for the Vercel domain

On the **backend** (GCP), `CORS_ORIGINS` must include the **exact** Vercel origin the browser uses, for example:

- Production: `https://your-project.vercel.app`
- Or custom domain: `https://rag.yourdomain.com`

Add that origin to `CORS_ORIGINS` (see section 1.1). No CORS config is needed on Vercel itself; CORS is enforced by the backend.

### 2.4 HTTPS and mixed content

If the webapp is on **HTTPS** (Vercel) and the backend is **HTTP** (e.g. `http://VM_IP:8080`), some browsers may block “mixed content” (HTTPS page calling HTTP API). Options:

- **For a quick demo**: Use a browser that still allows mixed content for that site, or run the backend behind **HTTPS** (e.g. nginx + Let’s Encrypt on the VM, or a load balancer with a cert).
- **For production**: Serve the API over HTTPS (recommended).

---

## 3. Checklist

**On GCP (backend VM):**

- [ ] Backend container has `CORS_ORIGINS` (and optionally `FRONTEND_URL`) set to include your Vercel URL and `http://localhost:3000` if you use local dev.
- [ ] Firewall allows **ingress tcp:8080** (or your API port) to the VM.
- [ ] You know the backend base URL (e.g. `http://<VM_IP>:8080`). Prefer a **static external IP** so the URL doesn’t change.

**On Vercel (webapp):**

- [ ] Clerk env vars are set; redeploy after adding them.
- [ ] Optionally set `NEXT_PUBLIC_API_URL` to the backend URL (or leave unset and have users set the Backend URL in the app).
- [ ] Backend’s `CORS_ORIGINS` includes the Vercel app origin (e.g. `https://your-app.vercel.app`).

**Users:**

- [ ] After login, set **Backend URL** in the bar to the current backend base URL if not using `NEXT_PUBLIC_API_URL`.
