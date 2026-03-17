# scripts/add_indexes.py
"""
Add missing indexes to existing database without losing data.
Run this ONCE after updating models.
"""

import sys
import os

# ✅ Add project root to Python path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Now imports will work
from db.models import engine


from models import engine
from sqlalchemy import text


def add_indexes():
    """Add indexes to existing tables"""
    
    with engine.connect() as conn:
        print("📊 Adding indexes to existing database...")
        
        # User table indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_username ON users (username)"))
        print("✅ Added index: users.username")
        
        # Poster table indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_event_date ON posters (event_date)"))
        print("✅ Added index: posters.event_date")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_status ON posters (status)"))
        print("✅ Added index: posters.status")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_moderated_by ON posters (moderated_by)"))
        print("✅ Added index: posters.moderated_by")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_moderated_at ON posters (moderated_at)"))
        print("✅ Added index: posters.moderated_at")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_channel_chat_id ON posters (channel_chat_id)"))
        print("✅ Added index: posters.channel_chat_id")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_is_anonymous ON posters (is_anonymous)"))
        print("✅ Added index: posters.is_anonymous")
        
        # Composite indexes
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_status_moderated_at ON posters (status, moderated_at)"))
        print("✅ Added composite index: posters(status, moderated_at)")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_user_id_status ON posters (user_id, status)"))
        print("✅ Added composite index: posters(user_id, status)")
        
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_posters_event_date_status ON posters (event_date, status)"))
        print("✅ Added composite index: posters(event_date, status)")
        
        conn.commit()
        
        print("\n✅ All indexes added successfully!")

if __name__ == "__main__":
    add_indexes()