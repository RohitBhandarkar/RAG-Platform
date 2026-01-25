# GitHub Actions CI/CD for RAG Backend

This directory contains automated deployment workflows for the RAG Platform backend.

## Workflow: deploy-backend.yml

Automatically builds, pushes, and deploys the backend Docker image to a GCP VM with GPU support.

### Triggers
- **Automatic**: Pushes to `release/strat-1` branch that modify `backend/**` or the workflow file
- **Manual**: Workflow dispatch from GitHub Actions UI

### What it does
1. Checks out code
2. Authenticates to GCP using Workload Identity Federation (no keys!)
3. Builds Docker image with commit SHA and `latest` tags
4. Pushes to Google Artifact Registry
5. SSH to VM via IAP tunnel
6. Pulls new image, stops old container, starts new one
7. Verifies health endpoints
8. Cleans up old images (keeps last 5)

## Initial Setup (One-time)

### Step 1: Create Artifact Registry Repository

```bash
gcloud artifacts repositories create rag-backend \
  --repository-format=docker \
  --location=us-east1 \
  --description="RAG Platform Backend Docker Images"
```

### Step 2: Set up Workload Identity Federation

Create a Workload Identity Pool and Provider to allow GitHub Actions to authenticate without service account keys:

```bash
# Set variables
export PROJECT_ID="your-gcp-project-id"
export POOL_NAME="github-actions-pool"
export PROVIDER_NAME="github-provider"
export SERVICE_ACCOUNT_NAME="github-actions-deployer"
export GITHUB_REPO="your-github-username/RAG-Platform"

# Create service account
gcloud iam service-accounts create ${SERVICE_ACCOUNT_NAME} \
  --display-name="GitHub Actions Deployer"

# Grant necessary permissions
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/artifactregistry.writer"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/compute.instanceAdmin.v1"

gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"

# Create Workload Identity Pool
gcloud iam workload-identity-pools create ${POOL_NAME} \
  --location="global" \
  --display-name="GitHub Actions Pool"

# Create Workload Identity Provider
gcloud iam workload-identity-pools providers create-oidc ${PROVIDER_NAME} \
  --location="global" \
  --workload-identity-pool=${POOL_NAME} \
  --display-name="GitHub Provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.repository_owner=assertion.repository_owner" \
  --attribute-condition="assertion.repository_owner == '${GITHUB_REPO%%/*}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Allow GitHub Actions to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding \
  ${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/$(gcloud projects describe ${PROJECT_ID} --format='value(projectNumber)')/locations/global/workloadIdentityPools/${POOL_NAME}/attribute.repository/${GITHUB_REPO}"

# Get the Workload Identity Provider resource name (save this for GitHub Secrets)
gcloud iam workload-identity-pools providers describe ${PROVIDER_NAME} \
  --location="global" \
  --workload-identity-pool=${POOL_NAME} \
  --format="value(name)"
```

### Step 3: Configure VM Docker Authentication

SSH to your GCP VM and set up Docker authentication:

```bash
gcloud compute ssh bioct-rag-strat-1 --zone=us-east1-b --tunnel-through-iap

# On the VM
gcloud auth configure-docker us-east1-docker.pkg.dev
```

### Step 4: Set GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Value | Example |
|------------|-------|---------|
| `GCP_PROJECT_ID` | Your GCP project ID | `bioct-rag-platform` |
| `GCP_VM_ZONE` | Zone where your VM is located | `us-east1-b` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full resource name from Step 2 | `projects/123.../locations/global/workloadIdentityPools/...` |
| `GCP_SERVICE_ACCOUNT` | Service account email | `github-actions-deployer@PROJECT_ID.iam.gserviceaccount.com` |

### Step 5: Enable IAP for SSH

```bash
# Enable IAP API
gcloud services enable iap.googleapis.com

# Grant the service account IAP tunnel user role
gcloud projects add-iam-policy-binding ${PROJECT_ID} \
  --member="serviceAccount:${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iap.tunnelResourceAccessor"

# Allow IAP to connect to your VM
gcloud compute firewall-rules create allow-ssh-ingress-from-iap \
  --direction=INGRESS \
  --action=allow \
  --rules=tcp:22 \
  --source-ranges=35.235.240.0/20
```

## Usage

### Normal Deployment Flow

1. Make changes to `backend/` directory
2. Commit and push to `release/strat-1` branch
3. GitHub Actions automatically:
   - Builds Docker image
   - Pushes to Artifact Registry
   - Deploys to GCP VM
   - Verifies health

### Manual Trigger

Go to GitHub Actions → Deploy Backend to GCP → Run workflow

### Rollback

To rollback to a previous version:

```bash
# List available images
gcloud artifacts docker images list \
  us-east1-docker.pkg.dev/${PROJECT_ID}/rag-backend/rag-backend

# SSH to VM
gcloud compute ssh bioct-rag-strat-1 --zone=us-east1-b --tunnel-through-iap

# On VM, pull and run specific version
docker pull us-east1-docker.pkg.dev/${PROJECT_ID}/rag-backend/rag-backend:COMMIT_SHA
docker stop rag-backend && docker rm rag-backend
docker run -d \
  --name rag-backend \
  --restart unless-stopped \
  --gpus all \
  --network host \
  --env-file /home/$USER/RAG-Platform/backend/.env \
  -v /home/$USER/RAG-Platform/backend/data:/app/data:ro \
  us-east1-docker.pkg.dev/${PROJECT_ID}/rag-backend/rag-backend:COMMIT_SHA
```

## Accessing the Deployed Backend

### Get External IP

```bash
gcloud compute instances describe bioct-rag-strat-1 \
  --zone=us-east1-b \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

### Access Swagger UI

Open in browser: `http://EXTERNAL_IP:8080/docs`

### Test Health Endpoints

```bash
# Basic health check
curl http://EXTERNAL_IP:8080/health

# LLM connectivity check (verifies backend can reach vLLM)
curl http://EXTERNAL_IP:8080/health/llm
```

### Upload a PDF

```bash
curl -X POST "http://EXTERNAL_IP:8080/documents/canonical" \
  -H "accept: application/json" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"
```

**Note**: The LLM endpoint (`http://localhost:11434/v1`) is only accessible internally within the VM via `--network host`. External users cannot directly access it.

## Monitoring & Troubleshooting

### View Workflow Logs

GitHub → Actions → Deploy Backend to GCP → Select run

### View Container Logs on VM

```bash
gcloud compute ssh bioct-rag-strat-1 --zone=us-east1-b --tunnel-through-iap

# View recent logs
docker logs rag-backend

# Follow logs in real-time
docker logs -f rag-backend

# Last 100 lines
docker logs --tail 100 rag-backend
```

### Check Container Status

```bash
docker ps -a | grep rag-backend
docker inspect rag-backend
```

### Common Issues

**Issue**: Workflow fails at authentication step
- **Solution**: Verify Workload Identity Federation setup, check GitHub Secrets

**Issue**: Container fails to start
- **Solution**: Check `.env` file exists on VM at `/home/$USER/RAG-Platform/backend/.env`

**Issue**: Health check fails
- **Solution**: Ensure vLLM container is running on port 11434, check `docker logs rag-backend`

**Issue**: Cannot access from external IP
- **Solution**: Verify firewall rules allow port 8080, check VM external IP is correct

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                     GCP VM (bioct-rag-strat-1)          │
│                                                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │  vLLM Container                                   │  │
│  │  - Port 11434 (internal only)                     │  │
│  │  - Model: meta-llama/Meta-Llama-3.1-8B-Instruct  │  │
│  │  - Endpoint: /v1/chat/completions                 │  │
│  └──────────────────────────────────────────────────┘  │
│                          ▲                              │
│                          │ localhost:11434/v1           │
│                          │ (--network host)             │
│  ┌──────────────────────────────────────────────────┐  │
│  │  Backend Container                                │  │
│  │  - Port 8080 (external)                           │  │
│  │  - FastAPI + RAG Engine                           │  │
│  │  - Auto-restarts on failure                       │  │
│  └──────────────────────────────────────────────────┘  │
│                          │                              │
└──────────────────────────┼──────────────────────────────┘
                           │
                           ▼ External IP:8080
                    ┌──────────────┐
                    │    Users     │
                    └──────────────┘
```

## CI/CD Flow

```
Code Push (release/strat-1)
  │
  ▼
GitHub Actions Triggered
  │
  ├─► Authenticate (Workload Identity)
  ├─► Build Docker Image
  ├─► Push to Artifact Registry
  ├─► SSH to VM (IAP Tunnel)
  ├─► Pull New Image
  ├─► Stop Old Container
  ├─► Start New Container
  ├─► Verify Health
  └─► Cleanup Old Images
  │
  ▼
Deployment Complete ✓
```
