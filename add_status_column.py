import sqlite3

conn = sqlite3.connect('customers.db')
c = conn.cursor()

# Check if 'status' column exists
c.execute("PRAGMA table_info(customers)")
columns = [col[1] for col in c.fetchall()]
if 'status' not in columns:
    c.execute("ALTER TABLE customers ADD COLUMN status TEXT DEFAULT 'Pending'")
    print("✅ 'status' column added to 'customers' table.")
else:
    print("⚠️ 'status' column already exists.")

conn.commit()
conn.close()
