#!/bin/bash

# GCP Initial Setup Script
# Sets up GCP project and basic infrastructure

set -e

PROJECT_ID="${1:-your-project-id}"
BILLING_ACCOUNT="${2}"

echo "=== Setting up GCP Project ==="
echo "Project ID: $PROJECT_ID"
echo ""

# Create project if it doesn't exist
echo "Creating project..."
gcloud projects create $PROJECT_ID --name="RAG Platform" || echo "Project already exists"

# Set project
gcloud config set project $PROJECT_ID

# Link billing account if provided
if [ ! -z "$BILLING_ACCOUNT" ]; then
  echo "Linking billing account..."
  gcloud billing projects link $PROJECT_ID --billing-account=$BILLING_ACCOUNT
fi

# Enable required APIs
echo "Enabling APIs..."
gcloud services enable cloudresourcemanager.googleapis.com
gcloud services enable serviceusage.googleapis.com
gcloud services enable iam.googleapis.com

# Create service account
echo "Creating service account..."
gcloud iam service-accounts create rag-platform-sa \
  --description="Service account for RAG Platform" \
  --display-name="RAG Platform Service Account" \
  || echo "Service account already exists"

# Grant necessary roles
echo "Granting IAM roles..."
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:rag-platform-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/run.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:rag-platform-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:rag-platform-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.admin"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:rag-platform-sa@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/aiplatform.user"

echo ""
echo "=== Setup Complete ==="
echo "Next steps:"
echo "1. Run ./deploy.sh $PROJECT_ID to deploy the application"
echo "2. Configure your .env file with GCP credentials"
