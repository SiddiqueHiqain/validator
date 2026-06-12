import sqlite3

DB_PATH = "nanpa.db"

try:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    print("📋 Tables:", tables)

    for table in tables:
        cursor.execute(f"SELECT COUNT(*) FROM {table[0]}")
        count = cursor.fetchone()[0]
        print(f"📊 Rows in {table[0]}:", count)

    conn.close()
except Exception as e:
    print("❌ Error checking DB:", e)
