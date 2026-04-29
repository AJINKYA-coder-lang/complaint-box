import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'complaints.db')

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    # Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'admin', 'department')),
            dept_id INTEGER,
            is_active INTEGER DEFAULT 1,
            designation TEXT,
            age INTEGER,
            phone TEXT,
            photo TEXT,
            FOREIGN KEY (dept_id) REFERENCES departments (dept_id)
        )
    ''')

    # Departments Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS departments (
            dept_id INTEGER PRIMARY KEY AUTOINCREMENT,
            dept_name TEXT NOT NULL
        )
    ''')

    # Complaints Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaints (
            complaint_id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Pending' CHECK(status IN ('Pending', 'In Progress', 'Resolved', 'Rejected')),
            priority TEXT NOT NULL DEFAULT 'Low' CHECK(priority IN ('High', 'Medium', 'Low')),
            file_path TEXT,
            date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    # Complaint_Assignment Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS complaint_assignments (
            assignment_id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER UNIQUE,
            dept_id INTEGER,
            remarks TEXT,
            FOREIGN KEY (complaint_id) REFERENCES complaints (complaint_id),
            FOREIGN KEY (dept_id) REFERENCES departments (dept_id)
        )
    ''')

    # Seed Admin User if not exists
    cursor.execute("SELECT * FROM users WHERE email = 'admin@college.edu'")
    if not cursor.fetchone():
        from werkzeug.security import generate_password_hash
        cursor.execute("INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
                       ('Admin', 'admin@college.edu', generate_password_hash('admin123'), 'admin'))

    # Seed Departments if empty
    cursor.execute("SELECT * FROM departments")
    if not cursor.fetchone():
        departments = [('IT Support',), ('Hostel Management',), ('Library',), ('Finance',), ('Academics',)]
        cursor.executemany("INSERT INTO departments (dept_name) VALUES (?)", departments)
        
    conn.commit()
    conn.close()

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
