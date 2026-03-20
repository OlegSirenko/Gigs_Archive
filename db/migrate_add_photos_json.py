"""
Migration script to add photos_json column to posters table.
Run this once to update the database schema.
"""
import sqlite3
from config import config

DATABASE_PATH = config.database_path

def migrate():
    """Add photos_json column to posters table"""
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    
    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(posters)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'photos_json' in columns:
            print("✅ Column 'photos_json' already exists")
            return
        
        # Add column
        cursor.execute("""
            ALTER TABLE posters 
            ADD COLUMN photos_json TEXT NULL
        """)
        
        conn.commit()
        print("✅ Migration successful: Added 'photos_json' column to 'posters' table")
        
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
