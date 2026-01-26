# RAG Platform Documentation

This directory contains project documentation.

## Contents

- API documentation (auto-generated from FastAPI)
- Architecture diagrams
- Development guides
- Deployment guides
- User manuals

## External Documentation

See the parent directory for:
- [design.md](../design.md) - Complete system design
- [README.md](../README.md) - Project overview
- [DEPLOYMENT.md](../DEPLOYMENT.md) - Deployment instructions with architecture
- [.github/workflows/README.md](../.github/workflows/README.md) - CI/CD setup guide

## Quick Start: Automated Deployment to GCP

### Prerequisites

1. GCP VM with GPU (g2-standard-8 with L4 or a2-highgpu-1g with A100)
2. vLLM container running on the VM (port 11434)
3. GitHub repository with release/strat-1 branch

### One-Time Setup

#### Step 1: Create Artifact Registry Repository

```bash
gcloud artifacts repositories create rag-backend \
  --repository-format=docker \
  --location=us-central1 \
  --description="RAG Platform Backend Docker Images"
```

#### Step 2: Set up Workload Identity Federation

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

#### Step 3: Configure VM Docker Authentication

SSH to your GCP VM and set up Docker authentication:

```bash
gcloud compute ssh bioct-rag-strat-1 --zone=us-central1-c --tunnel-through-iap

# On the VM
gcloud auth configure-docker us-central1-docker.pkg.dev
```

#### Step 4: Set GitHub Secrets

Add these secrets to your GitHub repository (Settings → Secrets and variables → Actions):

| Secret Name | Value | Example |
|------------|-------|---------|
| `GCP_PROJECT_ID` | Your GCP project ID | `bioct-rag-platform` |
| `GCP_VM_ZONE` | Zone where your VM is located | `us-central1-c` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | Full resource name from Step 2 | `projects/123.../locations/global/workloadIdentityPools/...` |
| `GCP_SERVICE_ACCOUNT` | Service account email | `github-actions-deployer@PROJECT_ID.iam.gserviceaccount.com` |

#### Step 5: Enable IAP for SSH

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

### Deploy the Backend

1. Make changes to the `backend/` directory
2. Commit and push to `release/strat-1` branch
3. GitHub Actions automatically builds, pushes, and deploys

### Access the Application

Get your VM's external IP:

```bash
gcloud compute instances describe bioct-rag-strat-1 \
  --zone=us-central1-c \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)'
```

Access the Swagger UI in your browser:
```
http://EXTERNAL_IP:8080/docs
```

Test the API:
```bash
# Health check
curl http://EXTERNAL_IP:8080/health

# LLM connectivity check
curl http://EXTERNAL_IP:8080/health/llm

# Upload a PDF
curl -X POST "http://EXTERNAL_IP:8080/documents/canonical" \
  -H "Content-Type: multipart/form-data" \
  -F "file=@your_paper.pdf"
```

## Architecture

The backend runs in a Docker container on a GCP VM with:
- **Backend**: Port 8080 (externally accessible)
- **vLLM**: Port 11434 (internal only, accessed via localhost by backend)
- **Network**: Host mode for container-to-container communication

For complete details, see [DEPLOYMENT.md](../DEPLOYMENT.md)
