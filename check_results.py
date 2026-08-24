import sqlite3
import pandas as pd
import sys

db_path = r'C:\Users\52664\.gemini\antigravity\scratch\sfa-ifa-pro\app\sfa_ifa_pro.db'
try:
    conn = sqlite3.connect(db_path)
    
    # Get last 10 orders
    orders_df = pd.read_sql_query("SELECT id, timestamp, type, status, entry_price, close_price, profit_loss, reason FROM orders ORDER BY timestamp DESC LIMIT 20", conn)
    print("--- ÚLTIMAS ÓRDENES ---")
    if orders_df.empty:
        print("No hay órdenes registradas.")
    else:
        print(orders_df.to_string(index=False))
        
    print("\n--- RESUMEN DE P&L ---")
    pnl_df = pd.read_sql_query("SELECT COUNT(*) as total_trades, SUM(profit_loss) as total_pnl, SUM(CASE WHEN profit_loss > 0 THEN 1 ELSE 0 END) as wins, SUM(CASE WHEN profit_loss < 0 THEN 1 ELSE 0 END) as losses FROM orders WHERE status = 'CLOSED'", conn)
    print(pnl_df.to_string(index=False))
    
    print("\n--- ÚLTIMOS LOGS DE AUDITORÍA ---")
    logs_df = pd.read_sql_query("SELECT timestamp, level, message FROM audit_logs ORDER BY timestamp DESC LIMIT 15", conn)
    print(logs_df.to_string(index=False))
    
    conn.close()
except Exception as e:
    print(f"Error reading DB: {e}")
