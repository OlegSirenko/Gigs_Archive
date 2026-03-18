# db/add_moderation_columns.py
"""
Add moderation_message_id and moderation_chat_id columns to existing database.
Run this ONCE after updating models.

Usage:
    python db/add_moderation_columns.py
"""

import sys
import os

# Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db.models import engine
from sqlalchemy import text

def add_columns():
    """Add missing columns to posters table"""
    
    print("🔧 Adding moderation columns to existing database...")
    print("=" * 60)
    
    with engine.connect() as conn:
        # Add moderation_message_id column
        try:
            conn.execute(text("ALTER TABLE posters ADD COLUMN moderation_message_id INTEGER"))
            print("✅ Added column: posters.moderation_message_id")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Column already exists: posters.moderation_message_id")
            else:
                print(f"❌ Error adding moderation_message_id: {e}")
        
        # Add moderation_chat_id column
        try:
            conn.execute(text("ALTER TABLE posters ADD COLUMN moderation_chat_id INTEGER"))
            print("✅ Added column: posters.moderation_chat_id")
        except Exception as e:
            if "duplicate column name" in str(e).lower():
                print("⚠️  Column already exists: posters.moderation_chat_id")
            else:
                print(f"❌ Error adding moderation_chat_id: {e}")
        
        conn.commit()
        
    print("=" * 60)
    print("✅ Database schema updated!")
    print("\n📝 Note: This script only needs to be run ONCE.")

if __name__ == "__main__":
    add_columns()