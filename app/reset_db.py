import os
import shutil
from app.database import DB_PATH, SessionLocal, OrderModel, AuditLogModel

def reset():
    print(f"Database path: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Database file does not exist.")
        return

    # 1. Create a backup of the current database
    backup_path = DB_PATH.replace(".db", "_backup_sim.db")
    print(f"Creating backup at: {backup_path}")
    shutil.copy2(DB_PATH, backup_path)

    # 2. Open DB Session and delete orders and logs
    db = SessionLocal()
    try:
        print("Clearing orders table...")
        db.query(OrderModel).delete()
        
        print("Clearing audit logs table...")
        db.query(AuditLogModel).delete()
        
        db.commit()
        print("Database successfully cleared (retaining config and ticks).")
    except Exception as e:
        print(f"Error resetting database: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    reset()
