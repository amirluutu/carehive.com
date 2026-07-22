"""
Carehive Homecare Limited — Complete Flask Application

Features:
  - Public marketing site with Care UK-inspired Hero Care Finder & Trust Bar
  - Integrated Uganda Geographical Taxonomy Registry with API & Cascading Dropdowns
  - Live GPS Location capture (with dropdown override) and Google Maps sharing
  - Enlarged logo & centered branding
  - Disappearing Dashboard Callout Banner prompting user Login/Signup
  - Appointment registration with valid contact verification (`/register`)
  - Client review submission (`/review`)
  - User authentication & portal (`/signup`, `/login`, `/logout`)
  - User Account Settings (`/settings`)
  - User activity log tracking & status monitoring
  - Enhanced User & Admin Dashboards (`/dashboard`)
  - Admin worker creation (`/admin/create-worker`) & appointments manager (`/admin`)
"""

import sqlite3
from datetime import datetime, timezone
from urllib.parse import quote
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super-secret-carehive-key'
DB_NAME = 'carehive.db'


# ==========================================
# UGANDA GEOGRAPHY TAXONOMY REGISTRY
# ==========================================

class Village:
    """Represents the lowest administrative unit (Level 5) in Uganda."""
    def __init__(self, name: str):
        self.name = name

    def __repr__(self):
        return f"Village({self.name})"


class SubCounty:
    """Represents a Sub-county, Town Council, or Division (Level 4)."""
    def __init__(self, name: str):
        self.name = name
        self.villages = {}

    def add_village(self, village_name: str) -> Village:
        if village_name not in self.villages:
            self.villages[village_name] = Village(village_name)
        return self.villages[village_name]

    def __repr__(self):
        return f"SubCounty({self.name}, Villages: {list(self.villages.keys())})"


class County:
    """Represents a County, Constituency, or Municipality (Level 3)."""
    def __init__(self, name: str):
        self.name = name
        self.sub_counties = {}

    def add_sub_county(self, sub_county_name: str) -> SubCounty:
        if sub_county_name not in self.sub_counties:
            self.sub_counties[sub_county_name] = SubCounty(sub_county_name)
        return self.sub_counties[sub_county_name]

    def __repr__(self):
        return f"County({self.name})"


class District:
    """Represents a District or City (Level 2)."""
    def __init__(self, name: str, region: str):
        self.name = name
        self.region = region  # Central, Western, Eastern, or Northern
        self.counties = {}

    def add_county(self, county_name: str) -> County:
        if county_name not in self.counties:
            self.counties[county_name] = County(county_name)
        return self.counties[county_name]

    def __repr__(self):
        return f"District({self.name}, Region: {self.region})"


class UgandaGeographyRegistry:
    """Main registry to manage the entire geographical structure of Uganda."""
    def __init__(self):
        self.districts = {}

    def add_location(self, region: str, district_name: str, county_name: str, sub_county_name: str, village_name: str):
        """Helper to quickly inject a full localized chain."""
        if district_name not in self.districts:
            self.districts[district_name] = District(district_name, region)
        
        district = self.districts[district_name]
        county = district.add_county(county_name)
        sub_county = county.add_sub_county(sub_county_name)
        sub_county.add_village(village_name)

    def get_district_details(self, district_name: str):
        """Fetches all nested information for a specific district."""
        district = self.districts.get(district_name)
        if not district:
            return f"District '{district_name}' not found."
        
        data = {
            "District": district.name,
            "Region": district.region,
            "Counties/Divisions": {}
        }
        for c_name, county in district.counties.items():
            data["Counties/Divisions"][c_name] = {}
            for s_name, sub_county in county.sub_counties.items():
                data["Counties/Divisions"][c_name][s_name] = list(sub_county.villages.keys())
        return data

    def to_dict(self):
        """Exports taxonomy data as a dict for frontend API consumption."""
        result = {}
        for d_name, district in self.districts.items():
            locations = []
            for c_name, county in district.counties.items():
                for s_name in county.sub_counties.keys():
                    locations.append(f"{s_name} ({c_name})")
            result[d_name] = {
                "region": district.region,
                "locations": sorted(list(set(locations)))
            }
        return result


# Instantiate global registry and add core administrative data
uganda_geo = UgandaGeographyRegistry()
uganda_geo.add_location("Central", "Kampala", "Makindye Division", "Ssabagabo", "Kanyanya")
uganda_geo.add_location("Central", "Kampala", "Central Division", "Nakasero", "Nakasero I")
uganda_geo.add_location("Western", "Mbarara", "Kashari County", "Bubaare", "Kashaka")


# ---------------------------------------------------------
# Custom Jinja Filter for Safe Image URLs with Spaces
# ---------------------------------------------------------
@app.template_filter('url_encode_path')
def url_encode_path(s):
    return quote(s)


# ---------------------------------------------------------
# Database Helpers & Initialization
# ---------------------------------------------------------
def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
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

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            service TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            client_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Migration check: Ensure latitude/longitude columns exist in existing DB
    cursor.execute("PRAGMA table_info(appointments)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'latitude' not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN latitude REAL")
    if 'longitude' not in columns:
        cursor.execute("ALTER TABLE appointments ADD COLUMN longitude REAL")

    # Seed default admin account
    cursor.execute('SELECT password FROM users WHERE email = ?', ('admin@carehive.com',))
    admin = cursor.fetchone()
    if not admin:
        cursor.execute(
            'INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)',
            ('admin@carehive.com', 'System Administrator', 'admin', generate_password_hash('admin123'))
        )

    # Seed default initial reviews if empty
    cursor.execute('SELECT COUNT(*) FROM reviews')
    if cursor.fetchone()[0] == 0:
        cursor.execute(
            'INSERT INTO reviews (client_name, rating, comment) VALUES (?, ?, ?)',
            ('Sarah K.', 5, 'Exceptional home care for my family in Kampala. Deeply compassionate nurses!')
        )
        cursor.execute(
            'INSERT INTO reviews (client_name, rating, comment) VALUES (?, ?, ?)',
            ('David M.', 5, 'Professional and prompt service. Highly recommend Carehive for elderly care.')
        )

    conn.commit()
    conn.close()


# ---------------------------------------------------------
# User Activity Log Tracking
# ---------------------------------------------------------
USER_STATUS = {}


def log_activity(email, action):
    conn = get_db_connection()
    cursor = conn.cursor()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute('INSERT INTO logs (email, action, timestamp) VALUES (?, ?, ?)', (email, action, now))
    conn.commit()
    conn.close()


def get_user_activity_info(email):
    if email not in USER_STATUS or USER_STATUS[email].get('status') == 'Logged Out':
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


# ---------------------------------------------------------
# HTML Templates
# ---------------------------------------------------------
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root { --primary: #2563eb; --primary-hover: #1d4ed8; --bg: #f8fafc; --surface: #ffffff; --text: #1e293b; --text-muted: #64748b; --border: #e2e8f0; }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Segoe UI', system-ui, sans-serif; }
        body { background-color: var(--bg); color: var(--text); line-height: 1.6; }
        .navbar { background: var(--surface); border-bottom: 1px solid var(--border); padding: 1.2rem 2rem; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; gap: 10px; }
        .logo-img { height: 110px; width: auto; object-fit: contain; }
        .btn { background: var(--primary); color: white; border: none; padding: 0.75rem 1.4rem; border-radius: 10px; font-weight: 600; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; }
        .btn:hover { background: var(--primary-hover); }
        .btn-outline { background: transparent; border: 1.5px solid var(--border); color: var(--text); }
        .container { max-width: 1140px; margin: 0 auto; padding: 0 1.5rem; }
        .card { background: var(--surface); border: 1px solid var(--border); border-radius: 16px; padding: 2rem; box-shadow: 0 4px 6px -1px rgba(0,0,0,0.03); }
        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; margin-bottom: 0.3rem; font-weight: 500; font-size: 0.9rem; }
        .form-group input, .form-group select, .form-group textarea { width: 100%; padding: 0.75rem; border: 1px solid var(--border); border-radius: 8px; }
        .alert { background: #fee2e2; color: #991b1b; padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; }
        .success-alert { background: #dcfce7; color: #166534; padding: 0.75rem; border-radius: 8px; margin-bottom: 1rem; }
    </style>
"""

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited</title>
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
        <div class="text-xs text-blue-200">Kampala, Uganda</div>
    </div>

    <!-- DISAPPEARING DASHBOARD LOGIN/SIGNUP PROMPT BANNER -->
    {% if not session.get('user') %}
    <div id="disappearing-dashboard-banner" class="bg-gradient-to-r from-blue-700 via-indigo-700 to-blue-900 text-white border-b border-indigo-500 shadow-md transition-all duration-500 overflow-hidden">
        <div class="max-w-7xl mx-auto px-6 py-3 flex flex-wrap items-center justify-between gap-4">
            <div class="flex items-center space-x-3">
                <span class="bg-amber-400 text-blue-950 p-2 rounded-lg font-bold text-xs shadow-sm flex items-center gap-1">
                    <i class="fa-solid fa-gauge-high"></i> DASHBOARD
                </span>
                <p class="text-xs md:text-sm font-medium">
                    Access your personalized Carehive Portal to track healthcare appointments and manage details!
                </p>
            </div>
            <div class="flex items-center space-x-3">
                <a href="/login" class="bg-white text-blue-900 hover:bg-slate-100 font-bold px-4 py-1.5 rounded-lg text-xs transition shadow-sm">
                    <i class="fa-solid fa-right-to-bracket mr-1"></i> Log In
                </a>
                <a href="/signup" class="bg-amber-400 hover:bg-amber-300 text-slate-900 font-bold px-4 py-1.5 rounded-lg text-xs transition shadow-sm">
                    <i class="fa-solid fa-user-plus mr-1"></i> Sign Up
                </a>
                <button onclick="dismissDashboardBanner()" class="text-blue-200 hover:text-white p-1 ml-2 transition focus:outline-none" title="Dismiss dashboard banner">
                    <i class="fa-solid fa-xmark text-lg"></i>
                </button>
            </div>
        </div>
    </div>
    <script>
        if (localStorage.getItem('hideDashboardBanner') === 'true') {
            const banner = document.getElementById('disappearing-dashboard-banner');
            if (banner) banner.style.display = 'none';
        }

        function dismissDashboardBanner() {
            const banner = document.getElementById('disappearing-dashboard-banner');
            if (banner) {
                banner.style.opacity = '0';
                banner.style.maxHeight = '0px';
                setTimeout(() => banner.style.display = 'none', 300);
            }
            localStorage.setItem('hideDashboardBanner', 'true');
        }
    </script>
    {% endif %}

    <!-- Header / Nav with Centered & Enlarged Logo -->
    <header class="bg-white shadow-md sticky top-0 z-50">
        <div class="max-w-7xl mx-auto px-6 py-4 flex flex-col items-center justify-center space-y-3">
            <div class="flex flex-col items-center text-center">
                <img src="/static/images/{{ 'company logo.jpeg'|url_encode_path }}" alt="Carehive Logo" class="h-28 w-auto rounded-2xl object-contain border border-slate-100 shadow-md mb-2" onerror="this.onerror=null; this.src='https://placehold.co/240x240?text=Carehive';">
                <h1 class="font-black text-2xl md:text-3xl text-blue-900 leading-tight tracking-tight">CAREHIVE HOMECARE LIMITED</h1>
                <p class="text-xs md:text-sm text-red-600 font-extrabold tracking-widest uppercase mt-0.5">SAFE NURSING & CARE AT YOUR HOME</p>
            </div>
            <nav class="flex items-center space-x-6 text-sm font-semibold pt-2 border-t border-slate-100 w-full justify-center">
                <a href="#services" class="hover:text-blue-700 transition">Services</a>
                <button onclick="openBookingForm()" class="hover:text-blue-700 transition font-semibold">Book Care</button>
                <a href="#reviews" class="hover:text-blue-700 transition">Reviews</a>
                {% if session.get('user') %}
                    <a href="/dashboard" class="bg-blue-600 text-white px-5 py-2 rounded-xl hover:bg-blue-700 transition">Dashboard</a>
                {% else %}
                    <a href="/login" class="bg-slate-100 text-slate-700 px-5 py-2 rounded-xl border hover:bg-slate-200 transition">Portal Login</a>
                {% endif %}
            </nav>
        </div>
    </header>

    <!-- Care UK-Inspired Hero Section with Interactive Care Finder -->
    <section class="relative bg-gradient-to-r from-blue-950 via-indigo-900 to-slate-900 text-white py-20 px-6 text-center">
        <div class="max-w-5xl mx-auto">
            <span class="bg-blue-800/80 text-blue-200 text-xs font-bold uppercase tracking-widest px-4 py-1.5 rounded-full border border-blue-700/50 inline-block mb-4">
                Uganda's Premier Home Nursing Service
            </span>
            <h2 class="text-4xl md:text-5xl font-black mb-4 leading-tight">Quality Home Care Services</h2>
            <p class="text-blue-100 max-w-2xl mx-auto mb-8 text-lg">Professional, compassionate healthcare and home nursing delivered directly to your doorstep in Uganda.</p>

            <!-- Inline Care Finder Bar with District Dropdown -->
            <div class="bg-white p-4 rounded-2xl shadow-2xl max-w-3xl mx-auto text-slate-800 flex flex-col md:flex-row gap-3">
                <div class="flex-1 text-left px-2">
                    <label class="block text-xs font-bold text-slate-400 uppercase">Care Needed</label>
                    <select id="hero-service-select" class="w-full text-sm font-semibold bg-transparent py-2 border-b border-slate-200 focus:outline-none">
                        <option value="Professional Nursing Care">Professional Nursing Care</option>
                        <option value="Elderly Care">Elderly & Respiratory Care</option>
                        <option value="Baby Care">Pediatric & Baby Care</option>
                        <option value="Post Surgery Care">Post-Surgery Support</option>
                    </select>
                </div>
                <div class="flex-1 text-left px-2">
                    <label class="block text-xs font-bold text-slate-400 uppercase">Select District</label>
                    <select id="hero-district-select" class="w-full text-sm font-semibold bg-transparent py-2 border-b border-slate-200 focus:outline-none">
                        <option value="">-- All Districts --</option>
                    </select>
                </div>
                <button onclick="handleHeroBooking()" class="bg-red-600 hover:bg-red-700 text-white font-bold px-8 py-3.5 rounded-xl shadow-lg transition flex items-center justify-center gap-2">
                    <i class="fa-solid fa-magnifying-glass"></i> Book Care
                </button>
            </div>
        </div>
    </section>

    <!-- Trust & Quality Indicators Bar -->
    <div class="bg-white border-b border-slate-200 py-6 px-6">
        <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
            <div>
                <div class="text-2xl font-black text-blue-900">4.9 / 5.0</div>
                <div class="text-xs text-slate-500 font-medium">Client Rating</div>
            </div>
            <div>
                <div class="text-2xl font-black text-blue-900">100%</div>
                <div class="text-xs text-slate-500 font-medium">Vetted Medical Staff</div>
            </div>
            <div>
                <div class="text-2xl font-black text-blue-900">24/7</div>
                <div class="text-xs text-slate-500 font-medium">On-Call Support</div>
            </div>
            <div>
                <div class="text-2xl font-black text-blue-900">Kampala & Beyond</div>
                <div class="text-xs text-slate-500 font-medium">Service Coverage</div>
            </div>
        </div>
    </div>

    <!-- Registration Prompt Notice -->
    <div class="max-w-7xl mx-auto mt-8 px-6">
        <div class="bg-amber-50 border-l-4 border-amber-500 p-4 rounded-r-xl shadow-sm flex items-start gap-3">
            <i class="fa-solid fa-circle-info text-amber-600 text-xl mt-0.5"></i>
            <div>
                <h4 class="font-bold text-amber-900 text-sm">Please Register with Valid Contact Details</h4>
                <p class="text-xs text-amber-800 mt-0.5">Explore all our available services and clinical details below. To schedule visits or request care, please register using your <strong>valid email address</strong> and <strong>phone number</strong> so our medical staff can reach you.</p>
            </div>
        </div>
    </div>

    <!-- Services Grid with Images -->
    <section id="services" class="py-12 px-6 max-w-7xl mx-auto">
        <h2 class="text-3xl font-bold text-center text-blue-900 mb-10">Our Nursing & Care Services</h2>
        <div class="grid md:grid-cols-3 gap-8">
            <!-- Service 1: Nursing Care -->
            <div class="bg-white rounded-2xl shadow-md border border-slate-200 overflow-hidden hover:shadow-lg transition">
                <img src="/static/images/{{ 'nursing care.jpeg'|url_encode_path }}" alt="Nursing Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=600&q=80';">
                <div class="p-6">
                    <h3 class="font-bold text-xl text-blue-900 mb-2">Professional Nursing Care</h3>
                    <p class="text-slate-600 text-sm mb-4">Post-operative support, wound dressing, vital signs monitoring, and medication management at home.</p>
                    <button onclick="openBookingForm('Wound Dressing')" class="text-xs font-bold text-blue-600 hover:underline inline-flex items-center gap-1">Register to Book <i class="fa-solid fa-arrow-right"></i></button>
                </div>
            </div>
            <!-- Service 2: Broncure Care -->
            <div class="bg-white rounded-2xl shadow-md border border-slate-200 overflow-hidden hover:shadow-lg transition">
                <img src="/static/images/{{ 'broncure.jpeg'|url_encode_path }}" alt="Respiratory & Elderly Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?auto=format&fit=crop&w=600&q=80';">
                <div class="p-6">
                    <h3 class="font-bold text-xl text-blue-900 mb-2">Respiratory & Elderly Care</h3>
                    <p class="text-slate-600 text-sm mb-4">Dedicated eldercare, respiratory support, and continuous health assessments for elderly family members.</p>
                    <button onclick="openBookingForm('Elderly Care')" class="text-xs font-bold text-blue-600 hover:underline inline-flex items-center gap-1">Register to Book <i class="fa-solid fa-arrow-right"></i></button>
                </div>
            </div>
            <!-- Service 3: Baby Care -->
            <div class="bg-white rounded-2xl shadow-md border border-slate-200 overflow-hidden hover:shadow-lg transition">
                <img src="/static/images/{{ 'baby care.jpeg'|url_encode_path }}" alt="Pediatric & Baby Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1555252333-9f8e92e65df9?auto=format&fit=crop&w=600&q=80';">
                <div class="p-6">
                    <h3 class="font-bold text-xl text-blue-900 mb-2">Pediatric & Baby Care</h3>
                    <p class="text-slate-600 text-sm mb-4">Expert infant care, postnatal mother support, and specialized pediatric nursing care at home.</p>
                    <button onclick="openBookingForm('Baby Care')" class="text-xs font-bold text-blue-600 hover:underline inline-flex items-center gap-1">Register to Book <i class="fa-solid fa-arrow-right"></i></button>
                </div>
            </div>
        </div>
    </section>

    <!-- Appointment Booking Modal/Form Container (Removed direct display from standard homepage flow) -->
    <section id="register-container" class="hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm overflow-y-auto p-4 md:p-6 flex items-center justify-center">
        <div class="max-w-3xl w-full bg-white p-8 rounded-2xl shadow-2xl border border-slate-200 relative my-8">
            <button onclick="closeBookingForm()" class="absolute top-4 right-4 text-slate-400 hover:text-slate-700 text-xl p-2"><i class="fa-solid fa-xmark"></i></button>
            <h2 class="text-2xl font-bold text-blue-900 mb-2 text-center">Book a Home Care Appointment</h2>
            <p class="text-center text-slate-500 text-sm mb-6">Enter your valid contact details and choose your location in Uganda.</p>
            <form action="/register" method="POST" class="space-y-4" onsubmit="return validateForm()">
                <input type="hidden" id="latitude" name="latitude">
                <input type="hidden" id="longitude" name="longitude">
                <input type="hidden" id="location" name="location">

                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Full Name</label>
                    <input type="text" name="full_name" required placeholder="John Doe" class="w-full p-3 border rounded-xl">
                </div>
                <div class="grid md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Valid Phone Number</label>
                        <input type="tel" name="phone" required placeholder="+256 700 000 000" class="w-full p-3 border rounded-xl">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Service Required</label>
                        <select id="form-service-select" name="service" required class="w-full p-3 border rounded-xl">
                            <option value="Blood Pressure Check">Blood Pressure Check</option>
                            <option value="Wound Dressing">Wound Dressing</option>
                            <option value="Elderly Care">Elderly Care</option>
                            <option value="Post Surgery Care">Post Surgery Care</option>
                            <option value="Baby Care">Baby & Infant Care</option>
                        </select>
                    </div>
                </div>

                <!-- CASCADING GEOGRAPHY DROPDOWNS & GPS OVERRIDE -->
                <div class="p-4 bg-slate-50 border rounded-xl space-y-3">
                    <div class="flex justify-between items-center">
                        <label class="block text-xs font-semibold text-slate-700 uppercase">
                            <i class="fa-solid fa-map-location-dot text-blue-600 mr-1"></i> Geographical Location
                        </label>
                        <button type="button" onclick="getLocation()" class="text-xs text-blue-600 hover:text-blue-800 font-bold flex items-center gap-1 bg-blue-50 px-2.5 py-1 rounded-lg border border-blue-200">
                            <i class="fa-solid fa-location-crosshairs"></i> Use Live GPS
                        </button>
                    </div>

                    <div id="district-selection-group" class="grid md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-500 mb-1">District / City</label>
                            <select id="district-select" class="w-full p-3 border rounded-xl bg-white" onchange="onDistrictChange()">
                                <option value="">-- Choose District --</option>
                            </select>
                        </div>
                        <div>
                            <label class="block text-xs font-medium text-slate-500 mb-1">Sub-County / Division</label>
                            <select id="location-select" class="w-full p-3 border rounded-xl bg-white" disabled>
                                <option value="">-- Select District First --</option>
                            </select>
                        </div>
                    </div>

                    <!-- Live GPS Auto-fill / Override Input View -->
                    <div id="gps-container" class="hidden">
                        <label class="block text-xs font-medium text-emerald-700 mb-1">Live Location Detected (Auto-Filled)</label>
                        <input type="text" id="gps-display" readonly class="w-full p-3 border border-emerald-300 bg-emerald-50 text-emerald-900 rounded-xl font-mono text-xs font-bold">
                        <button type="button" onclick="clearGPS()" class="text-xs text-slate-500 underline mt-1 block">Clear Live Location and select manually</button>
                    </div>

                    <span id="gps-status" class="text-xs text-emerald-600 block font-semibold hidden"></span>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Preferred Date</label>
                    <input type="date" name="preferred_date" required class="w-full p-3 border rounded-xl">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Additional Notes</label>
                    <textarea name="notes" placeholder="Specify any health details or directions..." class="w-full p-3 border rounded-xl h-24"></textarea>
                </div>
                <div class="flex gap-3">
                    <button type="button" onclick="closeBookingForm()" class="w-1/3 bg-slate-200 text-slate-700 font-bold py-3.5 rounded-xl transition">Cancel</button>
                    <button type="submit" class="w-2/3 bg-blue-800 hover:bg-blue-900 text-white font-bold py-3.5 rounded-xl shadow transition">Submit Care Request</button>
                </div>
            </form>
        </div>
    </section>

    <!-- Script for Geography API Integration, District Pre-filtering & Live GPS Auto-fill -->
    <script>
        let ugandaGeoData = {};
        let isGpsActive = false;

        // Fetch Uganda Taxonomy Registry on Page Load
        fetch('/api/uganda-geo')
            .then(res => res.json())
            .then(data => {
                ugandaGeoData = data;
                populateDistricts();
            });

        function populateDistricts() {
            const districtSelect = document.getElementById('district-select');
            const heroDistrictSelect = document.getElementById('hero-district-select');
            
            districtSelect.innerHTML = '<option value="">-- Choose District --</option>';
            if (heroDistrictSelect) heroDistrictSelect.innerHTML = '<option value="">-- All Districts --</option>';

            for (const district in ugandaGeoData) {
                const opt = document.createElement('option');
                opt.value = district;
                opt.textContent = `${district} (${ugandaGeoData[district].region} Region)`;
                districtSelect.appendChild(opt);

                if (heroDistrictSelect) {
                    const heroOpt = document.createElement('option');
                    heroOpt.value = district;
                    heroOpt.textContent = district;
                    heroDistrictSelect.appendChild(heroOpt);
                }
            }
        }

        function onDistrictChange() {
            const districtSelect = document.getElementById('district-select');
            const locSelect = document.getElementById('location-select');
            const selectedDistrict = districtSelect.value;

            locSelect.innerHTML = '';

            if (selectedDistrict && ugandaGeoData[selectedDistrict]) {
                locSelect.disabled = false;
                locSelect.innerHTML = '<option value="">-- Select Division/Sub-County --</option>';
                ugandaGeoData[selectedDistrict].locations.forEach(loc => {
                    const opt = document.createElement('option');
                    opt.value = loc;
                    opt.textContent = loc;
                    locSelect.appendChild(opt);
                });
            } else {
                locSelect.disabled = true;
                locSelect.innerHTML = '<option value="">-- Select District First --</option>';
            }
        }

        function openBookingForm(service = null, district = null) {
            const container = document.getElementById('register-container');
            container.classList.remove('hidden');

            if (service) {
                const serviceSelect = document.getElementById('form-service-select');
                if (serviceSelect) serviceSelect.value = service;
            }

            if (district) {
                const districtSelect = document.getElementById('district-select');
                districtSelect.value = district;
                onDistrictChange();
            }
        }

        function closeBookingForm() {
            document.getElementById('register-container').classList.add('hidden');
        }

        function handleHeroBooking() {
            const selectedDistrict = document.getElementById('hero-district-select').value;
            const selectedService = document.getElementById('hero-service-select').value;
            openBookingForm(selectedService, selectedDistrict);
        }

        function getLocation() {
            const statusText = document.getElementById('gps-status');
            statusText.classList.remove('hidden');
            statusText.innerText = "Detecting live location...";

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    (position) => {
                        const lat = position.coords.latitude;
                        const lng = position.coords.longitude;
                        
                        document.getElementById('latitude').value = lat;
                        document.getElementById('longitude').value = lng;
                        
                        const gpsString = `Live GPS Location (${lat.toFixed(5)}, ${lng.toFixed(5)})`;
                        document.getElementById('gps-display').value = gpsString;
                        
                        // Auto-fill and bypass manual district/location dropdown selection
                        isGpsActive = true;
                        document.getElementById('district-selection-group').classList.add('hidden');
                        document.getElementById('gps-container').classList.remove('hidden');

                        statusText.innerText = "✓ Live location detected! District selection bypassed.";
                    },
                    (error) => {
                        statusText.innerText = "Unable to retrieve live location. Please select district manually.";
                        statusText.classList.replace('text-emerald-600', 'text-red-500');
                    },
                    { enableHighAccuracy: true, timeout: 10000 }
                );
            } else {
                alert("Geolocation is not supported by your browser.");
            }
        }

        function clearGPS() {
            isGpsActive = false;
            document.getElementById('latitude').value = '';
            document.getElementById('longitude').value = '';
            document.getElementById('district-selection-group').classList.remove('hidden');
            document.getElementById('gps-container').classList.add('hidden');
            document.getElementById('gps-status').classList.add('hidden');
        }

        function validateForm() {
            const locInput = document.getElementById('location');
            if (isGpsActive) {
                locInput.value = document.getElementById('gps-display').value;
            } else {
                const dist = document.getElementById('district-select').value;
                const loc = document.getElementById('location-select').value;
                if (!dist || !loc) {
                    alert("Please select both a District and Location or detect Live Location.");
                    return false;
                }
                locInput.value = `${loc}, ${dist}`;
            }
            return true;
        }
    </script>

    <!-- Reviews Section -->
    <section id="reviews" class="py-16 px-6 max-w-5xl mx-auto">
        <h2 class="text-3xl font-bold text-center text-blue-900 mb-8">Client Testimonials</h2>
        
        <div class="grid md:grid-cols-2 gap-6 mb-12">
            {% for review in reviews %}
            <div class="bg-white p-6 rounded-2xl shadow border border-slate-200">
                <div class="flex justify-between items-center mb-3">
                    <h4 class="font-bold text-slate-900">{{ review['client_name'] }}</h4>
                    <div class="text-amber-400 text-sm">
                        {% for i in range(review['rating']) %}<i class="fa-solid fa-star"></i>{% endfor %}
                    </div>
                </div>
                <p class="text-slate-600 text-sm italic">"{{ review['comment'] }}"</p>
                <span class="text-xs text-slate-400 mt-3 block">{{ review['created_at'] }}</span>
            </div>
            {% endfor %}
        </div>

        <!-- Add Review Form -->
        <div class="bg-slate-100 p-6 rounded-2xl border border-slate-200 max-w-xl mx-auto">
            <h3 class="font-bold text-lg text-slate-900 mb-4 text-center">Leave a Client Review</h3>
            <form action="/review" method="POST" class="space-y-3">
                <input type="text" name="client_name" required placeholder="Your Name" class="w-full p-3 border rounded-lg">
                <select name="rating" class="w-full p-3 border rounded-lg">
                    <option value="5">5 Stars - Excellent</option>
                    <option value="4">4 Stars - Very Good</option>
                    <option value="3">3 Stars - Good</option>
                    <option value="2">2 Stars - Fair</option>
                    <option value="1">1 Star - Poor</option>
                </select>
                <textarea name="comment" required placeholder="Your experience with our care team..." class="w-full p-3 border rounded-lg h-20"></textarea>
                <button type="submit" class="w-full bg-slate-800 text-white font-bold py-2.5 rounded-lg hover:bg-slate-900 transition">Submit Review</button>
            </form>
        </div>
    </section>

    <footer class="bg-slate-900 text-slate-400 text-center py-8 border-t border-slate-800 text-sm">
        <p>© 2026 Carehive Homecare Limited. All rights reserved.</p>
    </footer>
</body>
</html>
"""

SIGNUP_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar">
        <a href="/" style="text-decoration:none; display:flex; flex-direction:column; align-items:center; gap:8px;">
            <img src="/static/images/{{ 'company logo.jpeg'|url_encode_path }}" class="logo-img" onerror="this.onerror=null; this.src='https://placehold.co/240x240?text=Carehive';">
            <span style="font-weight:800; font-size:1.4rem; color:var(--primary);">Carehive Portal</span>
        </a>
        <a href="/" class="btn btn-outline">← Home</a>
    </nav>
    <div class="container" style="max-width: 450px; margin-top: 2rem; margin-bottom: 3rem;">
        <div class="card">
            <h2 style="text-align: center; margin-bottom: 0.5rem;">Client Registration</h2>
            <p style="text-align: center; color: var(--text-muted); margin-bottom: 1.5rem;">Create your Carehive patient account with a valid email</p>
            {% if error %} <div class="alert">{{ error }}</div> {% endif %}
            <form action="/signup" method="POST">
                <div class="form-group"><label>Full Name</label><input type="text" name="fullname" required placeholder="John Doe"></div>
                <div class="form-group"><label>Valid Email Address</label><input type="email" name="email" required placeholder="name@domain.com"></div>
                <div class="form-group"><label>Password</label><input type="password" name="password" required></div>
                <button type="submit" class="btn" style="width: 100%; justify-content: center;">Register Account</button>
            </form>
            <p style="text-align:center; margin-top:1rem; font-size:0.85rem;">Already have an account? <a href="/login" style="color:var(--primary);">Login here</a></p>
        </div>
    </div>
</body>
</html>
"""

LOGIN_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar">
        <a href="/" style="text-decoration:none; display:flex; flex-direction:column; align-items:center; gap:8px;">
            <img src="/static/images/{{ 'company logo.jpeg'|url_encode_path }}" class="logo-img" onerror="this.onerror=null; this.src='https://placehold.co/240x240?text=Carehive';">
            <span style="font-weight:800; font-size:1.4rem; color:var(--primary);">Carehive Portal</span>
        </a>
        <a href="/" class="btn btn-outline">← Home</a>
    </nav>
    <div class="container" style="max-width: 400px; margin-top: 2rem; margin-bottom: 3rem;">
        <div class="card">
            <h2 style="text-align: center; margin-bottom: 0.5rem;">Portal Login</h2>
            <p style="text-align: center; color: var(--text-muted); margin-bottom: 1.5rem;">Sign in to Client & Staff Dashboard</p>
            {% if error %} <div class="alert">{{ error }}</div> {% endif %}
            <form action="/login" method="POST">
                <div class="form-group"><label>Email Address</label><input type="email" name="email" required></div>
                <div class="form-group"><label>Password</label><input type="password" name="password" required></div>
                <button type="submit" class="btn" style="width: 100%; justify-content: center;">Log In</button>
            </form>
            <p style="text-align:center; margin-top:1rem; font-size:0.85rem;">Need an account? <a href="/signup" style="color:var(--primary);">Sign up</a></p>
        </div>
    </div>
</body>
</html>
"""

SETTINGS_HTML = COMMON_HEAD + """
<body>
    <nav class="navbar">
        <a href="/" style="text-decoration:none; display:flex; flex-direction:column; align-items:center; gap:8px;">
            <img src="/static/images/{{ 'company logo.jpeg'|url_encode_path }}" class="logo-img" onerror="this.onerror=null; this.src='https://placehold.co/240x240?text=Carehive';">
            <span style="font-weight:800; font-size:1.4rem; color:var(--primary);">Carehive Portal</span>
        </a>
        <a href="/dashboard" class="btn btn-outline">← Dashboard</a>
    </nav>
    <div class="container" style="max-width: 500px; margin-top: 2rem; margin-bottom: 3rem;">
        <div class="card">
            <h2 style="text-align: center; margin-bottom: 0.5rem;"><i class="fa-solid fa-user-gear"></i> Account Settings</h2>
            <p style="text-align: center; color: var(--text-muted); margin-bottom: 1.5rem;">Update your profile details and password</p>
            {% if message %} <div class="success-alert">{{ message }}</div> {% endif %}
            <form action="/settings" method="POST">
                <div class="form-group">
                    <label>Email Address (Cannot be changed)</label>
                    <input type="email" value="{{ user['email'] }}" disabled style="background:#f1f5f9; cursor:not-allowed;">
                </div>
                <div class="form-group">
                    <label>Full Name</label>
                    <input type="text" name="fullname" value="{{ user['fullname'] }}" required>
                </div>
                <div class="form-group">
                    <label>New Password (Leave blank to keep current)</label>
                    <input type="password" name="password" placeholder="••••••••">
                </div>
                <button type="submit" class="btn" style="width: 100%; justify-content: center;">Save Changes</button>
            </form>
        </div>
    </div>
</body>
</html>
"""

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard | Carehive Homecare</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.3/chart.umd.min.js"></script>
</head>
<body class="bg-slate-100 text-slate-800">
    <div class="flex h-screen overflow-hidden">
        <!-- Sidebar Navigation -->
        <aside class="w-64 bg-slate-900 text-slate-300 flex flex-col justify-between hidden md:flex">
            <div>
                <div class="p-6 border-b border-slate-800 flex flex-col items-center text-center gap-3">
                    <img src="/static/images/{{ 'company logo.jpeg'|url_encode_path }}" class="w-20 h-20 rounded-xl object-contain bg-white p-1 border" onerror="this.src='https://placehold.co/100x100?text=CH';">
                    <div>
                        <h2 class="font-black text-white text-lg tracking-wide">CAREHIVE</h2>
                        <span class="text-xs text-blue-400 font-bold uppercase">Portal Dashboard</span>
                    </div>
                </div>
                <nav class="p-4 space-y-1">
                    <a href="/dashboard" class="flex items-center gap-3 px-4 py-3 bg-blue-600 text-white rounded-xl font-medium shadow">
                        <i class="fa-solid fa-chart-line w-5"></i> Overview
                    </a>
                    <a href="/settings" class="flex items-center gap-3 px-4 py-3 hover:bg-slate-800 hover:text-white rounded-xl font-medium transition">
                        <i class="fa-solid fa-gear w-5 text-amber-400"></i> Account Settings
                    </a>
                    {% if session['user']['role'] == 'admin' %}
                    <a href="/admin" class="flex items-center gap-3 px-4 py-3 hover:bg-slate-800 hover:text-white rounded-xl font-medium transition">
                        <i class="fa-solid fa-calendar-check w-5 text-blue-400"></i> Appointments Table
                    </a>
                    {% endif %}
                    <a href="/" class="flex items-center gap-3 px-4 py-3 hover:bg-slate-800 hover:text-white rounded-xl font-medium transition">
                        <i class="fa-solid fa-globe w-5 text-indigo-400"></i> Public Website
                    </a>
                </nav>
            </div>
            <div class="p-4 border-t border-slate-800 bg-slate-950/50">
                <div class="flex items-center gap-3 mb-3">
                    <div class="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center font-bold text-white uppercase text-sm">
                        {{ session['user']['fullname'][0] }}
                    </div>
                    <div class="overflow-hidden">
                        <p class="text-sm font-semibold text-white truncate">{{ session['user']['fullname'] }}</p>
                        <p class="text-xs text-slate-400 truncate">{{ session['user']['email'] }}</p>
                    </div>
                </div>
                <a href="/logout" class="w-full flex items-center justify-center gap-2 bg-slate-800 hover:bg-red-600 hover:text-white text-slate-300 py-2 rounded-lg text-xs font-bold transition">
                    <i class="fa-solid fa-right-from-bracket"></i> Sign Out
                </a>
            </div>
        </aside>

        <!-- Main Dashboard View -->
        <div class="flex-1 flex flex-col overflow-y-auto">
            <header class="bg-white border-b border-slate-200 px-8 py-4 flex justify-between items-center sticky top-0 z-10">
                <div>
                    <h1 class="text-2xl font-bold text-slate-900">Dashboard Overview</h1>
                    <p class="text-xs text-slate-500">Welcome back, {{ session['user']['fullname'] }}</p>
                </div>
                <div class="flex items-center gap-4">
                    <a href="/settings" class="text-xs font-semibold text-slate-600 hover:text-blue-600 flex items-center gap-1.5 bg-slate-100 px-3 py-1.5 rounded-lg border">
                        <i class="fa-solid fa-gear"></i> Settings
                    </a>
                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider
                        {% if session['user']['role'] == 'admin' %} bg-purple-100 text-purple-800 border border-purple-200 {% else %} bg-blue-100 text-blue-800 border border-blue-200 {% endif %}">
                        <i class="fa-solid {% if session['user']['role'] == 'admin' %}fa-shield-halved{% else %}fa-user{% endif %}"></i>
                        {{ session['user']['role'] }}
                    </span>
                </div>
            </header>

            <main class="p-8 space-y-8">
                <!-- Live Session Monitoring Banner -->
                <div class="bg-slate-900 text-white p-5 rounded-2xl shadow-lg border border-slate-800 flex flex-wrap justify-between items-center gap-4">
                    <div class="flex items-center gap-4">
                        <div class="w-12 h-12 bg-blue-600/20 text-blue-400 rounded-xl flex items-center justify-center text-xl border border-blue-500/30">
                            <i class="fa-solid fa-clock"></i>
                        </div>
                        <div>
                            <span class="text-xs uppercase font-bold tracking-wider text-slate-400 block">Session Status</span>
                            <span class="text-sm text-slate-200">
                                Status: <strong class="{% if activity['status'] == 'Active Online' %}text-emerald-400{% else %}text-amber-400{% endif %}">{{ activity['status'] }}</strong>
                            </span>
                        </div>
                    </div>
                    <div class="flex items-center gap-6 text-sm">
                        <div class="text-right">
                            <span class="text-xs text-slate-400 block">Session Duration</span>
                            <strong class="text-white text-base font-mono">{{ activity['duration'] }}</strong>
                        </div>
                        <div class="text-right border-l border-slate-800 pl-6">
                            <span class="text-xs text-slate-400 block">Last Active</span>
                            <strong class="text-white text-base font-mono">{{ activity['last_active'] }}</strong>
                        </div>
                    </div>
                </div>

                {% if session['user']['role'] == 'admin' %}
                <!-- Admin Key Metrics -->
                <div class="grid md:grid-cols-3 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                        <div>
                            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Appointments</p>
                            <h3 class="text-3xl font-black text-slate-900 mt-1">{{ stats['appointments'] }}</h3>
                        </div>
                        <div class="w-14 h-14 bg-blue-50 text-blue-600 rounded-2xl flex items-center justify-center text-2xl">
                            <i class="fa-solid fa-calendar-check"></i>
                        </div>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                        <div>
                            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Registered Users</p>
                            <h3 class="text-3xl font-black text-slate-900 mt-1">{{ stats['users'] }}</h3>
                        </div>
                        <div class="w-14 h-14 bg-indigo-50 text-indigo-600 rounded-2xl flex items-center justify-center text-2xl">
                            <i class="fa-solid fa-users"></i>
                        </div>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex items-center justify-between">
                        <div>
                            <p class="text-xs font-semibold uppercase tracking-wider text-slate-400">Total Reviews</p>
                            <h3 class="text-3xl font-black text-slate-900 mt-1">{{ stats['reviews'] }}</h3>
                        </div>
                        <div class="w-14 h-14 bg-amber-50 text-amber-500 rounded-2xl flex items-center justify-center text-2xl">
                            <i class="fa-solid fa-star"></i>
                        </div>
                    </div>
                </div>

                <!-- Analytics Charts -->
                <div class="grid lg:grid-cols-3 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 lg:col-span-2">
                        <h3 class="font-bold text-slate-900 mb-4"><i class="fa-solid fa-chart-line text-blue-600 mr-2"></i> Appointments Trend</h3>
                        <canvas id="trendChart" height="110"></canvas>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col items-center justify-center">
                        <h3 class="font-bold text-slate-900 mb-4 self-start"><i class="fa-solid fa-star text-amber-500 mr-2"></i> Avg. Review Rating</h3>
                        <div class="text-5xl font-black text-amber-500">{{ chart_data['avg_rating'] }}<span class="text-lg text-slate-400">/5</span></div>
                        <canvas id="ratingChart" class="mt-4" height="140"></canvas>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                        <h3 class="font-bold text-slate-900 mb-4"><i class="fa-solid fa-briefcase-medical text-indigo-600 mr-2"></i> Appointments by Service</h3>
                        <canvas id="serviceChart" height="220"></canvas>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                        <h3 class="font-bold text-slate-900 mb-4"><i class="fa-solid fa-location-dot text-emerald-600 mr-2"></i> Appointments by Location</h3>
                        <canvas id="locationChart" height="220"></canvas>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                        <h3 class="font-bold text-slate-900 mb-4"><i class="fa-solid fa-user-tag text-purple-600 mr-2"></i> Users by Role</h3>
                        <canvas id="roleChart" height="220"></canvas>
                    </div>
                </div>

                <!-- Admin Worker Onboarding Form -->
                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h3 class="text-lg font-bold text-slate-900 mb-4"><i class="fa-solid fa-user-plus text-blue-600 mr-2"></i> Create Worker Account</h3>
                    <form action="/admin/create-worker" method="POST" class="grid md:grid-cols-3 gap-4">
                        <input type="text" name="fullname" required placeholder="Worker Full Name" class="p-3 border rounded-xl">
                        <input type="email" name="email" required placeholder="Worker Email" class="p-3 border rounded-xl">
                        <input type="password" name="password" required placeholder="Default Password" class="p-3 border rounded-xl">
                        <button type="submit" class="md:col-span-3 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition">Add Care Worker</button>
                    </form>
                </div>

                <!-- System Logs Table -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-list-check text-indigo-600 mr-2"></i> Activity Audit Logs</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm text-slate-600">
                            <thead class="bg-slate-50 text-xs font-semibold uppercase text-slate-400 border-b">
                                <tr>
                                    <th class="p-4">User</th>
                                    <th class="p-4">Action</th>
                                    <th class="p-4">Timestamp</th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for log in logs %}
                                <tr>
                                    <td class="p-4 font-medium text-slate-900">{{ log['email'] }}</td>
                                    <td class="p-4">{{ log['action'] }}</td>
                                    <td class="p-4 text-xs font-mono text-slate-400">{{ log['timestamp'] }}</td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <script>
                    const chartData = {{ chart_data|tojson }};
                    const palette = ['#2563eb', '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6', '#0ea5e9', '#ec4899'];

                    new Chart(document.getElementById('trendChart'), {
                        type: 'line',
                        data: {
                            labels: chartData.appointments_trend.labels,
                            datasets: [{
                                label: 'Appointments',
                                data: chartData.appointments_trend.values,
                                borderColor: '#2563eb',
                                backgroundColor: 'rgba(37,99,235,0.1)',
                                tension: 0.35,
                                fill: true,
                                pointRadius: 3
                            }]
                        },
                        options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
                    });

                    new Chart(document.getElementById('ratingChart'), {
                        type: 'doughnut',
                        data: {
                            labels: chartData.reviews_by_rating.labels.map(r => r + ' ★'),
                            datasets: [{ data: chartData.reviews_by_rating.values, backgroundColor: palette }]
                        },
                        options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } } }
                    });

                    new Chart(document.getElementById('serviceChart'), {
                        type: 'doughnut',
                        data: {
                            labels: chartData.appointments_by_service.labels,
                            datasets: [{ data: chartData.appointments_by_service.values, backgroundColor: palette }]
                        },
                        options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } } }
                    });

                    new Chart(document.getElementById('locationChart'), {
                        type: 'bar',
                        data: {
                            labels: chartData.appointments_by_location.labels,
                            datasets: [{ label: 'Appointments', data: chartData.appointments_by_location.values, backgroundColor: '#10b981', borderRadius: 6 }]
                        },
                        options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { precision: 0 } } } }
                    });

                    new Chart(document.getElementById('roleChart'), {
                        type: 'bar',
                        data: {
                            labels: chartData.users_by_role.labels,
                            datasets: [{ label: 'Users', data: chartData.users_by_role.values, backgroundColor: '#8b5cf6', borderRadius: 6 }]
                        },
                        options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true, ticks: { precision: 0 } } } }
                    });
                </script>
                {% else %}
                <!-- Dedicated User / Client Portal Section -->
                <div class="grid md:grid-cols-3 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 md:col-span-2">
                        <h2 class="text-2xl font-bold text-slate-900 mb-2">Welcome to Your Carehive Portal</h2>
                        <p class="text-slate-600 text-sm mb-6">Manage your home healthcare requests, update your profile details, or book new medical visits.</p>
                        <div class="flex flex-wrap gap-4">
                            <a href="/#register" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-6 py-3 rounded-xl shadow transition text-sm inline-flex items-center gap-2">
                                <i class="fa-solid fa-calendar-plus"></i> Book Care Visit
                            </a>
                            <a href="/settings" class="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-6 py-3 rounded-xl border transition text-sm inline-flex items-center gap-2">
                                <i class="fa-solid fa-user-gear"></i> Account Settings
                            </a>
                        </div>
                    </div>
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 flex flex-col justify-between">
                        <div>
                            <span class="text-xs uppercase font-bold text-slate-400 block mb-1">Account Info</span>
                            <h3 class="font-bold text-slate-900 text-lg">{{ session['user']['fullname'] }}</h3>
                            <p class="text-xs text-slate-500 font-mono mt-0.5">{{ session['user']['email'] }}</p>
                        </div>
                        <div class="mt-4 pt-4 border-t border-slate-100">
                            <a href="/settings" class="text-xs text-blue-600 font-bold hover:underline">Edit profile settings →</a>
                        </div>
                    </div>
                </div>

                <!-- User Quick Activity History -->
                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-clock-rotate-left text-blue-600 mr-2"></i> Recent Account Activity</h3>
                    </div>
                    <div class="p-6">
                        {% if logs %}
                            <ul class="divide-y divide-slate-100 text-sm">
                                {% for log in logs %}
                                    {% if log['email'] == session['user']['email'] %}
                                    <li class="py-3 flex justify-between items-center">
                                        <span class="font-medium text-slate-800">{{ log['action'] }}</span>
                                        <span class="text-xs font-mono text-slate-400">{{ log['timestamp'] }}</span>
                                    </li>
                                    {% endif %}
                                {% endfor %}
                            </ul>
                        {% else %}
                            <p class="text-xs text-slate-400 italic">No recent activity logged.</p>
                        {% endif %}
                    </div>
                </div>
                {% endif %}
            </main>
        </div>
    </div>
</body>
</html>
"""

ADMIN_APPOINTMENTS_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Appointments | Carehive Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
</head>
<body class="bg-slate-100 text-slate-800">
    <div class="max-w-7xl mx-auto p-8">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-3xl font-bold text-slate-900">Appointments Registry</h1>
            <a href="/dashboard" class="bg-slate-800 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-slate-900">← Back to Dashboard</a>
        </div>
        <div class="bg-white rounded-2xl shadow border border-slate-200 overflow-hidden">
            <table class="w-full text-left text-sm text-slate-600">
                <thead class="bg-slate-50 text-xs uppercase font-semibold text-slate-400 border-b">
                    <tr>
                        <th class="p-4">Client Name</th>
                        <th class="p-4">Phone</th>
                        <th class="p-4">Service</th>
                        <th class="p-4">Location & GPS Pin</th>
                        <th class="p-4">Preferred Date</th>
                        <th class="p-4">Notes</th>
                    </tr>
                </thead>
                <tbody class="divide-y">
                    {% for appt in appointments %}
                    <tr>
                        <td class="p-4 font-bold text-slate-900">{{ appt['full_name'] }}</td>
                        <td class="p-4">{{ appt['phone'] }}</td>
                        <td class="p-4"><span class="bg-blue-100 text-blue-800 text-xs px-2.5 py-1 rounded-full font-medium">{{ appt['service'] }}</span></td>
                        <td class="p-4">
                            <div>{{ appt['location'] }}</div>
                            {% if appt['latitude'] and appt['longitude'] %}
                            <a href="https://www.google.com/maps?q={{ appt['latitude'] }},{{ appt['longitude'] }}" target="_blank" class="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline font-bold mt-1">
                                <i class="fa-solid fa-map-pin text-red-500"></i> View Live GPS Pin
                            </a>
                            {% endif %}
                        </td>
                        <td class="p-4 font-mono text-xs">{{ appt['preferred_date'] }}</td>
                        <td class="p-4 text-xs italic">{{ appt['notes'] }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


# ---------------------------------------------------------
# Application Routes
# ---------------------------------------------------------
@app.before_request
def update_last_active():
    if 'user' in session:
        email = session['user']['email']
        if email in USER_STATUS:
            USER_STATUS[email]['last_active'] = datetime.now(timezone.utc)


@app.route('/api/uganda-geo')
def get_uganda_geo():
    """API endpoint exposing the Uganda taxonomy data to frontend scripts."""
    return jsonify(uganda_geo.to_dict())


@app.route('/')
def home():
    conn = get_db_connection()
    reviews = conn.execute('SELECT * FROM reviews ORDER BY id DESC').fetchall()
    conn.close()
    return render_template_string(INDEX_HTML, reviews=reviews)


@app.route('/register', methods=['POST'])
def register_appointment():
    conn = get_db_connection()
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')
    
    conn.execute(
        'INSERT INTO appointments (full_name, phone, service, location, latitude, longitude, preferred_date, notes) VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
        (
            request.form['full_name'],
            request.form['phone'],
            request.form['service'],
            request.form['location'],
            float(lat) if lat else None,
            float(lng) if lng else None,
            request.form['preferred_date'],
            request.form.get('notes', '')
        )
    )
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/review', methods=['POST'])
def add_review():
    try:
        rating = int(request.form.get('rating', 5))
    except ValueError:
        rating = 5

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO reviews (client_name, rating, comment) VALUES (?, ?, ?)',
        (request.form['client_name'], rating, request.form['comment'])
    )
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        fullname = request.form.get('fullname')
        hashed_pw = generate_password_hash(request.form.get('password'))

        conn = get_db_connection()
        cursor = conn.cursor()
        try:
            cursor.execute('INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)', (email, fullname, 'client', hashed_pw))
            conn.commit()
        except sqlite3.IntegrityError:
            conn.close()
            return render_template_string(SIGNUP_HTML, error="An account with this email already exists.")
        conn.close()

        now = datetime.now(timezone.utc)
        USER_STATUS[email] = {'login_time': now, 'last_active': now, 'status': 'Active Online'}
        session['user'] = {'fullname': fullname, 'role': 'client', 'email': email}
        log_activity(email, "Client Registered Account")
        return redirect(url_for('dashboard'))

    return render_template_string(SIGNUP_HTML)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT name, role, password FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()
        conn.close()

        if user and check_password_hash(user['password'], password):
            now = datetime.now(timezone.utc)
            USER_STATUS[email] = {'login_time': now, 'last_active': now, 'status': 'Active Online'}
            session['user'] = {'fullname': user['name'], 'role': user['role'], 'email': email}
            log_activity(email, "User Logged In")
            return redirect(url_for('dashboard'))

        return render_template_string(LOGIN_HTML, error="Invalid email or password.")
    return render_template_string(LOGIN_HTML)


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user' not in session:
        return redirect(url_for('login'))

    email = session['user']['email']
    message = None

    if request.method == 'POST':
        new_name = request.form.get('fullname')
        new_pw = request.form.get('password')

        conn = get_db_connection()
        if new_pw and new_pw.strip():
            hashed = generate_password_hash(new_pw)
            conn.execute('UPDATE users SET name = ?, password = ? WHERE email = ?', (new_name, hashed, email))
        else:
            conn.execute('UPDATE users SET name = ? WHERE email = ?', (new_name, email))
        
        conn.commit()
        conn.close()

        session['user']['fullname'] = new_name
        log_activity(email, "Updated Account Settings")
        message = "Profile updated successfully!"

    user_info = {'email': email, 'fullname': session['user']['fullname']}
    return render_template_string(SETTINGS_HTML, user=user_info, message=message)


@app.route('/logout')
def logout():
    if 'user' in session:
        email = session['user']['email']
        log_activity(email, "User Logged Out")
        if email in USER_STATUS:
            USER_STATUS[email]['status'] = 'Logged Out'
        session.pop('user', None)
    return redirect(url_for('home'))


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    email = session['user']['email']
    activity_info = get_user_activity_info(email)

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT email, action, timestamp FROM logs ORDER BY id DESC LIMIT 50')
    logs = cursor.fetchall()

    cursor.execute('SELECT COUNT(*) FROM appointments')
    total_appointments = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM users')
    total_users = cursor.fetchone()[0]

    cursor.execute('SELECT COUNT(*) FROM reviews')
    total_reviews = cursor.fetchone()[0]

    chart_data = {}
    if session['user']['role'] == 'admin':
        cursor.execute('SELECT service, COUNT(*) as c FROM appointments GROUP BY service ORDER BY c DESC')
        rows = cursor.fetchall()
        chart_data['appointments_by_service'] = {
            'labels': [r['service'] for r in rows],
            'values': [r['c'] for r in rows]
        }

        cursor.execute('SELECT location, COUNT(*) as c FROM appointments GROUP BY location ORDER BY c DESC LIMIT 8')
        rows = cursor.fetchall()
        chart_data['appointments_by_location'] = {
            'labels': [r['location'] for r in rows],
            'values': [r['c'] for r in rows]
        }

        cursor.execute('''
            SELECT strftime('%Y-%m-%d', created_at) as day, COUNT(*) as c
            FROM appointments
            GROUP BY day
            ORDER BY day ASC
            LIMIT 14
        ''')
        rows = cursor.fetchall()
        chart_data['appointments_trend'] = {
            'labels': [r['day'] for r in rows],
            'values': [r['c'] for r in rows]
        }

        cursor.execute('SELECT role, COUNT(*) as c FROM users GROUP BY role')
        rows = cursor.fetchall()
        chart_data['users_by_role'] = {
            'labels': [r['role'] for r in rows],
            'values': [r['c'] for r in rows]
        }

        cursor.execute('SELECT rating, COUNT(*) as c FROM reviews GROUP BY rating ORDER BY rating ASC')
        rows = cursor.fetchall()
        rating_counts = {str(i): 0 for i in range(1, 6)}
        for r in rows:
            rating_counts[str(r['rating'])] = r['c']
        chart_data['reviews_by_rating'] = {
            'labels': list(rating_counts.keys()),
            'values': list(rating_counts.values())
        }

        cursor.execute('SELECT AVG(rating) as avg FROM reviews')
        avg_row = cursor.fetchone()
        chart_data['avg_rating'] = round(avg_row['avg'], 2) if avg_row['avg'] is not None else 0

    conn.close()

    stats = {'appointments': total_appointments, 'users': total_users, 'reviews': total_reviews}
    return render_template_string(DASHBOARD_HTML, logs=logs, activity=activity_info, stats=stats, chart_data=chart_data)


@app.route('/admin')
def admin_appointments():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    appointments = conn.execute('SELECT * FROM appointments ORDER BY id DESC').fetchall()
    conn.close()
    return render_template_string(ADMIN_APPOINTMENTS_HTML, appointments=appointments)


@app.route('/admin/create-worker', methods=['POST'])
def create_worker():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    email = request.form.get('email')
    fullname = request.form.get('fullname')
    hashed_pw = generate_password_hash(request.form.get('password'))

    conn = get_db_connection()
    try:
        conn.execute('INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)', (email, fullname, 'worker', hashed_pw))
        conn.commit()
        log_activity(session['user']['email'], f"Created Worker Account: {email}")
    except sqlite3.IntegrityError:
        pass
    finally:
        conn.close()

    return redirect(url_for('dashboard'))


if __name__ == '__main__':
    init_db()
    print("\n===============================================")
    print(" CAREHIVE HOMECARE LIMITED APP RUNNING")
    print(" URL: http://127.0.0.1:5000")
    print(" Admin Login: admin@carehive.com / admin123")
    print("===============================================\n")
    app.run(host='127.0.0.1', port=5000, debug=True)