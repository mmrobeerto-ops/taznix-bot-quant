# ---
# title: Database Cleanup Script
# description: Cleans up audit logs older than 30 days in batches of 100
# created_type: script
# assigned_to: Antigravity
# status: completed
# ---

import os
import time
import sqlite3
import datetime

# --- CONFIGURATION PARAMETERS ---
DB_PATH = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\sfa_ifa_pro.db"
OUTPUT_FOLDER = r"C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\scratch"
LIMIT_DAYS = 30
BATCH_SIZE = 100
# --------------------------------

def main():
    print(f"Starting database cleanup for DB: {DB_PATH}")
    print(f"Retention limit: {LIMIT_DAYS} days")
    print(f"Batch size: {BATCH_SIZE}")
    
    if not os.path.exists(DB_PATH):
        print(f"Error: Database file does not exist at '{DB_PATH}'")
        return
        
    if not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER, exist_ok=True)
        
    cutoff_timestamp = time.time() - (LIMIT_DAYS * 24 * 3600)
    cutoff_date = datetime.datetime.fromtimestamp(cutoff_timestamp).strftime('%Y-%m-%d %H:%M:%S')
    print(f"Cutoff timestamp: {cutoff_timestamp} ({cutoff_date})")
    
    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='audit_logs'")
        if not cursor.fetchone():
            print("Table 'audit_logs' does not exist in the database. Nothing to clean.")
            return
            
        # Count total records to delete
        cursor.execute("SELECT COUNT(*) FROM audit_logs WHERE timestamp < ?", (cutoff_timestamp,))
        total_to_delete = cursor.fetchone()[0]
        print(f"Total log records older than {LIMIT_DAYS} days: {total_to_delete}")
        
        if total_to_delete == 0:
            print("No records need cleanup.")
            save_summary(0, total_to_delete)
            return
            
        deleted_count = 0
        while True:
            # Select next batch of IDs
            cursor.execute("SELECT id FROM audit_logs WHERE timestamp < ? LIMIT ?", (cutoff_timestamp, BATCH_SIZE))
            rows = cursor.fetchall()
            if not rows:
                break
                
            ids = [r[0] for r in rows]
            # Delete batch
            placeholders = ",".join(["?"] * len(ids))
            cursor.execute(f"DELETE FROM audit_logs WHERE id IN ({placeholders})", ids)
            conn.commit()
            
            deleted_count += len(ids)
            print(f"Deleted batch of {len(ids)} logs. Progress: {deleted_count}/{total_to_delete}")
            
            # Brief sleep to avoid heavy locking
            time.sleep(0.01)
            
        print(f"Cleanup finished. Total deleted logs: {deleted_count}")
        save_summary(deleted_count, total_to_delete)
        
    except Exception as e:
        print(f"An error occurred during database cleanup: {e}")
    finally:
        if conn:
            conn.close()

def save_summary(deleted, total):
    summary_path = os.path.join(OUTPUT_FOLDER, "cleanup_summary.txt")
    try:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write(f"Cleanup Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Database Path: {DB_PATH}\n")
            f.write(f"Retention Limit: {LIMIT_DAYS} days\n")
            f.write(f"Total Matching Logs: {total}\n")
            f.write(f"Total Deleted Logs: {deleted}\n")
            f.write("Status: SUCCESS\n")
        print(f"Summary saved to: {summary_path}")
    except Exception as e:
        print(f"Failed to write summary: {e}")

if __name__ == "__main__":
    main()
