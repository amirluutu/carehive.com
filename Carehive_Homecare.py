import sqlite3
import hashlib
import json
import os
from flask import Flask, render_template_string, request, redirect, url_for, session
from datetime import datetime, timezone

app = Flask(__name__)
app.secret_key = 'super-secret-carehive-key'
DB_NAME = 'carehive.db'

# --- SECURITY HELPER ---
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    cursor.execute('SELECT * FROM users WHERE email = ?', ('admin@carehive.com',))
    if not cursor.fetchone():
        master_pass = hash_password('admin123')
        cursor.execute(
            'INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)',
            ('admin@carehive.com', 'System Administrator', 'admin', master_pass)
        )
    
    conn.commit()
    conn.close()

init_db()

USER_STATUS = {}

def log_activity(email, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    cursor.execute('INSERT INTO logs (email, action, timestamp) VALUES (?, ?, ?)', (email, action, now))
    conn.commit()
    conn.close()

def get_user_activity_info(email):
    if email not in USER_STATUS or USER_STATUS[email]['status'] == 'Logged Out':
        return {'status': 'Logged Out', 'duration': '0m', 'last_active': 'N/A'}
    
    info = USER_STATUS[email]
    now = datetime.now(timezone.utc)
    duration_secs = int((now - info['login_time']).total_seconds())
    mins, secs = divmod(duration_secs, 60)
    hours, mins = divmod(mins, 60)
    duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m {secs}s"
    
    idle_secs = (now - info['last_active']).total_seconds()
    current_status = 'Paused / Idle' if idle_secs > 300 else 'Active Online'
    
    return {
        'status': current_status,
        'duration': duration_str,
        'last_active': info['last_active'].strftime("%H:%M:%S UTC")
    }

# --- COMMON STYLES ---
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited</title>
    <style>
        :root {
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --primary-light: #eff6ff;
            --secondary: #0f172a;
            --bg: #f8fafc;
            --surface: #ffffff;
            --text: #1e293b;
            --text-muted: #64748b;
            --border: #e2e8f0;
            --purple: #7c3aed;
            --accent-green: #10b981;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, -apple-system, sans-serif; }
        body { background-color: var(--bg); color: var(--text); line-height: 1.6; }

        .navbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.2rem 2.5rem; display: flex; justify-content: space-between; align-items: center; position: sticky; top: 0; z-index: 1000; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }
        .logo { font-size: 1.5rem; font-weight: 800; color: var(--primary); text-decoration: none; }
        .nav-links { display: flex; gap: 1rem; align-items: center; }

        .btn { background: var(--primary); color: white; border: none; padding: 0.75rem 1.4rem; border-radius: 10px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; transition: all 0.2s ease; }
        .btn:hover { background: var(--primary-hover); transform: translateY(-1px); box-shadow: 0 4px 12px rgba(37,99,235,0.25); }
        .btn-outline { background: transparent; border: 1.5px solid var(--border); color: var(--text); }
        .btn-outline:hover { background: var(--bg); border-color: #cbd5e1; }
        .btn-purple { background: var(--purple); }

        .hero { background: linear-gradient(135deg, #eff6ff 0%, #ffffff 50%, #f0fdf4 100%); padding: 5rem 1.5rem 4rem; text-align: center; border-bottom: 1px solid var(--border); }
        .hero-badge { display: inline-flex; align-items: center; gap: 6px; background: #dbeafe; color: #1e40af; font-size: 0.85rem; font-weight: 700; padding: 0.4rem 1rem; border-radius: 9999px; margin-bottom: 1.5rem; }
        .hero h1 { font-size: 3.2rem; font-weight: 800; color: var(--secondary); letter-spacing: -0.02em; line-height: 1.2; margin-bottom: 1.2rem; }
        .hero h1 span { color: var(--primary); }
        .hero p { color: var(--text-muted); font-size: 1.25rem; max-width: 650px; margin: 0 auto 2.5rem; }

        .container { max-width: 1140px; margin: 0 auto; padding: 0 1.5rem; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1.8rem; }

        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03); transition: transform 0.2s, box-shadow 0.2s; }
        .card-hover:hover { transform: translateY(-4px); box-shadow: 0 12px 24px -8px rgba(0,0,0,0.08); }
        .card-highlight { border: 2px solid var(--primary); position: relative; }
        .popular-badge { position: absolute; top: -12px; right: 20px; background: var(--primary); color: white; font-size: 0.75rem; font-weight: 700; padding: 0.2rem 0.8rem; border-radius: 9999px; }

        .icon-box { width: 48px; height: 48px; background: var(--primary-light); color: var(--primary); border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; margin-bottom: 1.2rem; }

        .stats-bar { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1.5rem; background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; margin: -2.5rem auto 4rem; position: relative; z-index: 10; box-shadow: 0 10px 25px -5px rgba(0,0,0,0.05); text-align: center; }
        .stat-item h3 { font-size: 2rem; font-weight: 800; color: var(--primary); }
        .stat-item p { font-size: 0.9rem; color: var(--text-muted); font-weight: 500; }

        .pricing-price { font-size: 2.2rem; font-weight: 800; color: var(--secondary); margin: 0.8rem 0; }
        .pricing-price span { font-size: 0.9rem; color: var(--text-muted); font-weight: 400; }
        .feature-list { list-style: none; margin: 1.5rem 0; text-align: left; }
        .feature-list li { padding: 0.4rem 0; font-size: 0.95rem; color: var(--text); display: flex; align-items: center; gap: 8px; }

        .cta-banner { background: linear-gradient(135deg, var(--secondary) 0%, #1e293b 100%); color: white; border-radius: 20px; padding: 3rem 2rem; text-align: center; margin: 4rem 0; }
        .cta-banner h2 { font-size: 2rem; font-weight: 800; margin-bottom: 0.8rem; }
        .cta-banner p { color: #94a3b8; max-width: 600px; margin: 0 auto 1.8rem; }

        .footer { background: var(--surface); border-top: 1px solid var(--border); padding: 3rem 1.5rem 1.5rem; margin-top: 4rem; }
        .footer-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 2rem; margin-bottom: 2rem; }
        .footer-col h4 { font-size: 1rem; font-weight: 700; margin-bottom: 1rem; color: var(--secondary); }
        .footer-col ul { list-style: none; }
        .footer-col ul li { margin-bottom: 0.5rem; }
        .footer-col ul li a { color: var(--text-muted); text-decoration: none; font-size: 0.9rem; }
        .footer-col ul li a:hover { color: var(--primary); }
        .footer-bottom { text-align: center; border-top: 1px solid var(--border); padding-top: 1.5rem; color: var(--text-muted); font-size: 0.85rem; }

        .badge { padding: 0.3rem 0.8rem; border-radius: 9999px; font-size: 0.8rem; font-weight: 600; }
        .badge-active { background: #dcfce7; color: #166534; }
        .badge-paused { background: #fef3c7; color: #92400e; }
        .badge-admin { background: #f3e8ff; color: #6b21a8; }
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 0.3rem; font-weight: 500; font-size: 0.9rem; }
        .form-group input, .form-group select { width: 100%; padding: 0.75rem; border: 1px solid var(--border); border-radius: 8px; }
        .alert { background: #fee2e2; color: #991b1b; padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; }
        .status-box { background: #f1f5f9; padding: 1rem; border-radius: 12px; margin-bottom: 1.5rem; border-left: 4px solid var(--primary); }
    </style>
"""

# --- HOME PAGE TEMPLATE ---
HOME_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar">
        <a href="/" class="logo">🏥 Carehive</a>
        <div class="nav-links">
            {% if session.get('user') %}
                <a href="/dashboard" class="btn btn-outline">Dashboard</a>
                <a href="/logout" class="btn">Logout</a>
            {% else %}
                <a href="/login" class="btn btn-outline">Staff Login</a>
                <a href="/signup" class="btn">Client Sign Up</a>
            {% endif %}
        </div>
    </nav>

    <!-- HERO SECTION -->
    <section class="hero">
        <div class="hero-badge">✨ Professional In-Home Medical Care</div>
        <h1>Compassionate Care,<br><span>Right at Your Doorstep</span></h1>
        <p>Connecting patients with qualified medical professionals for personal home visits, ongoing nursing, and clinical monitoring.</p>
        <div>
            {% if session.get('user') %}
                <a href="/dashboard" class="btn" style="padding: 0.9rem 2.2rem; font-size: 1.05rem;">Go to Dashboard →</a>
            {% else %}
                <a href="/signup" class="btn" style="padding: 0.9rem 2.2rem; font-size: 1.05rem;">Get Started as Client</a>
                <a href="/login" class="btn btn-outline" style="padding: 0.9rem 2.2rem; font-size: 1.05rem;">Staff Access</a>
            {% endif %}
        </div>
    </section>

    <div class="container">
        <!-- STATS BAR -->
        <div class="stats-bar">
            <div class="stat-item"><h3>24 / 7</h3><p>Emergency Assistance</p></div>
            <div class="stat-item"><h3>100%</h3><p>Verified Medical Staff</p></div>
            <div class="stat-item"><h3>1,200+</h3><p>Patients Supported</p></div>
            <div class="stat-item"><h3>4.9 ★</h3><p>Client Satisfaction</p></div>
        </div>

        <!-- FEATURES SECTION -->
        <h2 style="text-align: center; font-size: 2rem; margin-bottom: 0.5rem; color: var(--secondary);">Why Choose Carehive?</h2>
        <p style="text-align: center; color: var(--text-muted); margin-bottom: 2.5rem;">Dedicated home healthcare solutions designed around your needs.</p>
        <div class="grid" style="margin-bottom: 4rem;">
            <div class="card card-hover">
                <div class="icon-box">🩺</div>
                <h3 style="margin-bottom: 0.5rem;">Doctor Home Visits</h3>
                <p style="color: var(--text-muted); font-size: 0.95rem;">Scheduled home visits from registered doctors for diagnoses, prescriptions, and health checks.</p>
            </div>
            <div class="card card-hover">
                <div class="icon-box">💉</div>
                <h3 style="margin-bottom: 0.5rem;">Dedicated Nursing</h3>
                <p style="color: var(--text-muted); font-size: 0.95rem;">Experienced nurses available for daily care, vitals tracking, post-surgery recovery, and medication management.</p>
            </div>
            <div class="card card-hover">
                <div class="icon-box">🔒</div>
                <h3 style="margin-bottom: 0.5rem;">Secure Medical Portal</h3>
                <p style="color: var(--text-muted); font-size: 0.95rem;">Role-based portal ensuring encrypted access for patients, doctors, nurses, and site administrators.</p>
            </div>
        </div>

        <!-- PRICING & PACKAGES -->
        <h2 style="text-align: center; font-size: 2rem; margin-bottom: 0.5rem; color: var(--secondary);">Care Packages</h2>
        <p style="text-align: center; color: var(--text-muted); margin-bottom: 2.5rem;">Transparent pricing for quality in-home medical services.</p>
        <div class="grid" style="margin-bottom: 4rem;">
            <div class="card card-hover" style="text-align: center;">
                <h3>Routine Nursing Visit</h3>
                <p style="color: var(--text-muted); font-size: 0.85rem;">Single visit for vitals & dressing</p>
                <div class="pricing-price">$45 <span>/ visit</span></div>
                <ul class="feature-list">
                    <li>✅ Blood Pressure & Vitals Check</li>
                    <li>✅ Wound Care & Dressings</li>
                    <li>✅ Medication Administration</li>
                    <li>✅ Visit Summary Report</li>
                </ul>
                <a href="/signup" class="btn btn-outline" style="width: 100%; justify-content: center;">Book Nurse Visit</a>
            </div>

            <div class="card card-hover card-highlight" style="text-align: center;">
                <div class="popular-badge">MOST POPULAR</div>
                <h3>Doctor Consultation</h3>
                <p style="color: var(--text-muted); font-size: 0.85rem;">Comprehensive in-home doctor checkup</p>
                <div class="pricing-price">$120 <span>/ consultation</span></div>
                <ul class="feature-list">
                    <li>✅ Full Physical Examination</li>
                    <li>✅ Prescription Issuance</li>
                    <li>✅ Lab Sample Collection Onsite</li>
                    <li>✅ Direct Follow-up Support</li>
                </ul>
                <a href="/signup" class="btn" style="width: 100%; justify-content: center;">Request Doctor Visit</a>
            </div>

            <div class="card card-hover" style="text-align: center;">
                <h3>Elderly Continuous Care</h3>
                <p style="color: var(--text-muted); font-size: 0.85rem;">Monthly dedicated nursing plan</p>
                <div class="pricing-price">$490 <span>/ month</span></div>
                <ul class="feature-list">
                    <li>✅ 3 Weekly Nurse Visits</li>
                    <li>✅ Monthly Doctor Assessment</li>
                    <li>✅ 24/7 On-call Nursing Hotline</li>
                    <li>✅ Dedicated Care Coordinator</li>
                </ul>
                <a href="/signup" class="btn btn-outline" style="width: 100%; justify-content: center;">Subscribe to Plan</a>
            </div>
        </div>

        <!-- TESTIMONIALS -->
        <h2 style="text-align: center; font-size: 2rem; margin-bottom: 0.5rem; color: var(--secondary);">What Families Say</h2>
        <p style="text-align: center; color: var(--text-muted); margin-bottom: 2.5rem;">Real experiences from patients and caregivers.</p>
        <div class="grid" style="margin-bottom: 4rem;">
            <div class="card">
                <p style="font-style: italic; color: var(--text-muted); margin-bottom: 1rem;">"Carehive brought peace of mind to our family. Nurse Mary provided gentle, reliable care for my mother after her surgery."</p>
                <strong>— Sarah M.</strong> <small style="color: var(--primary); display: block;">Family Caregiver</small>
            </div>
            <div class="card">
                <p style="font-style: italic; color: var(--text-muted); margin-bottom: 1rem;">"Having a doctor visit our father at home saved us so many stressful hospital trips. The medical portal is clear and easy to use."</p>
                <strong>— David K.</strong> <small style="color: var(--primary); display: block;">Patient Son</small>
            </div>
            <div class="card">
                <p style="font-style: italic; color: var(--text-muted); margin-bottom: 1rem;">"Top notch professional service! The nurse arrives promptly, tracks all vitals on the portal, and explains everything clearly."</p>
                <strong>— Linda T.</strong> <small style="color: var(--primary); display: block;">Client</small>
            </div>
        </div>

        <!-- CALL TO ACTION BANNER -->
        <div class="cta-banner">
            <h2>Ready for Quality In-Home Care?</h2>
            <p>Register a client account in under two minutes or contact our support team for urgent consultations.</p>
            <div style="display: flex; gap: 1rem; justify-content: center; flex-wrap: wrap;">
                <a href="/signup" class="btn" style="background: white; color: var(--secondary); font-weight: 700;">Sign Up as Client</a>
                <a href="tel:+18005550199" class="btn btn-outline" style="color: white; border-color: rgba(255,255,255,0.3);">📞 Call: +1 (800) 555-0199</a>
            </div>
        </div>
    </div>

    <!-- FOOTER -->
    <footer class="footer">
        <div class="container">
            <div class="footer-grid">
                <div class="footer-col">
                    <h4 style="color: var(--primary); font-size: 1.3rem;">🏥 Carehive</h4>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.5rem;">Providing safe, professional, and accessible home healthcare services.</p>
                </div>
                <div class="footer-col">
                    <h4>Services</h4>
                    <ul>
                        <li><a href="#">Doctor Home Visits</a></li>
                        <li><a href="#">Nurse Assist</a></li>
                        <li><a href="#">Elderly Care</a></li>
                        <li><a href="#">Post-Op Recovery</a></li>
                    </ul>
                </div>
                <div class="footer-col">
                    <h4>Portals</h4>
                    <ul>
                        <li><a href="/login">Staff Login</a></li>
                        <li><a href="/signup">Client Registration</a></li>
                        <li><a href="/dashboard">Dashboard</a></li>
                    </ul>
                </div>
                <div class="footer-col">
                    <h4>Contact</h4>
                    <p style="color: var(--text-muted); font-size: 0.85rem;">📍 100 Medical Plaza, Suite 400</p>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.3rem;">✉️ support@carehive.com</p>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-top: 0.3rem;">📞 +1 (800) 555-0199</p>
                </div>
            </div>
            <div class="footer-bottom">
                <p>&copy; 2026 Carehive Homecare Limited. All rights reserved.</p>
            </div>
        </div>
    </footer>
</body>
</html>
"""

SIGNUP_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar"><a href="/" class="logo">🏥 Carehive</a><div class="nav-links"><a href="/" class="btn btn-outline">← Back to Home</a></div></nav>
    <div class="container" style="max-width: 450px; margin-top: 3rem;">
        <div class="card">
            <h2 style="text-align: center; margin-bottom: 0.5rem;">Client Registration</h2>
            <p style="text-align: center; color: var(--text-muted); margin-bottom: 1.5rem;">Public signup for clients & patients</p>
            {% if error %} <div class="alert">{{ error }}</div> {% endif %}
            <form action="/signup" method="POST">
                <div class="form-group"><label>Full Name</label><input type="text" name="fullname" required></div>
                <div class="form-group"><label>Email Address</label><input type="email" name="email" required></div>
                <div class="form-group"><label>Password</label><input type="password" name="password" required></div>
                <button type="submit" class="btn" style="width: 100%; justify-content: center;">Create Client Account</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar"><a href="/" class="logo">🏥 Carehive</a><div class="nav-links"><a href="/" class="btn btn-outline">← Back to Home</a></div></nav>
    <div class="container" style="max-width: 400px; margin-top: 3rem;">
        <div class="card">
            <h2 style="text-align: center; margin-bottom: 0.5rem;">Account Login</h2>
            <p style="text-align: center; color: var(--text-muted); margin-bottom: 1.5rem;">Access Client & Staff Portals</p>
            {% if error %} <div class="alert">{{ error }}</div> {% endif %}
            <form action="/login" method="POST">
                <div class="form-group"><label>Email Address</label><input type="email" name="email" required></div>
                <div class="form-group"><label>Password</label><input type="password" name="password" required></div>
                <button type="submit" class="btn" style="width: 100%; justify-content: center;">Log In</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar">
        <a href="/" class="logo">🏥 Carehive</a>
        <div class="nav-links">
            <a href="/" class="btn btn-outline">← Back to Home</a>
            <span>Logged in as: <strong>{{ session['user']['fullname'] }}</strong></span>
            <a href="/logout" class="btn">Logout</a>
        </div>
    </nav>

    <div class="container" style="margin-top: 2rem;">
        <div class="status-box">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <strong>Session Tracker:</strong>
                    <span class="badge {% if activity['status'] == 'Active Online' %}badge-active{% else %}badge-paused{% endif %}">
                        {{ activity['status'] }}
                    </span>
                </div>
                <div>
                    <span>⏱ Online Duration: <strong>{{ activity['duration'] }}</strong></span> | 
                    <span>Last Active: <strong>{{ activity['last_active'] }}</strong></span>
                </div>
            </div>
        </div>

        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 2rem;">
            <div>
                <h1>Dashboard</h1>
                <p style="color: var(--text-muted);">Role Overview & Administration</p>
            </div>
            <span class="badge {% if session['user']['role'] == 'admin' %}badge-admin{% endif %}">
                Role: {{ session['user']['role'].upper() }}
            </span>
        </div>

        {% if session['user']['role'] == 'admin' %}
            <div class="grid">
                <div class="card">
                    <h3>➕ Admin: Onboard Staff</h3>
                    <p style="color: var(--text-muted); font-size: 0.85rem; margin-bottom: 1rem;">Only Administrators can create Doctor or Nurse roles.</p>
                    <form action="/admin/create-worker" method="POST">
                        <div class="form-group">
                            <label>Assigned Role</label>
                            <select name="role" required>
                                <option value="nurse">Registered Nurse</option>
                                <option value="doctor">Medical Doctor</option>
                            </select>
                        </div>
                        <div class="form-group"><label>Full Name</label><input type="text" name="fullname" placeholder="Dr. Sarah" required></div>
                        <div class="form-group"><label>Work Email</label><input type="email" name="email" placeholder="staff@carehive.com" required></div>
                        <div class="form-group"><label>Password</label><input type="password" name="password" required></div>
                        <button type="submit" class="btn btn-purple" style="width: 100%; justify-content: center;">Create Worker Account</button>
                    </form>
                </div>

                <div class="card">
                    <h3>📜 Activity & Session Logs</h3>
                    <div style="max-height: 320px; overflow-y: auto; margin-top: 1rem;">
                        <ul style="list-style: none;">
                            {% for log in logs|reverse %}
                                <li style="padding: 0.5rem 0; border-bottom: 1px solid var(--border); font-size: 0.85rem;">
                                    <strong>{{ log[0] }}</strong> — 
                                    <span style="color: var(--primary);">{{ log[1] }}</span><br>
                                    <small style="color: var(--text-muted);">{{ log[2] }}</small>
                                </li>
                            {% endfor %}
                        </ul>
                    </div>
                </div>
            </div>
        {% else %}
            <div class="card">
                <h3>👤 Client Workspace</h3>
                <p>Request home health visits, view assigned nurses, and check consultation logs.</p>
            </div>
        {% endif %}
    </div>
</body>
</html>
"""

# --- ROUTE HANDLERS ---
@app.before_request
def update_last_active():
    if 'user' in session:
        email = session['user']['email']
        if email in USER_STATUS:
            USER_STATUS[email]['last_active'] = datetime.now(timezone.utc)

@app.route('/')
def home():
    return render_template_string(HOME_HTML)

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        fullname = request.form.get('fullname')
        hashed_pw = hash_password(request.form.get('password'))

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)',
                           (email, fullname, 'client', hashed_pw))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template_string(SIGNUP_HTML, error="Account with this email already exists.")
        conn.close()

        now = datetime.now(timezone.utc)
        USER_STATUS[email] = {'login_time': now, 'last_active': now, 'status': 'Active Online'}
        log_activity(email, "Client Registered & Logged In")

        session['user'] = {'fullname': fullname, 'role': 'client', 'email': email}
        return redirect(url_for('dashboard'))
    return render_template_string(SIGNUP_HTML)

@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        email = request.form.get('email')
        hashed_pw = hash_password(request.form.get('password'))

        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute('SELECT name, role FROM users WHERE email = ? AND password = ?', (email, hashed_pw))
        user = cursor.fetchone()
        conn.close()

        if user:
            now = datetime.now(timezone.utc)
            USER_STATUS[email] = {'login_time': now, 'last_active': now, 'status': 'Active Online'}
            log_activity(email, "User Logged In")

            session['user'] = {'fullname': user[0], 'role': user[1], 'email': email}
            return redirect(url_for('dashboard'))
        
        error = "Invalid email address or password."
    return render_template_string(LOGIN_HTML, error=error)

@app.route('/admin/create-worker', methods=['POST'])
def create_worker():
    if session.get('user', {}).get('role') != 'admin':
        return "Unauthorized Access: Admin privileges required.", 403
    
    email = request.form.get('email')
    fullname = request.form.get('fullname')
    role = request.form.get('role')
    hashed_pw = hash_password(request.form.get('password'))

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute('INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)',
                       (email, fullname, role, hashed_pw))
        conn.commit()
    except sqlite3.IntegrityError:
        pass
    conn.close()

    log_activity(session['user']['email'], f"Created {role.capitalize()} account for {email}")
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    
    email = session['user']['email']
    activity_info = get_user_activity_info(email)

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('SELECT email, action, timestamp FROM logs ORDER BY id DESC LIMIT 50')
    logs = cursor.fetchall()
    conn.close()

    return render_template_string(
        DASHBOARD_HTML, 
        logs=logs, 
        activity=activity_info
    )

@app.route('/logout')
def logout():
    if 'user' in session:
        email = session['user']['email']
        log_activity(email, "User Logged Out")
        if email in USER_STATUS:
            USER_STATUS[email]['status'] = 'Logged Out'
        session.pop('user', None)
    return redirect(url_for('home'))

if __name__ == '__main__':
    app.run(debug=True)

    # Create appointments / client registration table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            location TEXT NOT NULL,
            service TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Create patient reviews table
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """
    )

    # Insert initial sample review if empty
    cursor.execute("SELECT COUNT(*) FROM reviews")
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            """
            INSERT INTO reviews (client_name, rating, comment) 
            VALUES ('Sarah K.', 5, 'Exceptional home care for my family in Kampala. The nurses are deeply compassionate and professional!')
        """
        )

    conn.commit()
    conn.close()


init_db()


def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


# ---------------------------------------------------------
# Web Page Layout & HTML Templates
# ---------------------------------------------------------
INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited | Localhost Web System</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-50 text-slate-800 font-sans">

    <!-- Top Contact Bar -->
    <div class="bg-blue-900 text-white text-sm py-2 px-6 flex justify-between items-center flex-wrap">
        <div class="flex items-center space-x-6">
            <span><i class="fa-solid fa-phone text-red-400 mr-2"></i>+256 753 976 912</span>
            <span><i class="fa-brands fa-whatsapp text-green-400 mr-2"></i>+256 708 083 118</span>
        </div>
        <div class="text-xs text-blue-200">Localhost Server Active | Uganda</div>
    </div>

    <!-- Navigation Header -->
    <header class="bg-white shadow-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 py-4 flex justify-between items-center">
            <div class="flex items-center space-x-3">
                <div class="w-12 h-12 rounded-full border-2 border-blue-700 flex items-center justify-center bg-blue-50 text-blue-800 font-bold text-xl">
                    <i class="fa-solid fa-user-nurse text-2xl text-blue-700"></i>
                </div>
                <div>
                    <h1 class="font-extrabold text-xl text-blue-900 tracking-tight">CAREHIVE HOMECARE LIMITED</h1>
                    <p class="text-xs text-red-600 font-semibold tracking-wide">PROFESSIONAL SAFE CARE & NURSING AT YOUR HOME</p>
                </div>
            </div>
            <nav class="hidden md:flex space-x-6 text-sm font-semibold">
                <a href="#about" class="hover:text-blue-700 transition">About Us</a>
                <a href="#services" class="hover:text-blue-700 transition">Services</a>
                <a href="#register" class="hover:text-blue-700 transition">Book Care</a>
                <a href="#reviews" class="hover:text-blue-700 transition">Reviews</a>
                <a href="/admin" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1.5 rounded-md border">Admin Dashboard</a>
            </nav>
        </div>
    </header>

    <!-- Hero Banner -->
    <section class="relative bg-gradient-to-r from-blue-900 to-indigo-800 text-white py-20 px-6">
        <div class="max-w-5xl mx-auto text-center">
            <span class="bg-red-600 text-white text-xs uppercase px-3 py-1 rounded-full font-bold tracking-wider">Clinical Excellence</span>
            <h2 class="text-4xl md:text-5xl font-black mt-4 mb-6 leading-tight">Unparalleled Standard of Healthcare at Your Home</h2>
            <p class="text-lg text-blue-100 max-w-2xl mx-auto mb-8">Extraordinary service born out of strong, true foundations and a genuine passion for caring of the highest quality.</p>
            <div class="flex justify-center gap-4 flex-wrap">
                <a href="#register" class="bg-red-600 hover:bg-red-700 text-white font-bold px-8 py-3 rounded-lg shadow-lg transition">Book Nurse / Appointment</a>
                <a href="https://wa.me/256708083118" target="_blank" class="bg-green-600 hover:bg-green-700 text-white font-bold px-6 py-3 rounded-lg shadow-lg flex items-center gap-2 transition">
                    <i class="fa-brands fa-whatsapp text-lg"></i> Chat on WhatsApp
                </a>
            </div>
        </div>
    </section>

    <!-- Vision & Mission -->
    <section id="about" class="py-16 px-6 max-w-7xl mx-auto grid md:grid-cols-2 gap-8">
        <div class="bg-white p-8 rounded-2xl border border-blue-100 shadow-sm border-l-4 border-l-blue-700">
            <h3 class="text-2xl font-bold text-blue-900 mb-3 flex items-center gap-2">
                <i class="fa-solid fa-eye text-blue-700"></i> Our Vision
            </h3>
            <p class="text-slate-600 leading-relaxed">
                To become the elite home nursing provider of choice in Uganda achieving clinical excellence and delivering an unparalleled standard of healthcare at home.
            </p>
        </div>
        <div class="bg-white p-8 rounded-2xl border border-blue-100 shadow-sm border-l-4 border-l-red-600">
            <h3 class="text-2xl font-bold text-blue-900 mb-3 flex items-center gap-2">
                <i class="fa-solid fa-bullseye text-red-600"></i> Our Mission
            </h3>
            <p class="text-slate-600 leading-relaxed">
                Extraordinary service is born out of strong and true foundations. It is this genuine passion for caring of the highest quality that drives consistent excellence and unwavering confidence in what we do. This begins with constant education and support for every Carehive Homecare Limited employee that enables the enrichment of lives throughout communities. It is this invaluable effect that creates recognition of Carehive Homecare Limited as a leader in home health care services.
            </p>
        </div>
    </section>

    <!-- Services Grid -->
    <section id="services" class="py-16 bg-slate-100 px-6">
        <div class="max-w-7xl mx-auto">
            <div class="text-center mb-12">
                <h2 class="text-3xl font-bold text-blue-900">Our Professional Services</h2>
                <p class="text-slate-600 mt-2">Comprehensive nursing and home care tailored to your family's needs</p>
            </div>
            <div class="grid md:grid-cols-3 gap-6">
                {% set services = [
                    ("Blood Pressure Check", "fa-heart-pulse"),
                    ("Blood Sugar Check", "fa-droplet"),
                    ("Wound Dressing", "fa-bandage"),
                    ("Injection (Prescribed)", "fa-syringe"),
                    ("Catheter Care", "fa-user-nurse"),
                    ("Baby and Maternal Care", "fa-baby"),
                    ("Child Care", "fa-child-reaching"),
                    ("Elderly Care", "fa-wheelchair"),
                    ("Post Surgery Care", "fa-bed-pulse")
                ] %}
                {% for name, icon in services %}
                <div class="bg-white p-6 rounded-xl shadow-sm border hover:shadow-md transition">
                    <div class="w-12 h-12 bg-blue-100 text-blue-800 rounded-lg flex items-center justify-center mb-4 text-xl">
                        <i class="fa-solid {{ icon }}"></i>
                    </div>
                    <h4 class="font-bold text-lg text-slate-800 mb-2">{{ name }}</h4>
                    <p class="text-sm text-slate-500">Delivered by certified healthcare professionals directly at your residence.</p>
                </div>
                {% endfor %}
            </div>
        </div>
    </section>

    <!-- Client Registration / Appointment Form -->
    <section id="register" class="py-16 px-6 max-w-4xl mx-auto">
        <div class="bg-white p-8 md:p-12 rounded-2xl shadow-xl border border-blue-100">
            <h2 class="text-3xl font-bold text-blue-900 text-center mb-2">Book a Nurse / Service</h2>
            <p class="text-center text-slate-600 mb-8">Register your details below and our healthcare team will contact you immediately.</p>
            
            <form action="/register" method="POST" class="space-y-6">
                <div class="grid md:grid-cols-2 gap-6">
                    <div>
                        <label class="block text-sm font-semibold mb-2">Full Name</label>
                        <input type="text" name="full_name" required placeholder="e.g. John Doe" class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none">
                    </div>
                    <div>
                        <label class="block text-sm font-semibold mb-2">Phone Number</label>
                        <input type="tel" name="phone" required placeholder="e.g. +256 700 000 000" class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none">
                    </div>
                </div>

                <div class="grid md:grid-cols-2 gap-6">
                    <div>
                        <label class="block text-sm font-semibold mb-2">Service Required</label>
                        <select name="service" required class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none">
                            <option value="Blood Pressure Check">Blood Pressure Check</option>
                            <option value="Blood Sugar Check">Blood Sugar Check</option>
                            <option value="Wound Dressing">Wound Dressing</option>
                            <option value="Injection (Prescribed)">Injection (Prescribed)</option>
                            <option value="Catheter Care">Catheter Care</option>
                            <option value="Baby and Maternal Care">Baby and Maternal Care</option>
                            <option value="Child Care">Child Care</option>
                            <option value="Elderly Care">Elderly Care</option>
                            <option value="Post Surgery Care">Post Surgery Care</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-semibold mb-2">Location / Address in Uganda</label>
                        <input type="text" name="location" required placeholder="e.g. Kampala / Entebbe / Wakiso" class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none">
                    </div>
                </div>

                <div>
                    <label class="block text-sm font-semibold mb-2">Preferred Appointment Date</label>
                    <input type="date" name="preferred_date" required class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none">
                </div>

                <div>
                    <label class="block text-sm font-semibold mb-2">Additional Medical Information / Notes</label>
                    <textarea name="notes" rows="3" placeholder="Briefly describe patient condition or specific request..." class="w-full px-4 py-3 rounded-lg border focus:ring-2 focus:ring-blue-600 outline-none"></textarea>
                </div>

                <button type="submit" class="w-full bg-blue-800 hover:bg-blue-900 text-white font-bold py-4 rounded-lg shadow-lg transition">Submit Registration Request</button>
            </form>
        </div>
    </section>

    <!-- Client Reviews Section -->
    <section id="reviews" class="py-16 bg-slate-100 px-6">
        <div class="max-w-6xl mx-auto">
            <h2 class="text-3xl font-bold text-blue-900 text-center mb-8">Client Testimonials & Reviews</h2>
            
            <div class="grid md:grid-cols-2 gap-6 mb-12">
                {% for r in reviews %}
                <div class="bg-white p-6 rounded-xl shadow-sm border">
                    <div class="flex justify-between items-center mb-3">
                        <span class="font-bold text-slate-800">{{ r['client_name'] }}</span>
                        <div class="text-amber-400">
                            {% for i in range(r['rating']) %}<i class="fa-solid fa-star"></i>{% endfor %}
                        </div>
                    </div>
                    <p class="text-slate-600 italic">"{{ r['comment'] }}"</p>
                    <span class="text-xs text-slate-400 mt-3 block">{{ r['created_at'] }}</span>
                </div>
                {% endfor %}
            </div>

            <!-- Submit Review Form -->
            <div class="bg-white p-8 rounded-2xl border max-w-2xl mx-auto shadow-sm">
                <h3 class="text-xl font-bold text-slate-800 mb-4">Leave a Review</h3>
                <form action="/review" method="POST" class="space-y-4">
                    <input type="text" name="client_name" required placeholder="Your Name" class="w-full px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-600">
                    <select name="rating" class="w-full px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-600">
                        <option value="5">5 Stars - Outstanding</option>
                        <option value="4">4 Stars - Very Good</option>
                        <option value="3">3 Stars - Good</option>
                    </select>
                    <textarea name="comment" required placeholder="Share your experience with Carehive..." class="w-full px-4 py-2 border rounded-lg outline-none focus:ring-2 focus:ring-blue-600" rows="3"></textarea>
                    <button type="submit" class="bg-red-600 hover:bg-red-700 text-white font-bold px-6 py-2 rounded-lg transition">Post Review</button>
                </form>
            </div>
        </div>
    </section>

    <!-- Footer -->
    <footer class="bg-slate-900 text-slate-400 py-10 px-6">
        <div class="max-w-7xl mx-auto text-center space-y-4">
            <h3 class="text-white font-bold text-lg">CAREHIVE HOMECARE LIMITED</h3>
            <p class="text-sm">Contact Appointments: +256 753 976 912 | WhatsApp: +256 708 083 118</p>
            <p class="text-xs text-slate-500">&copy; 2026 Carehive Homecare Limited. All rights reserved.</p>
        </div>
    </footer>
</body>
</html>
"""

ADMIN_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Admin Dashboard</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-100 p-8">
    <div class="max-w-6xl mx-auto">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-3xl font-bold text-blue-900">Carehive Admin Dashboard</h1>
                <p class="text-slate-600 text-sm">Manage client appointment registrations and records</p>
            </div>
            <a href="/" class="text-sm bg-blue-700 hover:bg-blue-800 text-white px-4 py-2 rounded-lg font-bold shadow transition">
                <i class="fa-solid fa-globe mr-1"></i> Back to Website
            </a>
        </div>

        <div class="bg-white rounded-xl shadow-md overflow-hidden mb-12 border">
            <div class="p-6 bg-slate-800 text-white flex justify-between items-center">
                <h2 class="text-xl font-bold"><i class="fa-solid fa-users text-blue-400 mr-2"></i> Registered Client Requests</h2>
                <span class="text-xs bg-blue-600 text-white px-3 py-1 rounded-full font-semibold">{{ appointments|length }} Total</span>
            </div>
            <div class="overflow-x-auto">
                <table class="w-full text-left border-collapse">
                    <thead class="bg-slate-100 text-slate-700 text-xs uppercase font-bold border-b">
                        <tr>
                            <th class="p-4">ID</th>
                            <th class="p-4">Name</th>
                            <th class="p-4">Phone</th>
                            <th class="p-4">Service Required</th>
                            <th class="p-4">Location</th>
                            <th class="p-4">Preferred Date</th>
                            <th class="p-4">Notes</th>
                        </tr>
                    </thead>
                    <tbody class="text-sm divide-y">
                        {% for a in appointments %}
                        <tr class="hover:bg-slate-50 transition">
                            <td class="p-4 font-mono text-slate-400">#{{ a['id'] }}</td>
                            <td class="p-4 font-bold text-slate-800">{{ a['full_name'] }}</td>
                            <td class="p-4 text-blue-700 font-semibold">{{ a['phone'] }}</td>
                            <td class="p-4">
                                <span class="bg-blue-100 text-blue-800 px-2 py-1 rounded text-xs font-semibold">
                                    {{ a['service'] }}
                                </span>
                            </td>
                            <td class="p-4">{{ a['location'] }}</td>
                            <td class="p-4 text-slate-600">{{ a['preferred_date'] }}</td>
                            <td class="p-4 text-xs text-slate-500 max-w-xs">{{ a['notes'] or 'N/A' }}</td>
                        </tr>
                        {% else %}
                        <tr>
                            <td colspan="7" class="p-8 text-center text-slate-400">No client registration requests submitted yet.</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
    </div>
</body>
</html>
"""


# ---------------------------------------------------------
# Web Server Routes
# ---------------------------------------------------------
@app.route("/")
def home():
    conn = get_db_connection()
    reviews = conn.execute(
        "SELECT * FROM reviews ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template_string(INDEX_HTML, reviews=reviews)


@app.route("/register", methods=["POST"])
def register():
    full_name = request.form["full_name"]
    phone = request.form["phone"]
    service = request.form["service"]
    location = request.form["location"]
    preferred_date = request.form["preferred_date"]
    notes = request.form.get("notes", "")

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO appointments (full_name, phone, service, location, preferred_date, notes)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
        (full_name, phone, service, location, preferred_date, notes),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("home") + "#register")


@app.route("/review", methods=["POST"])
def add_review():
    client_name = request.form["client_name"]
    rating = int(request.form["rating"])
    comment = request.form["comment"]

    conn = get_db_connection()
    conn.execute(
        """
        INSERT INTO reviews (client_name, rating, comment)
        VALUES (?, ?, ?)
        """,
        (client_name, rating, comment),
    )
    conn.commit()
    conn.close()

    return redirect(url_for("home") + "#reviews")


@app.route("/admin")
def admin():
    conn = get_db_connection()
    appointments = conn.execute(
        "SELECT * FROM appointments ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template_string(ADMIN_HTML, appointments=appointments)


@app.route("/dashboard")
def dashboard():
    return "<h1>Welcome to the Admin Dashboard</h1>"

@app.route("/user_dashboard")
def user_dashboard():
    user = {"name": "Musa"}
    next_appointment = {"date": "July 25", "time": "10:00 AM"}
    stats = {"total": 5, "completed": 3, "pending": 2}
    notifications = [
        "Your appointment was confirmed.",
        "New service available."
    ]
    return render_template(
        "user_dashboard.html",
        user=user,
        next_appointment=next_appointment,
        stats=stats,
        notifications=notifications
    )

if __name__ == "__main__":
    print("\n===============================================")
    print(" CAREHIVE HOMECARE LIMITED WEBSITE IS RUNNING ON LOCALHOST!")
    print(" Open your web browser and navigate to:")
    print(" --> http://localhost:5000 OR http://127.0.0.1:5000")
    print("===============================================\n")

    app.run(host="127.0.0.1", port=5000, debug=True)

