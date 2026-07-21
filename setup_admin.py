import sqlite3
import hashlib
import getpass

# 1. Database filename for master credentials
MASTER_DB_NAME = "master_credentials.db"

# 2. Setup the database table
def setup_master_db():
    try:
        conn = sqlite3.connect(MASTER_DB_NAME)
        cursor = conn.cursor()
        
        # Create a table to store the master admin
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS master_admin (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL
            )
        """)
        conn.commit()
        print(f"✅ Master database '{MASTER_DB_NAME}' and table created successfully.")
        conn.close()
    except sqlite3.Error as e:
        print(f"❌ Error setting up master database: {e}")

# 3. Securely create the master admin account
def create_master_admin():
    print("\n--- Create Master Admin Account ---")
    
    # Prompt for a username
    username = input("Enter master username: ")
    
    # Securely prompt for a password (will not echo as you type)
    password = getpass.getpass("Enter master password: ")
    confirm_password = getpass.getpass("Confirm master password: ")
    
    if password != confirm_password:
        print("❌ Passwords do not match. Please try again.")
        return

    # Generate a secure SHA-256 hash of the password
    password_hash = hashlib.sha256(password.encode()).hexdigest()
    
    try:
        conn = sqlite3.connect(MASTER_DB_NAME)
        cursor = conn.cursor()
        
        # Insert the master admin credentials
        cursor.execute("""
            INSERT INTO master_admin (username, password_hash)
            VALUES (?, ?)
        """, (username, password_hash))
        
        conn.commit()
        print(f"✅ Master admin account '{username}' created successfully.")
        conn.close()
    except sqlite3.IntegrityError:
        print(f"❌ Master admin username '{username}' already exists.")
    except sqlite3.Error as e:
        print(f"❌ Error creating master admin account: {e}")

# 4. Main execution block
if __name__ == "__main__":
    setup_master_db()
    create_master_admin()