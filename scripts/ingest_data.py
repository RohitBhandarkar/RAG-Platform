"""
Data Ingestion Script
Ingest data from various sources into the system
"""
import asyncio
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.data.ingestion.pubmed_ingester import PubMedIngester
from backend.app.data.ingestion.fda_ingester import FDAIngester
from backend.app.data.ingestion.document_processor import DocumentProcessor


async def ingest_pubmed_data():
    """Ingest data from PubMed"""
    print("Starting PubMed ingestion...")
    ingester = PubMedIngester()
    
    queries = [
        "SEDDS formulation solubility enhancement",
        "amorphous solid dispersion bioavailability",
        "nanosuspension drug delivery"
    ]
    
    for query in queries:
        print(f"  Searching: {query}")
        # results = await ingester.search(query, max_results=50)
        # TODO: Process and store results
    
    print("✓ PubMed ingestion complete")


async def ingest_fda_data():
    """Ingest data from FDA databases"""
    print("Starting FDA ingestion...")
    ingester = FDAIngester()
    
    # iid_data = await ingester.fetch_iid_data()
    # TODO: Process and store IID data
    
    print("✓ FDA ingestion complete")


async def main():
    """Main ingestion pipeline"""
    print("=== Data Ingestion Pipeline ===\n")
    
    # await ingest_pubmed_data()
    # await ingest_fda_data()
    
    print("\n=== Ingestion Complete ===")


if __name__ == "__main__":
    asyncio.run(main())
