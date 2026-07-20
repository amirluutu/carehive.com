import sqlite3

# Connect to (or create) the database file
conn = sqlite3.connect('stationery.db')
c = conn.cursor()

# Create inventory table
c.execute('''
CREATE TABLE IF NOT EXISTS inventory (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL
)
''')

# Create sales table
c.execute('''
CREATE TABLE IF NOT EXISTS sales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
''')

# Clear old inventory (optional, so you don’t duplicate items if you run again)
c.execute("DELETE FROM inventory")

# Insert starting inventory
c.execute("INSERT INTO inventory (item, quantity) VALUES ('pen', 100)")
c.execute("INSERT INTO inventory (item, quantity) VALUES ('notebook', 50)")
c.execute("INSERT INTO inventory (item, quantity) VALUES ('paper', 200)")
c.execute("INSERT INTO inventory (item, quantity) VALUES ('ruler', 30)")

# Save changes and close
conn.commit()
conn.close()

print("Database initialized with inventory and sales tables.")
