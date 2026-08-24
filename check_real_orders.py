import sqlite3
import pandas as pd
import sys

db_path = r'C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\sfa_ifa_pro.db'
try:
    conn = sqlite3.connect(db_path)
    
    # Get last 5 NON-REJECTED orders
    orders_df = pd.read_sql_query("SELECT id, timestamp, type, status, entry_price, close_price, profit_loss, reason FROM orders WHERE status != 'REJECTED' ORDER BY timestamp DESC LIMIT 5", conn)
    print("--- ÚLTIMAS ÓRDENES (NO RECHAZADAS) ---")
    if orders_df.empty:
        print("No hay órdenes no rechazadas registradas.")
    else:
        print(orders_df.to_string(index=False))
        
    conn.close()
except Exception as e:
    print(f"Error reading DB: {e}")
