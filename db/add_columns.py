"""
Add missing columns to existing database without losing data.
Run this ONCE after updating models.

Usage:
    python db/add_columns.py
"""

import sys
import os

# ✅ Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db.models import engine
from sqlalchemy import text

def add_columns():
    """Add missing columns to posters table"""
    
    print("🔧 Adding missing columns to existing database...")
    print("=" * 60)
    
    with engine.connect() as conn:
        # Check if columns exist first (SQLite doesn't support IF NOT EXISTS for ALTER)
        
        # Add moderator_notes column
        try:
            conn.execute(text("ALTER TABLE posters ADD COLUMN moderator_notes TEXT"))
            print("✅ Added column: posters.moderator_notes")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Column already exists: posters.moderator_notes")
            else:
                print(f"❌ Error adding moderator_notes: {e}")
        
        # Add view_count column
        try:
            conn.execute(text("ALTER TABLE posters ADD COLUMN view_count INTEGER DEFAULT 0"))
            print("✅ Added column: posters.view_count")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Column already exists: posters.view_count")
            else:
                print(f"❌ Error adding view_count: {e}")
        
        conn.commit()
        
    print("=" * 60)
    print("✅ Database schema updated!")
    print("\n📝 Note: This script only needs to be run ONCE.")

if __name__ == "__main__":
    add_columns()