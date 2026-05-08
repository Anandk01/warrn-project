from app import app, db
import sqlite3
import os

def migrate_database():
    with app.app_context():
        db_path = os.path.join(app.instance_path, 'reports.db')
        
        # Connect directly to SQLite to add column
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        try:
            # Add accident_severity column to report table
            cursor.execute("ALTER TABLE report ADD COLUMN reporter_email VARCHAR(120)")
            print("Added reporter_email column to report table")
        except sqlite3.OperationalError as e:
            if "duplicate column name" in str(e):
                print("reporter_email column already exists")
            else:
                print(f"Error adding reporter_email column: {e}")
        
        conn.commit()
        conn.close()
        
        # Create NGO table if it doesn't exist
        db.create_all()
        print("Database migration completed!")

if __name__ == '__main__':
    migrate_database()