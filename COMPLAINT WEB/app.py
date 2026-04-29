from flask import Flask, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
import sqlite3
import database
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'super_secret_hackathon_key'
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # 16 MB max

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize Database
with app.app_context():
    database.init_db()

@app.before_request
def load_user():
    g.user = None
    if 'user_id' in session:
        conn = database.get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE user_id = ?', (session['user_id'],)).fetchone()
        conn.close()
        
        if user and user['is_active'] == 0:
            session.pop('user_id', None)
            g.user = None
            flash('Your account has been terminated by the administrator.', 'danger')
        else:
            g.user = user

@app.route('/')
def index():
    if g.user:
        if g.user['role'] == 'admin':
            return redirect(url_for('admin_dashboard'))
        elif g.user['role'] == 'department':
            return redirect(url_for('dept_dashboard'))
        else:
            return redirect(url_for('user_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=('GET', 'POST'))
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        
        conn = database.get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE email = ?', (email,)).fetchone()
        conn.close()
        
        if user and check_password_hash(user['password'], password):
            if user['is_active'] == 0:
                flash('Your account has been terminated. Please contact the administrator.', 'danger')
            else:
                session['user_id'] = user['user_id']
                return redirect(url_for('index'))
        else:
            flash('Invalid email or password', 'danger')
            
    return render_template('login.html')

@app.route('/register', methods=('GET', 'POST'))
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form.get('role', 'student') # Default to student
        dept_id = request.form.get('dept_id') if role == 'department' else None
        
        # Security check: don't allow open registration for admin
        if role not in ['student', 'department']:
            role = 'student'
            
        hashed_password = generate_password_hash(password)
        
        conn = database.get_db_connection()
        try:
            conn.execute('INSERT INTO users (name, email, password, role, dept_id) VALUES (?, ?, ?, ?, ?)',
                         (name, email, hashed_password, role, dept_id))
            conn.commit()
            flash('Registration successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Email already registered.', 'danger')
        finally:
            conn.close()
            
    conn = database.get_db_connection()
    departments = conn.execute('SELECT * FROM departments').fetchall()
    conn.close()
    return render_template('register.html', departments=departments)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/dashboard')
def user_dashboard():
    if not g.user or g.user['role'] != 'student':
        return redirect(url_for('login'))
        
    conn = database.get_db_connection()
    complaints = conn.execute('''
        SELECT c.*, d.dept_name, a.remarks 
        FROM complaints c
        LEFT JOIN complaint_assignments a ON c.complaint_id = a.complaint_id
        LEFT JOIN departments d ON a.dept_id = d.dept_id
        WHERE c.user_id = ?
        ORDER BY c.date DESC
    ''', (g.user['user_id'],)).fetchall()
    conn.close()
    
    return render_template('user_dashboard.html', complaints=complaints)

@app.route('/submit_complaint', methods=('GET', 'POST'))
def submit_complaint():
    if not g.user or g.user['role'] != 'student':
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        category = request.form['category']
        priority = request.form['priority']
        
        file = request.files.get('proof')
        filename = None
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            
        conn = database.get_db_connection()
        conn.execute('''
            INSERT INTO complaints (user_id, title, description, category, priority, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (g.user['user_id'], title, description, category, priority, filename))
        conn.commit()
        conn.close()
        
        flash('Complaint submitted successfully.', 'success')
        return redirect(url_for('user_dashboard'))
        
    return render_template('submit_complaint.html')

@app.route('/update_profile', methods=['POST'])
def update_profile():
    if not g.user:
        return redirect(url_for('login'))
        
    designation = request.form.get('designation')
    age = request.form.get('age')
    phone = request.form.get('phone')
    
    photo_file = request.files.get('photo')
    photo_name = g.user['photo'] # Keep existing if no new one
    
    if photo_file and photo_file.filename != '':
        filename = secure_filename(photo_file.filename)
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        photo_name = f"profile_{timestamp}_{filename}"
        photo_file.save(os.path.join(app.config['UPLOAD_FOLDER'], photo_name))
        
    conn = database.get_db_connection()
    try:
        conn.execute('''
            UPDATE users 
            SET designation = ?, age = ?, phone = ?, photo = ?
            WHERE user_id = ?
        ''', (designation, age, phone, photo_name, g.user['user_id']))
        conn.commit()
        flash('Profile updated successfully!', 'success')
    except Exception as e:
        flash('Error updating profile.', 'danger')
    finally:
        conn.close()
        
    if g.user['role'] == 'admin':
        return redirect(url_for('admin_dashboard'))
    elif g.user['role'] == 'department':
        return redirect(url_for('dept_dashboard'))
    else:
        return redirect(url_for('user_dashboard'))

@app.route('/admin')
def admin_dashboard():
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('login'))
        
    status_filter = request.args.get('status', 'All')
    
    conn = database.get_db_connection()
    
    # Get stats for graphs
    stats_status = conn.execute('SELECT status, COUNT(*) as count FROM complaints GROUP BY status').fetchall()
    stats_category = conn.execute('SELECT category, COUNT(*) as count FROM complaints GROUP BY category').fetchall()
    
    # Format data for Chart.js
    chart_status = {'labels': [row['status'] for row in stats_status], 'data': [row['count'] for row in stats_status]}
    chart_category = {'labels': [row['category'] for row in stats_category], 'data': [row['count'] for row in stats_category]}
    
    query = '''
        SELECT c.*, u.name as user_name, d.dept_name, a.remarks
        FROM complaints c
        JOIN users u ON c.user_id = u.user_id
        LEFT JOIN complaint_assignments a ON c.complaint_id = a.complaint_id
        LEFT JOIN departments d ON a.dept_id = d.dept_id
    '''
    params = []
    
    if status_filter != 'All':
        query += ' WHERE c.status = ?'
        params.append(status_filter)
        
    query += ' ORDER BY c.date DESC'
    
    complaints = conn.execute(query, params).fetchall()
    departments = conn.execute('SELECT * FROM departments').fetchall()
    users = conn.execute('SELECT u.*, d.dept_name FROM users u LEFT JOIN departments d ON u.dept_id = d.dept_id WHERE u.role != "admin" ORDER BY u.role, u.name').fetchall()
    conn.close()
    
    return render_template('admin_dashboard.html', complaints=complaints, departments=departments, status_filter=status_filter, chart_status=chart_status, chart_category=chart_category, users=users)

@app.route('/assign_complaint', methods=['POST'])
def assign_complaint():
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('login'))
        
    complaint_id = request.form.get('complaint_id')
    dept_id = request.form.get('dept_id')
    
    if not dept_id:
        flash('Please select a department before assigning.', 'danger')
        return redirect(url_for('admin_dashboard'))
    
    conn = database.get_db_connection()
    # Check if assignment already exists
    existing = conn.execute('SELECT * FROM complaint_assignments WHERE complaint_id = ?', (complaint_id,)).fetchone()
    
    if existing:
        conn.execute('UPDATE complaint_assignments SET dept_id = ? WHERE complaint_id = ?', (dept_id, complaint_id))
    else:
        conn.execute('INSERT INTO complaint_assignments (complaint_id, dept_id) VALUES (?, ?)', (complaint_id, dept_id))
        
    # Update status to In Progress
    conn.execute('UPDATE complaints SET status = ? WHERE complaint_id = ?', ('In Progress', complaint_id))
    
    conn.commit()
    conn.close()
    
    flash('Complaint assigned successfully.', 'success')
    return redirect(url_for('admin_dashboard'))

@app.route('/toggle_user_status/<int:user_id>', methods=['POST'])
def toggle_user_status(user_id):
    if not g.user or g.user['role'] != 'admin':
        return redirect(url_for('login'))
        
    conn = database.get_db_connection()
    try:
        user = conn.execute('SELECT is_active, name FROM users WHERE user_id = ?', (user_id,)).fetchone()
        if user:
            new_status = 0 if user['is_active'] == 1 else 1
            conn.execute('UPDATE users SET is_active = ? WHERE user_id = ?', (new_status, user_id))
            conn.commit()
            if new_status == 0:
                flash(f"User {user['name']} has been terminated.", 'warning')
            else:
                flash(f"User {user['name']} has been restored.", 'success')
    except Exception as e:
        flash('Error updating user status.', 'danger')
    finally:
        conn.close()
        
    return redirect(url_for('admin_dashboard'))

@app.route('/department')
def dept_dashboard():
    if not g.user or g.user['role'] != 'department':
        return redirect(url_for('login'))
        
    conn = database.get_db_connection()
    user_dept_id = g.user['dept_id']
    
    if not user_dept_id:
        flash('Your account is not linked to any specific department.', 'warning')
        complaints = []
    else:
        complaints = conn.execute('''
            SELECT c.*, u.name as user_name, d.dept_name, a.remarks
            FROM complaints c
            JOIN users u ON c.user_id = u.user_id
            JOIN complaint_assignments a ON c.complaint_id = a.complaint_id
            JOIN departments d ON a.dept_id = d.dept_id
            WHERE a.dept_id = ?
            ORDER BY c.priority = 'High' DESC, c.date ASC
        ''', (user_dept_id,)).fetchall()
        
    conn.close()
    
    return render_template('dept_dashboard.html', complaints=complaints)

@app.route('/update_status', methods=['POST'])
def update_status():
    if not g.user or g.user['role'] not in ['admin', 'department']:
        return redirect(url_for('login'))
        
    complaint_id = request.form['complaint_id']
    status = request.form['status']
    remarks = request.form.get('remarks', '')
    
    conn = database.get_db_connection()
    conn.execute('UPDATE complaints SET status = ? WHERE complaint_id = ?', (status, complaint_id))
    if remarks:
        conn.execute('UPDATE complaint_assignments SET remarks = ? WHERE complaint_id = ?', (remarks, complaint_id))
    conn.commit()
    conn.close()
    
    flash('Complaint status updated.', 'success')
    return redirect(url_for('dept_dashboard') if g.user['role'] == 'department' else url_for('admin_dashboard'))

from flask import send_from_directory
@app.route('/uploads/<name>')
def download_file(name):
    return send_from_directory(app.config["UPLOAD_FOLDER"], name)

if __name__ == '__main__':
    app.run(debug=True)
