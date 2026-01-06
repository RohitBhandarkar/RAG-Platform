"""
Database Setup Script
Creates PostgreSQL database and tables
"""
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.models.user import Base as UserBase
from backend.app.models.formulation import Base as FormulationBase
from backend.app.models.document import Base as DocumentBase
from backend.app.config import settings


def setup_database():
    """
    Create database and all tables
    """
    print(f"Connecting to database: {settings.DATABASE_URL}")
    
    # Create engine
    engine = create_engine(settings.DATABASE_URL)
    
    # Create all tables
    print("Creating tables...")
    UserBase.metadata.create_all(bind=engine)
    FormulationBase.metadata.create_all(bind=engine)
    DocumentBase.metadata.create_all(bind=engine)
    
    print("✓ Database setup complete!")
    
    # Test connection
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        session.execute("SELECT 1")
        print("✓ Database connection test successful")
    except Exception as e:
        print(f"✗ Database connection test failed: {e}")
    finally:
        session.close()


if __name__ == "__main__":
    setup_database()
