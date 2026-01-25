# Quick Start Guide

## How to Deploy & Access Your RAG Platform

### Prerequisites Check
- ✅ GCP VM running (bioct-rag-strat-1)
- ✅ vLLM container running on VM at port 11434
- ✅ One-time GitHub Actions setup completed

### Deploy New Code

**Simple**: Just push to the `release/strat-1` branch:

```bash
# Make your changes in backend/
git add .
git commit -m "Your changes"
git push origin release/strat-1
```

**That's it!** GitHub Actions automatically:
1. Builds Docker image
2. Pushes to Artifact Registry  
3. Deploys to your GCP VM
4. Starts the backend container with proper networking
5. Verifies health endpoints

Watch the deployment at: `https://github.com/YOUR_USERNAME/RAG-Platform/actions`

### Access Your Backend

#### 1. Get Your VM's External IP

```bash
gcloud compute instances describe bioct-rag-strat-1 \
  --zone=us-central1-c \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Example output: `34.73.123.456`

#### 2. Access the Swagger UI

Open in your browser:
```
http://34.73.123.456:8080/docs
```

#### 3. Test the API

```bash
# Replace EXTERNAL_IP with your VM's IP
EXTERNAL_IP="34.73.123.456"

# Health check
curl http://$EXTERNAL_IP:8080/health

# Expected: {"status":"ok"}

# LLM connectivity check
curl http://$EXTERNAL_IP:8080/health/llm

# Expected: {"status":"healthy","base_url":"http://localhost:11434/v1",...}

# Upload a PDF for processing
curl -X POST "http://$EXTERNAL_IP:8080/documents/canonical" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf" \
  | jq '.'
```

### How the Networking Works

```
┌─────────────────────────────────────────────┐
│         Your GCP VM                         │
│                                             │
│  ┌──────────────────────────────────────┐  │
│  │  vLLM Container                       │  │
│  │  Port: 11434 (internal only)         │  │
│  │  Endpoint: /v1/chat/completions      │  │
│  └──────────────────────────────────────┘  │
│                    ▲                        │
│                    │                        │
│          localhost:11434/v1                 │
│          (--network host)                   │
│                    │                        │
│  ┌──────────────────────────────────────┐  │
│  │  Backend Container                    │  │
│  │  Port: 8080 (external)                │  │
│  │  Auto-starts on VM boot               │  │
│  │  Auto-restarts on failure             │  │
│  └──────────────────────────────────────┘  │
│                    │                        │
└────────────────────┼────────────────────────┘
                     │
                     ▼
           External IP:8080
                     │
              ┌──────┴──────┐
              │    You      │
              │  (Browser)  │
              └─────────────┘
```

**Key Points:**
- Backend listens on port **8080** and is accessible via the VM's external IP
- vLLM listens on port **11434** but is **NOT** accessible externally (security)
- Backend uses `--network host` to communicate with vLLM via localhost
- The GitHub Actions workflow automatically starts the backend container
- Container is set to `--restart unless-stopped` so it survives VM reboots

### Common Commands

#### View Backend Logs

```bash
# SSH to your VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# View backend logs
docker logs rag-backend

# Follow logs in real-time
docker logs -f rag-backend

# View last 50 lines
docker logs --tail 50 rag-backend
```

#### Check Container Status

```bash
# SSH to VM first
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Check if containers are running
docker ps | grep -E 'rag-backend|llama'

# Check backend container details
docker inspect rag-backend
```

#### Manually Restart Backend (if needed)

```bash
# SSH to VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Restart container
docker restart rag-backend

# Or stop and start
docker stop rag-backend
docker start rag-backend
```

#### View Deployment History

Check deployed images:
```bash
gcloud artifacts docker images list \
  us-central1-docker.pkg.dev/YOUR_PROJECT_ID/rag-backend/rag-backend
```

### Troubleshooting

#### Backend Not Responding on External IP

**Check:**
1. Container is running: `docker ps | grep rag-backend`
2. Port is exposed: `docker port rag-backend`
3. Firewall allows port 8080: `gcloud compute firewall-rules list | grep 8080`

**Fix:**
```bash
# Restart container
docker restart rag-backend

# Check logs for errors
docker logs --tail 100 rag-backend
```

#### LLM Health Check Fails

**Check:**
1. vLLM container is running: `docker ps | grep llama`
2. vLLM is responding: `curl http://localhost:11434/v1/models`

**Fix:**
```bash
# Restart vLLM container
docker restart llama31-8b

# If not running, start it:
docker run -d \
  --name llama31-8b \
  --gpus all \
  -p 11434:8000 \
  vllm/vllm-openai:latest \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --host 0.0.0.0 \
  --port 8000 \
  --max-model-len 8192 \
  --gpu-memory-utilization 0.9
```

#### Workflow Fails

**Check GitHub Actions logs:**
1. Go to `https://github.com/YOUR_USERNAME/RAG-Platform/actions`
2. Click on the failed workflow run
3. Review the error in the logs

**Common issues:**
- Missing GitHub Secrets → Add them in repo settings
- Workload Identity not set up → Follow Step 2 in docs/README.md
- VM not accessible via IAP → Enable IAP and firewall rules (Step 5)

### Need Help?

- Full deployment guide: [DEPLOYMENT.md](DEPLOYMENT.md)
- CI/CD setup: [.github/workflows/README.md](.github/workflows/README.md)
- Architecture details: [docs/README.md](docs/README.md)
