#!/bin/bash

# GCP Deployment Script
# Deploys RAG Platform to Google Cloud Platform

set -e

PROJECT_ID="${1:-your-project-id}"
REGION="${2:-us-central1}"

echo "=== Deploying RAG Platform to GCP ==="
echo "Project ID: $PROJECT_ID"
echo "Region: $REGION"
echo ""

# Set project
gcloud config set project $PROJECT_ID

# Enable required APIs
echo "Enabling required APIs..."
gcloud services enable run.googleapis.com
gcloud services enable sqladmin.googleapis.com
gcloud services enable aiplatform.googleapis.com
gcloud services enable storage-api.googleapis.com
gcloud services enable secretmanager.googleapis.com
gcloud services enable cloudbuild.googleapis.com
gcloud services enable logging.googleapis.com
gcloud services enable monitoring.googleapis.com

# Create Cloud SQL instance
echo "Creating Cloud SQL instance..."
gcloud sql instances create rag-db \
  --database-version=POSTGRES_15 \
  --tier=db-f1-micro \
  --region=$REGION \
  --network=default \
  || echo "Cloud SQL instance already exists"

# Create database
echo "Creating database..."
gcloud sql databases create formulation_rag \
  --instance=rag-db \
  || echo "Database already exists"

# Create Cloud Storage buckets
echo "Creating Cloud Storage buckets..."
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${PROJECT_ID}-rag-raw-docs || echo "Bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${PROJECT_ID}-rag-processed-docs || echo "Bucket already exists"
gsutil mb -p $PROJECT_ID -c STANDARD -l $REGION gs://${PROJECT_ID}-rag-frontend || echo "Bucket already exists"

# Configure frontend bucket for static website hosting
echo "Configuring frontend bucket..."
gsutil web set -m index.html -e index.html gs://${PROJECT_ID}-rag-frontend
gsutil iam ch allUsers:objectViewer gs://${PROJECT_ID}-rag-frontend

# Store secrets in Secret Manager
echo "Storing secrets..."
echo "Please enter your OpenAI API key:"
read -s OPENAI_KEY
echo -n "$OPENAI_KEY" | gcloud secrets create openai-api-key --data-file=- || echo "Secret already exists"

echo "Please enter your database password:"
read -s DB_PASSWORD
echo -n "$DB_PASSWORD" | gcloud secrets create postgres-password --data-file=- || echo "Secret already exists"

# Build and deploy with Cloud Build
echo "Building and deploying..."
gcloud builds submit --config=gcp/cloudbuild.yaml --substitutions=_FRONTEND_BUCKET=${PROJECT_ID}-rag-frontend

echo ""
echo "=== Deployment Complete ==="
echo "Backend: https://rag-backend-[hash]-uc.a.run.app"
echo "Frontend: https://storage.googleapis.com/${PROJECT_ID}-rag-frontend/index.html"
