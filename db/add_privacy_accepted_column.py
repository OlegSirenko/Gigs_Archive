"""
Migration: Add privacy_accepted column to users table
"""
import sqlite3
from config import config

def migrate():
    """Add privacy_accepted column to users table"""
    conn = sqlite3.connect(config.database_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if "privacy_accepted" not in columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN privacy_accepted BOOLEAN DEFAULT 0"
            )
            conn.commit()
            print("✅ Added privacy_accepted column to users table")
        else:
            print("ℹ️ Column privacy_accepted already exists")

    except Exception as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
