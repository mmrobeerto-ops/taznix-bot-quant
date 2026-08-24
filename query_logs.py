import sqlite3
import datetime

conn = sqlite3.connect('app/sfa_ifa_pro.db')
rows = conn.cursor().execute("SELECT timestamp, message FROM audit_logs WHERE level='ERROR' ORDER BY timestamp DESC LIMIT 3").fetchall()
for r in reversed(rows):
    print(f"[{datetime.datetime.fromtimestamp(r[0])}]\n{r[1]}\n{'-'*40}")
conn.close()
