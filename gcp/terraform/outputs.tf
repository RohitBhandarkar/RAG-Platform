# Terraform Outputs

output "postgres_instance_connection_name" {
  description = "Connection name for Cloud SQL instance"
  value       = google_sql_database_instance.postgres.connection_name
}

output "frontend_bucket_url" {
  description = "URL for frontend bucket"
  value       = "https://storage.googleapis.com/${google_storage_bucket.frontend.name}/index.html"
}

output "raw_docs_bucket" {
  description = "Raw documents bucket name"
  value       = google_storage_bucket.raw_docs.name
}

output "processed_docs_bucket" {
  description = "Processed documents bucket name"
  value       = google_storage_bucket.processed_docs.name
}
