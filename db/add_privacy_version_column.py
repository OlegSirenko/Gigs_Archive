"""
Migration: Add privacy_version_accepted column to users table
"""
import sqlite3
from config import config

def migrate():
    """Add privacy_version_accepted column to users table"""
    conn = sqlite3.connect(config.database_path)
    cursor = conn.cursor()

    try:
        # Check if column already exists
        cursor.execute("PRAGMA table_info(users)")
        columns = [column[1] for column in cursor.fetchall()]

        if "privacy_version_accepted" not in columns:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN privacy_version_accepted TEXT"
            )
            conn.commit()
            print("✅ Added privacy_version_accepted column to users table")
        else:
            print("ℹ️ Column privacy_version_accepted already exists")

        # Optional: Set default version for users who already accepted
        cursor.execute(
            "UPDATE users SET privacy_version_accepted = '1.0' WHERE privacy_accepted = 1 AND privacy_version_accepted IS NULL"
        )
        conn.commit()
        print("✅ Updated existing users with default version 1.0")

    except Exception as e:
        print(f"❌ Migration error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
