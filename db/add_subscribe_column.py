import sys, os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from db.models import engine
from sqlalchemy import text

with engine.connect() as conn:
    try:
        conn.execute(text("ALTER TABLE users ADD COLUMN subscribe_weekly BOOLEAN DEFAULT FALSE"))
        print("✅ Added subscribe_weekly column")
    except Exception as e:
        if "duplicate" not in str(e).lower():
            print(f"❌ Error: {e}")
    conn.commit()

print("✅ Migration complete!")
