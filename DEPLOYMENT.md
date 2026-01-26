# Deployment Guide

## Recent Changes

### LLM Endpoint Configuration
- **Changed**: LLM endpoint from `http://localhost:11434` to `http://localhost:11434/v1`
- **Updated in**: `backend/app/config.py` (`LLM_BASE_URL`)
- **Reason**: vLLM uses OpenAI-compatible API at `/v1` path prefix

### Docker Networking
- **Changed**: Backend container now uses `--network host` instead of `-p 8080:8080`
- **Updated in**: `.github/workflows/deploy-backend.yml`
- **Reason**: Allows backend container to communicate with vLLM container via `localhost:11434`

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                  GCP VM (bioct-rag-strat-1)                     │
│                                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  vLLM Container (llama31-8b)                           │    │
│  │  - Internal port: 8000                                  │    │
│  │  - Host port: 11434                                     │    │
│  │  - Model: meta-llama/Meta-Llama-3.1-8B-Instruct        │    │
│  │  - API: OpenAI-compatible (/v1/chat/completions)       │    │
│  └────────────────────────────────────────────────────────┘    │
│                           ▲                                     │
│                           │                                     │
│                  localhost:11434/v1                             │
│                  (host network mode)                            │
│                           │                                     │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  Backend Container (rag-backend)                        │    │
│  │  - Port: 8080 (exposed to external IP)                 │    │
│  │  - Network: host mode                                   │    │
│  │  - Framework: FastAPI                                   │    │
│  │  - Features: PDF parsing, RAG, LLM integration         │    │
│  └────────────────────────────────────────────────────────┘    │
│                           │                                     │
└───────────────────────────┼─────────────────────────────────────┘
                            │
                            ▼
                 External IP:8080
                            │
                    ┌───────┴────────┐
                    │     Users      │
                    │  (via browser  │
                    │   or curl)     │
                    └────────────────┘
```

## Deployment Steps

### 1. Ensure vLLM is Running on VM

SSH to your VM and verify vLLM container is running:

```bash
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Check if vLLM container is running
docker ps | grep llama31-8b

# If not running, start it
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

# Verify vLLM is responding
curl http://localhost:11434/v1/models
```

### 2. Create .env File on VM

Ensure the `.env` file exists at `/home/$USER/RAG-Platform/backend/.env`:

```bash
# Create directory if needed
mkdir -p /home/$USER/RAG-Platform/backend

# Create .env file
cat > /home/$USER/RAG-Platform/backend/.env << 'EOF'
# API Configuration
API_PORT=8080
API_HOST=0.0.0.0

# LLM Configuration
LLM_BASE_URL=http://localhost:11434/v1
LLM_MODEL=llama3.1

# Database Configuration (if using)
# DATABASE_URL=postgresql://user:password@localhost:5432/dbname

# ChromaDB Configuration (if using)
# CHROMA_HOST=localhost
# CHROMA_PORT=8001
EOF
```

### 3. Push to release/strat-1 Branch

From your local machine:

```bash
# Ensure you're on the correct branch
git checkout release/strat-1

# Make your changes to backend/
# ... edit files ...

# Commit and push
git add .
git commit -m "Update backend with LLM integration"
git push origin release/strat-1
```

### 4. Monitor Deployment

The GitHub Actions workflow will automatically:
1. Build Docker image
2. Push to Artifact Registry
3. Deploy to VM
4. Verify health

Watch progress at: `https://github.com/YOUR_USERNAME/RAG-Platform/actions`

## Accessing the Deployed Backend

### Get External IP

```bash
gcloud compute instances describe bioct-rag-strat-1 \
  --zone=us-central1-c \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

### Access Swagger UI

Open in browser:
```
http://EXTERNAL_IP:8080/docs
```

### Test Endpoints

```bash
# Basic health check
curl http://EXTERNAL_IP:8080/health

# LLM connectivity check
curl http://EXTERNAL_IP:8080/health/llm

# Upload a PDF for parsing
curl -X POST "http://EXTERNAL_IP:8080/documents/canonical" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"

# Get parsed output (debug endpoint)
curl -X POST "http://EXTERNAL_IP:8080/documents/parsed" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"

# Get chunks (debug endpoint)
curl -X POST "http://EXTERNAL_IP:8080/documents/chunks" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"

# Preview LLM prompt (debug endpoint)
curl -X POST "http://EXTERNAL_IP:8080/documents/prompt-preview" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"
```

## Troubleshooting

### Backend Cannot Connect to LLM

**Symptoms**: `/health/llm` returns error, or document processing fails

**Check**:
```bash
# SSH to VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Verify vLLM is running
docker ps | grep llama31-8b

# Test vLLM endpoint
curl http://localhost:11434/v1/models

# Check backend logs
docker logs rag-backend
```

**Solution**: Ensure vLLM container is running and accessible at `localhost:11434/v1`

### Cannot Access Backend from External IP

**Symptoms**: Connection timeout or refused when accessing `EXTERNAL_IP:8080`

**Check**:
```bash
# SSH to VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Check if backend is running
docker ps | grep rag-backend

# Test from VM
curl http://localhost:8080/health

# Check firewall rules
gcloud compute firewall-rules list | grep 8080
```

**Solution**: 
- Ensure backend container is running
- Verify firewall allows port 8080
- Check VM external IP is correct

### Container Not Starting

**Symptoms**: Container exits immediately after `docker run`

**Check**:
```bash
# View container logs
docker logs rag-backend

# Check if .env file exists
ls -la /home/$USER/RAG-Platform/backend/.env

# Inspect container
docker inspect rag-backend
```

**Solution**:
- Verify `.env` file exists and has correct values
- Check logs for specific error messages
- Ensure GPU drivers are working: `nvidia-smi`

### Workflow Fails at Deployment Step

**Symptoms**: GitHub Actions workflow fails during "Deploy to GCP VM" step

**Check**:
- View workflow logs in GitHub Actions UI
- Verify GitHub Secrets are set correctly
- Check Workload Identity Federation setup

**Solution**: See [.github/workflows/README.md](.github/workflows/README.md) for troubleshooting steps

## Manual Deployment (Fallback)

If you need to deploy manually without GitHub Actions:

```bash
# SSH to VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# Pull latest code
cd ~/RAG-Platform
git pull origin release/strat-1

# Build image locally on VM
cd backend
docker build -t rag-backend:manual .

# Stop old container
docker stop rag-backend || true
docker rm rag-backend || true

# Start new container
docker run -d \
  --name rag-backend \
  --restart unless-stopped \
  --gpus all \
  --network host \
  --env-file /home/$USER/RAG-Platform/backend/.env \
  -v /home/$USER/RAG-Platform/backend/data:/app/data:ro \
  rag-backend:manual

# Verify
docker logs rag-backend
curl http://localhost:8080/health
```

## Network Configuration Notes

### Why --network host?

The backend container uses `--network host` mode to communicate with the vLLM container via `localhost`. This is necessary because:

1. vLLM runs in a separate container, exposing port 11434 on the host
2. Backend needs to call `http://localhost:11434/v1/chat/completions`
3. With host network mode, the backend container shares the host's network namespace
4. Both containers can communicate via localhost without Docker network bridges

### Port Mapping

- **vLLM**: `-p 11434:8000` → host port 11434 → container port 8000
- **Backend**: `--network host` → host port 8080 → container port 8080 (direct)

### External Access

- Users access: `http://EXTERNAL_IP:8080` → backend container
- Backend calls: `http://localhost:11434/v1` → vLLM container (internal only)
- vLLM is NOT accessible from external IP (security feature)
