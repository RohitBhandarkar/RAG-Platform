# Terraform Configuration for RAG Platform
# Main infrastructure setup

terraform {
  required_version = ">= 1.0"
  
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# Cloud SQL Instance
resource "google_sql_database_instance" "postgres" {
  name             = "rag-postgres"
  database_version = "POSTGRES_15"
  region           = var.region
  
  settings {
    tier = "db-f1-micro"
    
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        name  = "all"
        value = "0.0.0.0/0"
      }
    }
    
    backup_configuration {
      enabled = true
    }
  }
  
  deletion_protection = false
}

# Cloud SQL Database
resource "google_sql_database" "database" {
  name     = "formulation_rag"
  instance = google_sql_database_instance.postgres.name
}

# Cloud Storage Buckets
resource "google_storage_bucket" "raw_docs" {
  name          = "${var.project_id}-rag-raw-docs"
  location      = var.region
  force_destroy = true
  
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "processed_docs" {
  name          = "${var.project_id}-rag-processed-docs"
  location      = var.region
  force_destroy = true
  
  uniform_bucket_level_access = true
}

resource "google_storage_bucket" "frontend" {
  name          = "${var.project_id}-rag-frontend"
  location      = var.region
  force_destroy = true
  
  uniform_bucket_level_access = true
  
  website {
    main_page_suffix = "index.html"
    not_found_page   = "index.html"
  }
}

# Make frontend bucket public
resource "google_storage_bucket_iam_member" "frontend_public" {
  bucket = google_storage_bucket.frontend.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

# Secret Manager Secrets
resource "google_secret_manager_secret" "openai_key" {
  secret_id = "openai-api-key"
  
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret" "postgres_password" {
  secret_id = "postgres-password"
  
  replication {
    auto {}
  }
}
