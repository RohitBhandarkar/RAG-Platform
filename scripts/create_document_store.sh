#!/usr/bin/env bash
# Script to create or reset the document store layout used by the backend.
# Usage:
#   ./create_document_store.sh [BASE_DIR]
# If BASE_DIR is not provided, it defaults to ../data relative to this script.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_BASE_DIR="${SCRIPT_DIR}/../data"
BASE_DIR="${1:-$DEFAULT_BASE_DIR}"

RAW_DIR="${BASE_DIR}/raw"
PROCESSED_DIR="${BASE_DIR}/processed"
EMBEDDINGS_DIR="${BASE_DIR}/embeddings"

echo "Using base document store directory: ${BASE_DIR}"

if [[ -d "${RAW_DIR}" || -d "${PROCESSED_DIR}" || -d "${EMBEDDINGS_DIR}" ]]; then
  echo "Existing document store layout detected under: ${BASE_DIR}"
  read -r -p "This will DELETE all contents under raw/, processed/, and embeddings/. Continue? [y/N] " confirm
  case "${confirm}" in
    [yY])
      echo "Removing existing layout..."
      rm -rf "${RAW_DIR}" "${PROCESSED_DIR}" "${EMBEDDINGS_DIR}"
      ;;
    *)
      echo "Aborting without changes."
      exit 0
      ;;
  esac
fi

echo "Creating document store layout..."

mkdir -p "${RAW_DIR}"/pubmed
mkdir -p "${RAW_DIR}"/patents
mkdir -p "${RAW_DIR}"/fda
mkdir -p "${RAW_DIR}"/user_uploads

mkdir -p "${PROCESSED_DIR}"/pubmed
mkdir -p "${PROCESSED_DIR}"/patents
mkdir -p "${PROCESSED_DIR}"/fda
mkdir -p "${PROCESSED_DIR}"/user_uploads

mkdir -p "${EMBEDDINGS_DIR}"

echo "Document store layout ensured at: ${BASE_DIR}"

echo "Creating canonical JSON schema..."
python3 "${SCRIPT_DIR}/canonical_json_builder.py" "${BASE_DIR}/canonical.json"
