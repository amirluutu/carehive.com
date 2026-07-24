"""
Carehive Homecare Limited — Unified Complete Flask Application (Production-Ready)

Features:
  - Public marketing site with Hero Care Finder & Trust Bar
  - Integrated Uganda Geographical Taxonomy Registry with API & Cascading Dropdowns
  - Live GPS Location capture (with dropdown override) and Google Maps sharing
  - Disappearing Dashboard Callout Banner prompting user Login/Signup
  - Appointment registration with valid contact verification (`/register`)
  - Client review submission (`/review`)
  - User authentication & portal (`/signup`, `/login`, `/logout`)
  - User Account Settings (`/settings`)
  - User activity log tracking & status monitoring
  - Enhanced User & Admin Dashboards with Chart.js analytics (`/dashboard`)
  - Admin worker creation (`/admin/create-worker`) & appointments manager (`/admin`)
"""

import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify
from werkzeug.security import generate_password_hash, check_password_hash


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'super-secret-carehive-key-2026')
DATABASE_URL = os.environ.get('DATABASE_URL')

# In-memory session tracking registry
USER_STATUS = {}


def log_activity(email: str, action: str):
    """Logs user actions into the persistent database audit log."""
    try:
        conn = get_db_connection()
        conn.execute(
            'INSERT INTO logs (email, action, timestamp) VALUES (?, ?, ?)',
            (email, action, datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC'))
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Logging error: {e}")


def get_user_activity_info(email: str):
    """Retrieves or calculates user session uptime and activity status."""
    now = datetime.now(timezone.utc)
    if email not in USER_STATUS:
        USER_STATUS[email] = {
            'login_time': now,
            'last_active': now,
            'status': 'Active Online'
        }
    
    data = USER_STATUS[email]
    if data['status'] == 'Active Online':
        delta = now - data['login_time']
        hours, remainder = divmod(int(delta.total_seconds()), 3600)
        minutes, seconds = divmod(remainder, 60)
        duration_str = f"{hours}h {minutes}m {seconds}s"
    else:
        duration_str = "Session Ended"

    return {
        'status': data['status'],
        'duration': duration_str,
        'last_active': data['last_active'].strftime('%H:%M:%S UTC')
    }


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
    """Main registry to manage the geographical structure of Uganda."""
    def __init__(self):
        self.districts = {}

    def add_location(self, region: str, district_name: str, county_name: str, sub_county_name: str, village_name: str):
        if district_name not in self.districts:
            self.districts[district_name] = District(district_name, region)
        
        district = self.districts[district_name]
        county = district.add_county(county_name)
        sub_county = county.add_sub_county(sub_county_name)
        sub_county.add_village(village_name)

    def add_district(self, region: str, district_name: str):
        if district_name not in self.districts:
            self.districts[district_name] = District(district_name, region)

    def to_dict(self):
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

# Instantiate global registry, scoped to the major cities/towns Carehive
# actually serves. Anywhere else is captured via the "Other / Type Your
# Area" manual entry already built into the booking form.
uganda_geo = UgandaGeographyRegistry()

# Kampala — 5 official divisions, several parishes each
uganda_geo.add_location("Central", "Kampala", "Central Division", "Nakasero", "Nakasero I")
uganda_geo.add_location("Central", "Kampala", "Central Division", "Kololo", "Kololo I")
uganda_geo.add_location("Central", "Kampala", "Central Division", "Old Kampala", "Old Kampala")
uganda_geo.add_location("Central", "Kampala", "Kawempe Division", "Bwaise", "Bwaise I")
uganda_geo.add_location("Central", "Kampala", "Kawempe Division", "Kazo", "Kazo Angola")
uganda_geo.add_location("Central", "Kampala", "Kawempe Division", "Kyebando", "Kyebando")
uganda_geo.add_location("Central", "Kampala", "Makindye Division", "Ssabagabo", "Kanyanya")
uganda_geo.add_location("Central", "Kampala", "Makindye Division", "Nsambya", "Nsambya")
uganda_geo.add_location("Central", "Kampala", "Makindye Division", "Salaama", "Salaama Road")
uganda_geo.add_location("Central", "Kampala", "Nakawa Division", "Kireka", "Kireka D")
uganda_geo.add_location("Central", "Kampala", "Nakawa Division", "Ntinda", "Ntinda")
uganda_geo.add_location("Central", "Kampala", "Nakawa Division", "Naguru", "Naguru")
uganda_geo.add_location("Central", "Kampala", "Rubaga Division", "Mengo", "Mengo Kisenyi")
uganda_geo.add_location("Central", "Kampala", "Rubaga Division", "Nateete", "Nateete")
uganda_geo.add_location("Central", "Kampala", "Rubaga Division", "Busega", "Busega")

# Wakiso — Kyadondo & Busiro counties, main municipalities/town councils
uganda_geo.add_location("Central", "Wakiso", "Kyadondo County", "Kira Municipality", "Kira")
uganda_geo.add_location("Central", "Wakiso", "Kyadondo County", "Namugongo Division", "Kinawataka Road")
uganda_geo.add_location("Central", "Wakiso", "Kyadondo County", "Nansana Municipality", "Nansana")
uganda_geo.add_location("Central", "Wakiso", "Kyadondo County", "Kasangati Town Council", "Kasangati")
uganda_geo.add_location("Central", "Wakiso", "Kyadondo County", "Wakiso Town Council", "Wakiso Central")
uganda_geo.add_location("Central", "Wakiso", "Busiro County", "Entebbe Municipality", "Entebbe Town")
uganda_geo.add_location("Central", "Wakiso", "Busiro County", "Kajjansi Town Council", "Kajjansi")
uganda_geo.add_location("Central", "Wakiso", "Busiro County", "Nabweru Sub-County", "Nabweru")

# Mukono — Municipality divisions + surrounding sub-counties
uganda_geo.add_location("Central", "Mukono", "Mukono Municipality", "Central Division", "Mukono Town")
uganda_geo.add_location("Central", "Mukono", "Mukono Municipality", "Goma Division", "Goma")
uganda_geo.add_location("Central", "Mukono", "Mukono Municipality", "Nabuti Division", "Nabuti")
uganda_geo.add_location("Central", "Mukono", "Mukono County", "Nakisunga Sub-County", "Nakisunga")
uganda_geo.add_location("Central", "Mukono", "Mukono County", "Ntenjeru Sub-County", "Ntenjeru")
uganda_geo.add_location("Central", "Mukono", "Mukono County", "Seeta-Nazigo Sub-County", "Seeta")
uganda_geo.add_location("Central", "Mukono", "Mukono County", "Goma Sub-County", "Naggalama")

# Jinja — Jinja City divisions + Jinja District sub-counties
uganda_geo.add_location("Eastern", "Jinja", "Jinja City", "Central Division", "Jinja Central")
uganda_geo.add_location("Eastern", "Jinja", "Jinja City", "Northern Division", "Walukuba")
uganda_geo.add_location("Eastern", "Jinja", "Jinja City", "Mpumudde-Kimaka Division", "Kimaka")
uganda_geo.add_location("Eastern", "Jinja", "Jinja District", "Budondo Sub-County", "Budondo")
uganda_geo.add_location("Eastern", "Jinja", "Jinja District", "Buwenge Sub-County", "Buwenge")
uganda_geo.add_location("Eastern", "Jinja", "Jinja District", "Mafubira Sub-County", "Mafubira")
uganda_geo.add_location("Eastern", "Jinja", "Jinja District", "Kakira Town Council", "Kakira")

# Mbale — Mbale City divisions + Mbale District sub-counties
uganda_geo.add_location("Eastern", "Mbale", "Mbale City", "Northern Division", "Namakwekwe")
uganda_geo.add_location("Eastern", "Mbale", "Mbale City", "Industrial Division", "Namatala")
uganda_geo.add_location("Eastern", "Mbale", "Mbale City", "Wanale Division", "Busamaga")
uganda_geo.add_location("Eastern", "Mbale", "Mbale District", "Bungokho Sub-County", "Bungokho")
uganda_geo.add_location("Eastern", "Mbale", "Mbale District", "Busiu Sub-County", "Busiu")
uganda_geo.add_location("Eastern", "Mbale", "Mbale District", "Nakaloke Sub-County", "Nakaloke")

# Masaka — Masaka City divisions + Masaka District sub-counties
uganda_geo.add_location("Central", "Masaka", "Masaka City", "Katwe-Butego Division", "Katwe")
uganda_geo.add_location("Central", "Masaka", "Masaka City", "Nyendo-Mukungwe Division", "Nyendo")
uganda_geo.add_location("Central", "Masaka", "Masaka City", "Kimaanya-Kabonera Division", "Kimaanya")
uganda_geo.add_location("Central", "Masaka", "Masaka District", "Kyanamukaaka Sub-County", "Kyanamukaaka")
uganda_geo.add_location("Central", "Masaka", "Masaka District", "Bukakata Sub-County", "Bukakata")

# Mbarara — Mbarara City divisions + Mbarara District sub-counties
uganda_geo.add_location("Western", "Mbarara", "Mbarara City", "Kamukuzi Division", "Kamukuzi")
uganda_geo.add_location("Western", "Mbarara", "Mbarara City", "Kakoba Division", "Kakoba")
uganda_geo.add_location("Western", "Mbarara", "Mbarara City", "Nyamitanga Division", "Nyamitanga")
uganda_geo.add_location("Western", "Mbarara", "Mbarara City", "Biharwe Division", "Biharwe")
uganda_geo.add_location("Western", "Mbarara", "Mbarara District", "Kakiika Sub-County", "Kakiika")
uganda_geo.add_location("Western", "Mbarara", "Mbarara District", "Rubaya Sub-County", "Rubaya")

# Gulu — Gulu City divisions + Gulu District sub-counties
uganda_geo.add_location("Northern", "Gulu", "Gulu City", "Laroo-Pece Division", "Pece")
uganda_geo.add_location("Northern", "Gulu", "Gulu City", "Bardege-Layibi Division", "Layibi")
uganda_geo.add_location("Northern", "Gulu", "Gulu City", "Layibi Division", "Layibi Techo")
uganda_geo.add_location("Northern", "Gulu", "Gulu District", "Bungatira Sub-County", "Bungatira")
uganda_geo.add_location("Northern", "Gulu", "Gulu District", "Awach Sub-County", "Awach")


# ---------------------------------------------------------
# Custom Jinja Filter for Safe Image URLs
# ---------------------------------------------------------
@app.template_filter('url_encode_path')
def url_encode_path(s):
    return quote(s)


# ---------------------------------------------------------
# Database Helpers & Initialization
# ---------------------------------------------------------
class PGCursor:
    """Wraps a psycopg2 cursor so the app's existing SQLite-style call sites
    (using '?' placeholders and .lastrowid) work unchanged against Postgres."""
    def __init__(self, cur):
        self._cur = cur

    def execute(self, query, params=()):
        self._cur.execute(query.replace('?', '%s'), params)
        return self

    def fetchone(self):
        return self._cur.fetchone()

    def fetchall(self):
        return self._cur.fetchall()

    @property
    def lastrowid(self):
        self._cur.execute("SELECT lastval()")
        return self._cur.fetchone()['lastval']


class PGConnection:
    """Wraps a psycopg2 connection so conn.execute(...) / row['col'] access
    (both SQLite conveniences the templates and routes rely on) keep working."""
    def __init__(self, conn):
        self._conn = conn

    def cursor(self):
        return PGCursor(self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor))

    def execute(self, query, params=()):
        c = self.cursor()
        c.execute(query, params)
        return c

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def get_db_connection():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return PGConnection(conn)


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password TEXT NOT NULL,
            permissions TEXT,
            date_of_birth TEXT,
            phone TEXT,
            status TEXT DEFAULT 'active',
            on_duty INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS logs (
            id SERIAL PRIMARY KEY,
            email TEXT NOT NULL,
            action TEXT NOT NULL,
            timestamp TEXT NOT NULL
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS appointments (
            id SERIAL PRIMARY KEY,
            full_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            location TEXT NOT NULL,
            latitude REAL,
            longitude REAL,
            service TEXT NOT NULL,
            preferred_date TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            reference TEXT,
            patient_dob TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS reviews (
            id SERIAL PRIMARY KEY,
            client_name TEXT NOT NULL,
            rating INTEGER NOT NULL,
            comment TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    # Idempotent for older/partially-migrated databases.
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS reference TEXT")
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS patient_dob TEXT")
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS gender TEXT")
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS photo BYTEA")
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS approval_status TEXT DEFAULT 'approved'")
    cursor.execute("ALTER TABLE appointments ADD COLUMN IF NOT EXISTS booked_by_email TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS permissions TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS date_of_birth TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS phone TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'active'")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS on_duty INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nin TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS nssf_number TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS tin_number TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS passport_number TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_of_kin_name TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS next_of_kin_phone TEXT")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS id_photo BYTEA")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS failed_login_count INTEGER DEFAULT 0")
    cursor.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS locked_until TIMESTAMP")

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_users_role ON users(role);')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_appointments_service ON appointments(service);')

    admin_email = "admin@carehive.com"
    cursor.execute("SELECT password FROM users WHERE email = ?", (admin_email,))
    admin_row = cursor.fetchone()
    # A valid Werkzeug hash carries its method prefix (e.g. "pbkdf2:sha256:...").
    # Older data seeded a bare SHA-256 digest, which check_password_hash cannot
    # verify, so the admin could never log in. Create or repair the account here.
    admin_pass_ok = admin_row is not None and ':' in (admin_row['password'] or '')
    if not admin_pass_ok:
        admin_pass = generate_password_hash("admin123")
        if admin_row is None:
            cursor.execute(
                'INSERT INTO users (email, name, role, password) VALUES (?, ?, ?, ?)',
                (admin_email, 'System Administrator', 'admin', admin_pass)
            )
        else:
            cursor.execute(
                "UPDATE users SET role = 'admin', password = ? WHERE email = ?",
                (admin_pass, admin_email)
            )

    cursor.execute('SELECT COUNT(*) AS cnt FROM reviews')
    if cursor.fetchone()['cnt'] == 0:
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
# HTML Templates
# ---------------------------------------------------------
COMMON_HEAD = """
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
"""

INDEX_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Carehive Homecare Limited - Compassionate & Connected Care</title>
    <link rel="preconnect" href="https://cdn.tailwindcss.com">
    <link rel="preconnect" href="https://cdnjs.cloudflare.com" crossorigin>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-50 text-slate-800 antialiased">
    <div class="bg-slate-900 text-blue-100 text-xs py-2 px-6 border-b border-slate-800">
        <div class="max-w-7xl mx-auto flex justify-between items-center flex-wrap gap-2">
            <div class="flex items-center space-x-6">
                <a href="tel:+256753976912" class="hover:text-white transition-colors"><i class="fa-solid fa-phone text-blue-400 mr-2"></i>+256 753 976 912</a>
                <a href="https://wa.me/256708083118" target="_blank" rel="noopener" class="hover:text-white transition-colors"><i class="fa-brands fa-whatsapp text-emerald-400 mr-2"></i>+256 708 083 118</a>
                <a href="mailto:carehivehomecare@gmail.com" class="hidden sm:inline hover:text-white transition-colors"><i class="fa-solid fa-envelope text-amber-400 mr-2"></i>carehivehomecare@gmail.com</a>
            </div>
            <div class="text-blue-300 font-medium"><i class="fa-solid fa-location-dot mr-1"></i>Kampala & Greater Uganda</div>
        </div>
    </div>

    <header class="sticky top-0 z-40 bg-white/95 backdrop-blur-md border-b border-slate-100 shadow-sm">
        <div class="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
            <div class="flex items-center gap-3">
                <button type="button" onclick="openLogoLightbox()" title="View full logo" class="cursor-zoom-in">
                    <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="Carehive Logo" class="h-14 w-auto rounded-xl object-contain border border-slate-100 shadow-sm hover:opacity-80 transition-opacity" onerror="this.onerror=null; this.src='https://placehold.co/180x180?text=Carehive';">
                </button>
                <a href="/">
                    <span class="text-xl md:text-2xl font-bold text-slate-900 tracking-tight block">Care<span class="text-blue-600">Hive</span></span>
                    <span class="text-[10px] text-blue-700 font-bold tracking-wider uppercase block -mt-1">Homecare Limited</span>
                </a>
            </div>

            <nav class="hidden md:flex items-center gap-8 text-sm font-semibold text-slate-600">
                <a href="#services" class="hover:text-blue-600 transition-colors">Services</a>
                <a href="#how-it-works" class="hover:text-blue-600 transition-colors">How It Works</a>
                <a href="#reviews" class="hover:text-blue-600 transition-colors">Testimonials</a>
                <a href="#contact" class="hover:text-blue-600 transition-colors">Contact</a>
                <button onclick="openBookingForm()" class="hover:text-blue-600 transition-colors">Book Care</button>
            </nav>

            <div class="flex items-center gap-3">
                <a href="/login" class="text-sm font-semibold text-slate-700 hover:text-blue-600 px-3 py-2 transition-colors">Log In</a>
                <a href="/signup" class="bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold px-5 py-2.5 rounded-xl shadow-md shadow-blue-600/20 transition-all hover:-translate-y-0.5">
                    Sign Up
                </a>
            </div>
        </div>
    </header>

    <div id="logo-lightbox" class="hidden fixed inset-0 z-[60] bg-slate-900/85 backdrop-blur-sm flex items-center justify-center p-6" onclick="closeLogoLightbox()">
        <button type="button" onclick="closeLogoLightbox()" class="absolute top-6 right-6 text-white/80 hover:text-white text-3xl"><i class="fa-solid fa-xmark"></i></button>
        <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="Carehive Logo" class="max-w-full max-h-full rounded-2xl shadow-2xl" onerror="this.onerror=null; this.src='https://placehold.co/400x400?text=Carehive';">
    </div>
    <script>
        function openLogoLightbox() { document.getElementById('logo-lightbox').classList.remove('hidden'); }
        function closeLogoLightbox() { document.getElementById('logo-lightbox').classList.add('hidden'); }
    </script>

    {% if booking_reference %}
    <div class="fixed inset-0 z-50 bg-slate-900/70 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white max-w-md w-full rounded-3xl shadow-2xl p-8 text-center space-y-4">
            <div class="w-16 h-16 rounded-full bg-amber-100 text-amber-600 flex items-center justify-center mx-auto text-2xl">
                <i class="fa-solid fa-hourglass-half"></i>
            </div>
            <h3 class="text-xl font-bold text-slate-900">Request Received — Pending Approval</h3>
            <p class="text-sm text-slate-500">Your reference number is</p>
            <p class="text-lg font-mono font-bold text-blue-700 bg-blue-50 rounded-xl py-2">{{ booking_reference }}</p>
            <p class="text-xs text-slate-500">Our team will review your request and confirm your visit date. Log in any time to check its status.</p>
            <a href="/ticket/{{ booking_reference }}" target="_blank" class="inline-flex w-full justify-center items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition text-sm">
                <i class="fa-solid fa-file-pdf"></i> View / Download Request Receipt
            </a>
            <a href="/" class="block text-xs text-slate-400 hover:text-slate-600">Close</a>
        </div>
    </div>
    {% endif %}

    {% if booking_error %}
    <div class="fixed inset-0 z-50 bg-slate-900/70 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="bg-white max-w-md w-full rounded-3xl shadow-2xl p-8 text-center space-y-4">
            <div class="w-16 h-16 rounded-full bg-red-100 text-red-600 flex items-center justify-center mx-auto text-2xl">
                <i class="fa-solid fa-triangle-exclamation"></i>
            </div>
            <h3 class="text-xl font-bold text-slate-900">Booking Couldn't Be Submitted</h3>
            <p class="text-sm text-slate-600">{{ booking_error }}</p>
            <a href="/" class="block bg-slate-900 hover:bg-slate-800 text-white font-bold py-3 rounded-xl transition text-sm">Try Again</a>
        </div>
    </div>
    {% endif %}

    <main>
        <section class="relative py-16 lg:py-24 overflow-hidden bg-slate-900 text-white">
            <style>
                @keyframes hero-ken-burns {
                    0%   { transform: scale(1) translate(0, 0); }
                    50%  { transform: scale(1.12) translate(-1.5%, -1%); }
                    100% { transform: scale(1) translate(0, 0); }
                }
                #hero-bg-img { animation: hero-ken-burns 22s ease-in-out infinite; }
                @media (prefers-reduced-motion: reduce) { #hero-bg-img { animation: none; } }
            </style>
            <div class="absolute inset-0 z-0">
                <img id="hero-bg-img" src="/static/images/{{ 'home-hero-background.jpg'|url_encode_path }}" alt="" class="w-full h-full object-cover opacity-60" onerror="this.onerror=null; this.src='https://images.unsplash.com/photo-1631815589968-fdb09a223b1e?auto=format&fit=crop&w=1600&q=80';">
                <div class="absolute inset-0 bg-gradient-to-r from-slate-900/95 via-slate-900/75 to-slate-900/40"></div>
            </div>
            <div class="relative z-10 max-w-7xl mx-auto px-6 grid lg:grid-cols-2 gap-12 items-center">
                <div class="space-y-6 text-center lg:text-left">
                    <div class="inline-flex items-center gap-2 bg-blue-500/10 border border-blue-500/30 text-blue-300 px-3 py-1.5 rounded-full text-xs font-semibold uppercase tracking-wider">
                        <span class="w-2 h-2 rounded-full bg-blue-400 animate-ping"></span>
                        Compassionate Care At Your Home
                    </div>
                    <h1 class="text-4xl sm:text-5xl lg:text-6xl font-extrabold text-white leading-tight">
                        Safe nursing care, <span class="text-blue-400">connected community.</span>
                    </h1>
                    <p class="text-slate-300 text-base sm:text-lg max-w-xl mx-auto lg:mx-0 leading-relaxed">
                        Carehive Homecare Limited delivers vetted, professional medical support and eldercare directly to your family's doorstep across Uganda.
                    </p>

                    <div class="bg-white p-4 rounded-2xl shadow-2xl text-slate-800 space-y-3 mt-6">
                        <div class="grid sm:grid-cols-2 gap-3 text-left">
                            <div>
                                <label class="block text-xs font-bold text-slate-400 uppercase mb-1">Care Required</label>
                                <select id="hero-service-select" class="w-full text-sm font-semibold bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-500">
                                    <option value="Blood Pressure Check">Blood Pressure Check</option>
                                    <option value="Elderly Care">Elderly & Respiratory Care</option>
                                    <option value="Baby Care">Pediatric & Baby Care</option>
                                    <option value="Post Surgery Care">Post-Surgery Support</option>
                                    <option value="Other">Other (Specify in Form)</option>
                                </select>
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-400 uppercase mb-1">Select District</label>
                                <select id="hero-district-select" class="w-full text-sm font-semibold bg-slate-50 border border-slate-200 rounded-lg p-2.5 focus:outline-none focus:border-blue-500">
                                    <option value="">-- All Districts --</option>
                                </select>
                            </div>
                        </div>
                        <button onclick="handleHeroBooking()" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition-all flex items-center justify-center gap-2">
                            <i class="fa-solid fa-magnifying-glass"></i> Find Care & Book
                        </button>
                    </div>
                </div>

                <div class="relative flex justify-center items-center min-h-[420px]">
                    <div class="w-full max-w-sm bg-white p-7 rounded-3xl shadow-2xl text-slate-800 space-y-7 relative z-10 border border-slate-100">
                        <div class="flex items-center justify-between border-b border-slate-100 pb-4">
                            <div class="flex items-center gap-3">
                                <div class="w-12 h-12 rounded-full bg-blue-100 flex items-center justify-center text-blue-700 font-bold text-lg">CH</div>
                                <div>
                                    <h3 class="font-bold text-slate-900">Carehive Staff</h3>
                                    <p class="text-xs text-slate-500">Verified Homecare Specialist</p>
                                </div>
                            </div>
                            <span class="bg-emerald-50 text-emerald-700 text-xs font-medium px-2.5 py-1 rounded-full border border-emerald-200 flex items-center gap-1">
                                <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                                {% if site_stats['on_duty_count'] > 0 %}{{ site_stats['on_duty_count'] }} On Duty{% else %}On Duty{% endif %}
                            </span>
                        </div>
                        <div class="space-y-3">
                            <p class="text-xs font-semibold text-slate-400 uppercase tracking-wider">Scheduled Care Visit</p>
                            <div class="flex items-center justify-between p-3 bg-slate-50 rounded-xl text-sm border border-slate-100">
                                <span class="font-medium text-slate-700"><i class="fa-solid fa-pills text-blue-600 mr-2"></i> Medication Management</span>
                                <span class="text-xs bg-blue-100 text-blue-800 px-2 py-0.5 rounded font-semibold">Completed</span>
                            </div>
                            <div class="flex items-center justify-between p-3 bg-slate-50 rounded-xl text-sm border border-slate-100">
                                <span class="font-medium text-slate-700"><i class="fa-solid fa-stethoscope text-amber-500 mr-2"></i> Vital Signs Checkup</span>
                                <span class="text-xs bg-amber-100 text-amber-800 px-2 py-0.5 rounded font-semibold">Today</span>
                            </div>
                        </div>
                    </div>
                    <div class="absolute -top-10 -right-10 w-72 h-72 bg-blue-500/20 rounded-full blur-3xl -z-0"></div>
                </div>
            </div>
        </section>

        <div class="bg-white border-b border-slate-200 py-8 px-6">
            <div class="max-w-7xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-6 text-center">
                <div>
                    <p class="text-3xl font-extrabold text-slate-900">{{ site_stats['avg_rating'] }} / 5.0</p>
                    <p class="text-xs text-slate-500 font-medium uppercase mt-1">Client Satisfaction</p>
                </div>
                <div>
                    <p class="text-3xl font-extrabold text-slate-900">100%</p>
                    <p class="text-xs text-slate-500 font-medium uppercase mt-1">Vetted Medical Staff</p>
                </div>
                <div>
                    <p class="text-3xl font-extrabold text-slate-900">24 / 7</p>
                    <p class="text-xs text-slate-500 font-medium uppercase mt-1">On-Call Support</p>
                </div>
                <div>
                    <p class="text-3xl font-extrabold text-slate-900">{{ site_stats['district_count'] }}+</p>
                    <p class="text-xs text-slate-500 font-medium uppercase mt-1">Districts Covered</p>
                </div>
            </div>
        </div>

        <section id="services" class="py-20 bg-white">
            <div class="max-w-7xl mx-auto px-6">
                <div class="text-center max-w-2xl mx-auto mb-16">
                    <h2 class="text-3xl font-bold text-slate-900">Our Nursing & Care Services</h2>
                    <p class="text-slate-600 mt-3">Tailored healthcare plans designed specifically for your home environment.</p>
                </div>

                <div class="grid md:grid-cols-3 gap-8">
                    <div class="rounded-2xl bg-slate-50 border border-slate-100 overflow-hidden hover:shadow-lg transition-all flex flex-col justify-between">
                        <div>
                            <img src="/static/images/{{ 'nursing-care.jpeg'|url_encode_path }}" alt="Nursing Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1576091160399-112ba8d25d1d?auto=format&fit=crop&w=600&q=80';">
                            <div class="p-6">
                                <h3 class="text-xl font-bold text-slate-900 mb-2">Professional Nursing Care</h3>
                                <p class="text-slate-600 text-sm leading-relaxed">
                                    Wound dressing, post-operative rehabilitation, vital signs tracking, and medication administration by certified nurses.
                                </p>
                            </div>
                        </div>
                        <div class="p-6 pt-0">
                            <button onclick="openBookingForm('Wound Dressing')" class="text-sm font-bold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1">
                                Book Nursing Care <i class="fa-solid fa-arrow-right text-xs"></i>
                            </button>
                        </div>
                    </div>

                    <div class="rounded-2xl bg-slate-50 border border-slate-100 overflow-hidden hover:shadow-lg transition-all flex flex-col justify-between">
                        <div>
                            <img src="/static/images/{{ 'broncure.jpeg'|url_encode_path }}" alt="Elderly Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1584515979956-d9f6e5d09982?auto=format&fit=crop&w=600&q=80';">
                            <div class="p-6">
                                <h3 class="text-xl font-bold text-slate-900 mb-2">Respiratory & Elderly Care</h3>
                                <p class="text-slate-600 text-sm leading-relaxed">
                                    Comprehensive support for senior family members, mobility assistance, respiratory monitoring, and continuous companion care.
                                </p>
                            </div>
                        </div>
                        <div class="p-6 pt-0">
                            <button onclick="openBookingForm('Elderly Care')" class="text-sm font-bold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1">
                                Book Elderly Care <i class="fa-solid fa-arrow-right text-xs"></i>
                            </button>
                        </div>
                    </div>

                    <div class="rounded-2xl bg-slate-50 border border-slate-100 overflow-hidden hover:shadow-lg transition-all flex flex-col justify-between">
                        <div>
                            <img src="/static/images/{{ 'baby-care.jpeg'|url_encode_path }}" alt="Baby Care" class="w-full h-48 object-cover" onerror="this.src='https://images.unsplash.com/photo-1555252333-9f8e92e65df9?auto=format&fit=crop&w=600&q=80';">
                            <div class="p-6">
                                <h3 class="text-xl font-bold text-slate-900 mb-2">Pediatric & Baby Care</h3>
                                <p class="text-slate-600 text-sm leading-relaxed">
                                    Gentle postnatal support for mothers and newborns, specialized pediatric nursing care, and infant wellness checks.
                                </p>
                            </div>
                        </div>
                        <div class="p-6 pt-0">
                            <button onclick="openBookingForm('Baby Care')" class="text-sm font-bold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1">
                                Book Baby Care <i class="fa-solid fa-arrow-right text-xs"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <section id="how-it-works" class="py-20 bg-slate-50 border-t border-b border-slate-100">
            <div class="max-w-7xl mx-auto px-6">
                <div class="text-center max-w-2xl mx-auto mb-16">
                    <h2 class="text-3xl font-bold text-slate-900">How Carehive Works</h2>
                    <p class="text-slate-600 mt-3">Simple steps to coordinate homecare visits effortlessly.</p>
                </div>
                <div class="grid md:grid-cols-3 gap-8 text-center">
                    <div class="space-y-4 p-6 bg-white rounded-2xl shadow-sm border border-slate-100">
                        <div class="w-12 h-12 rounded-full bg-blue-600 text-white font-bold text-lg flex items-center justify-center mx-auto shadow-md">1</div>
                        <h3 class="text-lg font-bold text-slate-900">Select Service & Location</h3>
                        <p class="text-sm text-slate-600">Choose required healthcare assistance and set your location using GPS or regional dropdowns.</p>
                    </div>
                    <div class="space-y-4 p-6 bg-white rounded-2xl shadow-sm border border-slate-100">
                        <div class="w-12 h-12 rounded-full bg-blue-600 text-white font-bold text-lg flex items-center justify-center mx-auto shadow-md">2</div>
                        <h3 class="text-lg font-bold text-slate-900">Schedule & Match</h3>
                        <p class="text-sm text-slate-600">Set your preferred care date. We match your request with trained medical professionals.</p>
                    </div>
                    <div class="space-y-4 p-6 bg-white rounded-2xl shadow-sm border border-slate-100">
                        <div class="w-12 h-12 rounded-full bg-blue-600 text-white font-bold text-lg flex items-center justify-center mx-auto shadow-md">3</div>
                        <h3 class="text-lg font-bold text-slate-900">Receive Care & Track</h3>
                        <p class="text-sm text-slate-600">Our caregiver arrives at your home. Track updates and records in your portal dashboard.</p>
                    </div>
                </div>
            </div>
        </section>

        <section id="reviews" class="py-12 bg-white">
            <div class="max-w-4xl mx-auto px-6">
                <div class="text-center max-w-2xl mx-auto mb-6">
                    <h2 class="text-2xl font-bold text-slate-900">Client Testimonials</h2>
                    <p class="text-slate-600 text-sm mt-1.5">Hear from families who trust Carehive Homecare for their loved ones.</p>
                </div>

                <div class="flex flex-wrap justify-center gap-3 mb-5">
                    {% for review in reviews %}
                    <div class="bg-slate-50 p-4 rounded-2xl border border-slate-100 shadow-sm flex flex-col w-full sm:w-64">
                        <div class="flex items-center gap-2.5 mb-1.5">
                            <div class="w-7 h-7 shrink-0 rounded-full bg-blue-600 text-white text-xs font-bold flex items-center justify-center">
                                {{ review['client_name'][:1]|upper }}
                            </div>
                            <div class="min-w-0">
                                <h4 class="font-bold text-slate-900 text-xs truncate">{{ review['client_name'] }}</h4>
                                <div class="text-amber-400 text-[10px]">
                                    {% for i in range(review['rating']) %}<i class="fa-solid fa-star"></i>{% endfor %}
                                </div>
                            </div>
                        </div>
                        <p class="text-slate-600 text-xs italic line-clamp-3">"{{ review['comment'] }}"</p>
                    </div>
                    {% endfor %}
                </div>

                <div class="text-center">
                    <button type="button" onclick="toggleReviewForm()" id="review-form-toggle" class="text-xs font-bold text-blue-600 hover:text-blue-700 inline-flex items-center gap-1.5">
                        <i class="fa-solid fa-pen-nib"></i> Share Your Experience
                    </button>
                </div>

                <div id="review-form-wrap" class="hidden mt-4">
                    <div class="bg-slate-50 p-5 rounded-2xl border border-slate-200 max-w-sm mx-auto shadow-sm">
                        <form action="/review" method="POST" class="space-y-2.5">
                            <input type="text" name="client_name" required placeholder="Your Name" class="w-full p-2 border border-slate-200 rounded-xl text-xs focus:outline-none focus:border-blue-500">
                            <select name="rating" class="w-full p-2 border border-slate-200 rounded-xl text-xs bg-white">
                                <option value="5">5 Stars - Excellent</option>
                                <option value="4">4 Stars - Very Good</option>
                                <option value="3">3 Stars - Good</option>
                                <option value="2">2 Stars - Fair</option>
                                <option value="1">1 Star - Poor</option>
                            </select>
                            <textarea name="comment" required placeholder="Describe your experience with our care team..." class="w-full p-2 border border-slate-200 rounded-xl text-xs h-16 focus:outline-none focus:border-blue-500"></textarea>
                            <button type="submit" class="w-full bg-slate-900 hover:bg-slate-800 text-white font-bold py-2 rounded-xl transition text-xs">Submit Client Review</button>
                        </form>
                    </div>
                </div>
            </div>
        </section>

        <section id="contact" class="py-20 bg-slate-900 text-white">
            <div class="max-w-7xl mx-auto px-6">
                <div class="text-center max-w-2xl mx-auto mb-14">
                    <h2 class="text-3xl font-bold text-white">Get In Touch</h2>
                    <p class="text-slate-300 mt-3">Reach our care coordination team any time — we're on call 24/7 across Uganda.</p>
                </div>
                <div class="grid sm:grid-cols-2 lg:grid-cols-4 gap-6">
                    <a href="tel:+256753976912" class="bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl p-6 text-center transition-all">
                        <div class="w-12 h-12 rounded-xl bg-blue-500/20 text-blue-300 flex items-center justify-center mx-auto mb-4 text-xl">
                            <i class="fa-solid fa-phone"></i>
                        </div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Call Us</p>
                        <p class="font-bold text-white">+256 753 976 912</p>
                    </a>
                    <a href="https://wa.me/256708083118" target="_blank" rel="noopener" class="bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl p-6 text-center transition-all">
                        <div class="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-300 flex items-center justify-center mx-auto mb-4 text-xl">
                            <i class="fa-brands fa-whatsapp"></i>
                        </div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">WhatsApp</p>
                        <p class="font-bold text-white">+256 708 083 118</p>
                    </a>
                    <a href="mailto:carehivehomecare@gmail.com" class="bg-white/5 hover:bg-white/10 border border-white/10 rounded-2xl p-6 text-center transition-all">
                        <div class="w-12 h-12 rounded-xl bg-amber-500/20 text-amber-300 flex items-center justify-center mx-auto mb-4 text-xl">
                            <i class="fa-solid fa-envelope"></i>
                        </div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Email</p>
                        <p class="font-bold text-white break-all">carehivehomecare@gmail.com</p>
                    </a>
                    <div class="bg-white/5 border border-white/10 rounded-2xl p-6 text-center">
                        <div class="w-12 h-12 rounded-xl bg-rose-500/20 text-rose-300 flex items-center justify-center mx-auto mb-4 text-xl">
                            <i class="fa-solid fa-location-dot"></i>
                        </div>
                        <p class="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-1">Coverage Area</p>
                        <p class="font-bold text-white">Kampala & Greater Uganda</p>
                    </div>
                </div>
                <div class="text-center mt-10">
                    <button onclick="openBookingForm()" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-8 py-3.5 rounded-xl shadow-lg shadow-blue-600/20 transition-all hover:-translate-y-0.5 inline-flex items-center gap-2">
                        <i class="fa-solid fa-calendar-check"></i> Book a Care Visit Now
                    </button>
                </div>
            </div>
        </section>
    </main>

    <footer class="bg-slate-950 text-slate-400 pt-14 pb-6">
        <div class="max-w-7xl mx-auto px-6 grid sm:grid-cols-2 lg:grid-cols-4 gap-10 pb-10 border-b border-slate-800">
            <div class="space-y-3">
                <div class="flex items-center gap-2">
                    <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">CH</div>
                    <span class="text-lg font-bold text-white tracking-tight">Care<span class="text-blue-400">Hive</span></span>
                </div>
                <p class="text-sm leading-relaxed">Vetted, professional medical support and eldercare delivered directly to your family's doorstep across Uganda.</p>
            </div>
            <div>
                <h4 class="text-white font-bold text-sm uppercase tracking-wider mb-4">Quick Links</h4>
                <ul class="space-y-2 text-sm">
                    <li><a href="#services" class="hover:text-white transition-colors">Services</a></li>
                    <li><a href="#how-it-works" class="hover:text-white transition-colors">How It Works</a></li>
                    <li><a href="#reviews" class="hover:text-white transition-colors">Testimonials</a></li>
                    <li><a href="#contact" class="hover:text-white transition-colors">Contact</a></li>
                </ul>
            </div>
            <div>
                <h4 class="text-white font-bold text-sm uppercase tracking-wider mb-4">Our Services</h4>
                <ul class="space-y-2 text-sm">
                    <li><button onclick="openBookingForm('Wound Dressing')" class="hover:text-white transition-colors text-left">Professional Nursing Care</button></li>
                    <li><button onclick="openBookingForm('Elderly Care')" class="hover:text-white transition-colors text-left">Elderly & Respiratory Care</button></li>
                    <li><button onclick="openBookingForm('Baby Care')" class="hover:text-white transition-colors text-left">Pediatric & Baby Care</button></li>
                    <li><button onclick="openBookingForm('Post Surgery Care')" class="hover:text-white transition-colors text-left">Post-Surgery Support</button></li>
                </ul>
            </div>
            <div>
                <h4 class="text-white font-bold text-sm uppercase tracking-wider mb-4">Contact Us</h4>
                <ul class="space-y-3 text-sm">
                    <li><a href="tel:+256753976912" class="flex items-center gap-2 hover:text-white transition-colors"><i class="fa-solid fa-phone text-blue-400"></i> +256 753 976 912</a></li>
                    <li><a href="https://wa.me/256708083118" target="_blank" rel="noopener" class="flex items-center gap-2 hover:text-white transition-colors"><i class="fa-brands fa-whatsapp text-emerald-400"></i> +256 708 083 118</a></li>
                    <li><a href="mailto:carehivehomecare@gmail.com" class="flex items-center gap-2 hover:text-white transition-colors"><i class="fa-solid fa-envelope text-amber-400"></i> carehivehomecare@gmail.com</a></li>
                    <li class="flex items-center gap-2"><i class="fa-solid fa-location-dot text-rose-400"></i> Kampala & Greater Uganda</li>
                </ul>
            </div>
        </div>
        <div class="max-w-7xl mx-auto px-6 pt-6 flex flex-col sm:flex-row justify-between items-center gap-3 text-xs">
            <p>&copy; 2026 Carehive Homecare Limited. All rights reserved.</p>
            <p>Licensed & vetted medical homecare provider in Uganda.</p>
        </div>
    </footer>

    <section id="register-container" class="hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm overflow-y-auto p-4 flex items-center justify-center">
        <div id="register-modal-card" class="max-w-3xl w-full bg-white rounded-3xl shadow-2xl border border-slate-200 relative my-auto max-h-[90vh] overflow-y-auto transform transition-all duration-300 scale-95 opacity-0">
            <div class="relative bg-gradient-to-r from-blue-600 via-blue-600 to-indigo-600 rounded-t-3xl px-6 md:px-8 py-6 text-white overflow-hidden">
                <div class="absolute -top-8 -right-8 w-32 h-32 bg-white/10 rounded-full"></div>
                <div class="absolute -bottom-10 -left-6 w-28 h-28 bg-white/10 rounded-full"></div>
                <button onclick="closeBookingForm()" class="absolute top-4 right-4 text-white/80 hover:text-white text-xl p-2 z-10"><i class="fa-solid fa-xmark"></i></button>
                <div class="relative z-10 flex items-center gap-3">
                    <div class="w-12 h-12 rounded-2xl bg-white/15 border border-white/30 flex items-center justify-center text-2xl">
                        <i class="fa-solid fa-hand-holding-heart"></i>
                    </div>
                    <div>
                        <h2 class="text-xl md:text-2xl font-extrabold">Let's Get You Compassionate Care</h2>
                        <p class="text-blue-100 text-xs mt-0.5">Takes under a minute — a caregiver will be matched to you shortly after.</p>
                    </div>
                </div>
            </div>

            <form action="/register" method="POST" enctype="multipart/form-data" class="p-6 md:p-8 relative" onsubmit="return validateForm()">
                <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="" class="pointer-events-none select-none absolute inset-0 m-auto w-64 h-64 object-contain opacity-[0.06] z-0" onerror="this.style.display='none';">
                <div class="relative z-10 space-y-4">
                <input type="hidden" id="latitude" name="latitude">
                <input type="hidden" id="longitude" name="longitude">
                <input type="hidden" id="location" name="location">

                <div class="grid md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Your Full Name</label>
                        <input type="text" name="full_name" required placeholder="John Doe" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Valid Phone Number</label>
                        <input type="tel" name="phone" required placeholder="+256 700 000 000" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                    </div>
                </div>

                <div class="grid md:grid-cols-2 gap-4">
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Patient's Date of Birth</label>
                        <input type="date" name="patient_dob" required max="{{ today }}" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                        <p class="text-[11px] text-slate-400 mt-1">The person receiving care — helps us match the right caregiver.</p>
                    </div>
                    <div>
                        <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Patient's Gender</label>
                        <select name="gender" required class="w-full p-3 border border-slate-200 rounded-xl text-sm bg-white">
                            <option value="">-- Select --</option>
                            <option value="Female">Female</option>
                            <option value="Male">Male</option>
                            <option value="Other">Other</option>
                        </select>
                    </div>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Patient's Photo</label>
                    <input type="file" name="photo" accept="image/*" required class="w-full p-2.5 border border-slate-200 rounded-xl text-sm bg-white file:mr-3 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 file:text-xs file:font-bold">
                    <p class="text-[11px] text-slate-400 mt-1">A clear photo of the patient — not shared publicly.</p>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-2">Service Required</label>
                    <div id="service-picker" class="grid grid-cols-2 sm:grid-cols-3 gap-3">
                        <button type="button" data-service="Blood Pressure Check" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-heart-pulse text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Blood Pressure Check</span>
                        </button>
                        <button type="button" data-service="Wound Dressing" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-band-aid text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Wound Dressing</span>
                        </button>
                        <button type="button" data-service="Elderly Care" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-person-cane text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Elderly Care</span>
                        </button>
                        <button type="button" data-service="Post Surgery Care" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-user-doctor text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Post Surgery Care</span>
                        </button>
                        <button type="button" data-service="Baby Care" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-baby text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Baby & Infant Care</span>
                        </button>
                        <button type="button" data-service="Other" onclick="selectService(this)" class="service-card flex flex-col items-center justify-center gap-1.5 p-3 rounded-2xl border-2 border-slate-200 text-slate-600 bg-white text-center transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40">
                            <i class="fa-solid fa-ellipsis text-xl"></i>
                            <span class="text-xs font-bold leading-tight">Other</span>
                        </button>
                    </div>
                    <input type="hidden" id="form-service-select" name="service" required>
                    <div id="other-service-wrap" class="hidden mt-3">
                        <label class="block text-xs font-medium text-amber-700 mb-1">Please describe the care you need</label>
                        <input type="text" id="other-service-input" name="service_other_detail" placeholder="e.g. Physiotherapy support" class="w-full p-3 border border-amber-300 bg-amber-50 rounded-xl text-sm">
                        <p class="text-[11px] text-slate-400 mt-1">Our team will confirm availability for this specific service before your visit.</p>
                    </div>
                </div>

                <div class="p-4 bg-slate-50 border border-slate-200 rounded-2xl space-y-3">
                    <div class="flex justify-between items-center">
                        <label class="block text-xs font-bold text-slate-700 uppercase">
                            <i class="fa-solid fa-map-location-dot text-blue-600 mr-1"></i> Geographical Location
                        </label>
                        <button type="button" onclick="getLocation()" class="text-xs text-blue-700 hover:text-blue-900 font-bold flex items-center gap-1 bg-blue-50 px-3 py-1 rounded-lg border border-blue-200">
                            <i class="fa-solid fa-location-crosshairs"></i> Use Live GPS
                        </button>
                    </div>

                    <div id="district-selection-group" class="grid md:grid-cols-2 gap-4">
                        <div>
                            <label class="block text-xs font-medium text-slate-500 mb-1">District / City</label>
                            <select id="district-select" class="w-full p-3 border border-slate-200 rounded-xl text-sm bg-white" onchange="onDistrictChange()">
                                <option value="">-- Choose District --</option>
                            </select>
                        </div>
                        <div id="location-select-group">
                            <label class="block text-xs font-medium text-slate-500 mb-1">Sub-County / Division</label>
                            <select id="location-select" class="w-full p-3 border border-slate-200 rounded-xl text-sm bg-white" onchange="updateManualVisibility()" disabled>
                                <option value="">-- Select District First --</option>
                            </select>
                        </div>
                    </div>

                    <div id="manual-location-inputs" class="hidden grid md:grid-cols-2 gap-4">
                        <div id="manual-district-wrap" class="hidden">
                            <label class="block text-xs font-medium text-amber-700 mb-1">Type Your District / Town</label>
                            <input type="text" id="manual-district-input" placeholder="e.g. Kalungu Town" class="w-full p-3 border border-amber-300 bg-amber-50 rounded-xl text-sm">
                        </div>
                        <div id="manual-area-wrap" class="hidden">
                            <label class="block text-xs font-medium text-amber-700 mb-1">Type Your Area / Village / Landmark</label>
                            <input type="text" id="manual-area-input" placeholder="e.g. Near Total Petrol Station" class="w-full p-3 border border-amber-300 bg-amber-50 rounded-xl text-sm">
                        </div>
                    </div>
                    <p class="text-[11px] text-slate-400">Can't find your area on the list? Choose "Other" in either dropdown to type it in.</p>

                    <div id="gps-container" class="hidden">
                        <label class="block text-xs font-medium text-emerald-700 mb-1">Live Location Detected</label>
                        <input type="text" id="gps-display" readonly class="w-full p-3 border border-emerald-300 bg-emerald-50 text-emerald-900 rounded-xl font-mono text-xs font-bold">
                        <button type="button" onclick="clearGPS()" class="text-xs text-slate-500 underline mt-1 block">Clear Live Location</button>
                    </div>

                    <span id="gps-status" class="text-xs text-emerald-600 block font-semibold hidden"></span>
                </div>

                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1"><i class="fa-solid fa-calendar-check text-blue-600 mr-1"></i> Preferred Visit Date</label>
                    <input type="date" name="preferred_date" required min="{{ today }}" max="{{ max_booking_date }}" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                    <p class="text-[11px] text-slate-400 mt-1">Bookings can be scheduled up to 2 months ahead.</p>
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Additional Notes</label>
                    <textarea name="notes" placeholder="Anything our care team should know..." class="w-full p-3 border border-slate-200 rounded-xl text-sm h-20"></textarea>
                </div>
                <div class="flex gap-3 pt-2">
                    <button type="button" onclick="closeBookingForm()" class="w-1/3 bg-slate-100 text-slate-700 font-bold py-3 rounded-xl text-sm">Cancel</button>
                    <button type="submit" class="w-2/3 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3.5 rounded-xl text-sm shadow-lg shadow-blue-600/30 transition-all hover:-translate-y-0.5 flex items-center justify-center gap-2">
                        <i class="fa-solid fa-paper-plane"></i> Confirm My Booking
                    </button>
                </div>
                <p class="text-center text-[11px] text-slate-400 flex items-center justify-center gap-1.5">
                    <i class="fa-solid fa-lock text-slate-300"></i> Your details are kept private and shared only with your assigned caregiver.
                </p>
                </div>
            </form>
        </div>
    </section>

    <script>
        let ugandaGeoData = {};
        let isGpsActive = false;

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

            const otherDistrictOpt = document.createElement('option');
            otherDistrictOpt.value = '__other_district__';
            otherDistrictOpt.textContent = "Other / My District Isn't Listed";
            districtSelect.appendChild(otherDistrictOpt);
        }

        function onDistrictChange() {
            const districtSelect = document.getElementById('district-select');
            const locSelect = document.getElementById('location-select');
            const selectedDistrict = districtSelect.value;
            locSelect.innerHTML = '<option value="">-- Select Division/Sub-County --</option>';

            if (selectedDistrict && selectedDistrict !== '__other_district__' && ugandaGeoData[selectedDistrict]) {
                ugandaGeoData[selectedDistrict].locations.forEach(loc => {
                    const opt = document.createElement('option');
                    opt.value = loc;
                    opt.textContent = loc;
                    locSelect.appendChild(opt);
                });
            }

            if (selectedDistrict && selectedDistrict !== '__other_district__') {
                const otherLocOpt = document.createElement('option');
                otherLocOpt.value = '__other_location__';
                otherLocOpt.textContent = "Other / My area isn't listed (type manually)";
                locSelect.appendChild(otherLocOpt);
                locSelect.disabled = false;
            } else {
                locSelect.disabled = true;
            }
            updateManualVisibility();
        }

        function updateManualVisibility() {
            const districtSelect = document.getElementById('district-select');
            const locSelect = document.getElementById('location-select');
            const manualWrap = document.getElementById('manual-location-inputs');
            const manualDistrictWrap = document.getElementById('manual-district-wrap');
            const manualAreaWrap = document.getElementById('manual-area-wrap');

            const needDistrict = districtSelect.value === '__other_district__';
            const needArea = needDistrict || locSelect.value === '__other_location__';

            manualDistrictWrap.classList.toggle('hidden', !needDistrict);
            manualAreaWrap.classList.toggle('hidden', !needArea);
            manualWrap.classList.toggle('hidden', !(needDistrict || needArea));
        }

        function selectService(serviceOrEl) {
            const picker = document.getElementById('service-picker');
            const value = typeof serviceOrEl === 'string' ? serviceOrEl : serviceOrEl.dataset.service;
            picker.querySelectorAll('.service-card').forEach(btn => {
                const active = btn.dataset.service === value;
                btn.classList.toggle('border-blue-600', active);
                btn.classList.toggle('bg-blue-50', active);
                btn.classList.toggle('text-blue-700', active);
                btn.classList.toggle('shadow-md', active);
                btn.classList.toggle('border-slate-200', !active);
                btn.classList.toggle('text-slate-600', !active);
                btn.classList.toggle('bg-white', !active);
            });
            document.getElementById('form-service-select').value = value;
            document.getElementById('other-service-wrap').classList.toggle('hidden', value !== 'Other');
        }
        selectService('Blood Pressure Check');

        const IS_LOGGED_IN = {{ 'true' if is_logged_in else 'false' }};

        function openBookingForm(service = null, district = null) {
            if (!IS_LOGGED_IN) {
                alert("Please sign up or log in first to book a care visit.");
                window.location.href = '/login?next=' + encodeURIComponent('/');
                return;
            }
            const container = document.getElementById('register-container');
            const card = document.getElementById('register-modal-card');
            container.classList.remove('hidden');
            requestAnimationFrame(() => {
                card.classList.remove('scale-95', 'opacity-0');
                card.classList.add('scale-100', 'opacity-100');
            });
            selectService(service || 'Blood Pressure Check');
            if (district) {
                document.getElementById('district-select').value = district;
                onDistrictChange();
            }
        }

        function closeBookingForm() {
            const container = document.getElementById('register-container');
            const card = document.getElementById('register-modal-card');
            card.classList.add('scale-95', 'opacity-0');
            card.classList.remove('scale-100', 'opacity-100');
            setTimeout(() => container.classList.add('hidden'), 200);
        }

        function toggleReviewForm() {
            const wrap = document.getElementById('review-form-wrap');
            const btn = document.getElementById('review-form-toggle');
            const isHidden = wrap.classList.toggle('hidden');
            btn.innerHTML = isHidden
                ? '<i class="fa-solid fa-pen-nib"></i> Share Your Experience'
                : '<i class="fa-solid fa-xmark"></i> Close';
            if (!isHidden) wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
        }

        function handleHeroBooking() {
            openBookingForm(document.getElementById('hero-service-select').value, document.getElementById('hero-district-select').value);
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
                        document.getElementById('gps-display').value = `Live GPS Location (${lat.toFixed(5)}, ${lng.toFixed(5)})`;
                        isGpsActive = true;
                        document.getElementById('district-selection-group').classList.add('hidden');
                        document.getElementById('gps-container').classList.remove('hidden');
                        statusText.innerText = "✓ Live location detected!";
                    },
                    (error) => {
                        statusText.innerText = "Unable to retrieve location.";
                    }
                );
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
            const serviceVal = document.getElementById('form-service-select').value;
            if (serviceVal === 'Other') {
                const detail = document.getElementById('other-service-input').value.trim();
                if (!detail) {
                    alert("Please describe the care you need.");
                    return false;
                }
            }

            const locInput = document.getElementById('location');
            if (isGpsActive) {
                locInput.value = document.getElementById('gps-display').value;
                return true;
            }

            const dist = document.getElementById('district-select').value;
            let districtName = dist;
            let areaName = document.getElementById('location-select').value;

            if (dist === '__other_district__') {
                districtName = document.getElementById('manual-district-input').value.trim();
                if (!districtName) {
                    alert("Please type your District / Town name.");
                    return false;
                }
                areaName = document.getElementById('manual-area-input').value.trim();
            } else {
                if (!dist) {
                    alert("Please select a District, or choose the 'Other / My District Isn't Listed' option if yours isn't shown.");
                    return false;
                }
                if (areaName === '__other_location__') {
                    areaName = document.getElementById('manual-area-input').value.trim();
                    if (!areaName) {
                        alert("Please type your Area / Village / Landmark.");
                        return false;
                    }
                } else if (!areaName) {
                    alert("Please select your Sub-County/Division, or choose 'Other' to type it manually.");
                    return false;
                }
            }

            locInput.value = areaName ? `${areaName}, ${districtName}` : districtName;
            return true;
        }
    </script>
</body>
</html>
"""

SIGNUP_HTML = COMMON_HEAD + """
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col justify-between">
    <nav class="bg-white border-b border-slate-100 py-4 px-6 flex justify-between items-center">
        <a href="/" class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">CH</div>
            <span class="text-lg font-bold text-slate-900 tracking-tight">Care<span class="text-blue-600">Hive</span> Portal</span>
        </a>
        <a href="/" class="text-xs font-semibold text-slate-600 hover:text-blue-600">← Back Home</a>
    </nav>
    <div class="max-w-md w-full mx-auto p-6 my-8">
        <div class="bg-white p-8 rounded-3xl shadow-xl border border-slate-100 relative overflow-hidden">
            <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="" class="pointer-events-none select-none absolute inset-0 m-auto w-56 h-56 object-contain opacity-[0.06] z-0" onerror="this.style.display='none';">
            <div class="relative z-10">
            <h2 class="text-2xl font-bold text-slate-900 text-center mb-1">Client Registration</h2>
            <p class="text-xs text-slate-500 text-center mb-6">Create your Carehive account with a valid email</p>
            {% if error %} <div class="bg-red-50 text-red-700 text-xs p-3 rounded-xl mb-4 border border-red-200">{{ error }}</div> {% endif %}
            <form action="/signup" method="POST" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Full Name</label>
                    <input type="text" name="fullname" required placeholder="John Doe" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Date of Birth</label>
                    <input type="date" name="date_of_birth" required max="{{ today }}" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Valid Email Address</label>
                    <input type="email" name="email" required placeholder="name@domain.com" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Password</label>
                    <input type="password" name="password" required class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition text-sm">Register Account</button>
            </form>
            <p class="text-center mt-6 text-xs text-slate-500">Already have an account? <a href="/login" class="text-blue-600 font-bold hover:underline">Login here</a></p>
            </div>
        </div>
    </div>
    <footer class="text-center py-4 text-xs text-slate-400">© 2026 Carehive Homecare Limited</footer>
</body>
</html>
"""

LOGIN_HTML = COMMON_HEAD + """
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col justify-between">
    <nav class="bg-white border-b border-slate-100 py-4 px-6 flex justify-between items-center">
        <a href="/" class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">CH</div>
            <span class="text-lg font-bold text-slate-900 tracking-tight">Care<span class="text-blue-600">Hive</span> Portal</span>
        </a>
        <a href="/" class="text-xs font-semibold text-slate-600 hover:text-blue-600">← Back Home</a>
    </nav>
    <div class="max-w-md w-full mx-auto p-6 my-8">
        <div class="bg-white p-8 rounded-3xl shadow-xl border border-slate-100 relative overflow-hidden">
            <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="" class="pointer-events-none select-none absolute inset-0 m-auto w-56 h-56 object-contain opacity-[0.06] z-0" onerror="this.style.display='none';">
            <div class="relative z-10">
            <h2 class="text-2xl font-bold text-slate-900 text-center mb-1">Portal Login</h2>
            <p class="text-xs text-slate-500 text-center mb-6">Sign in to Client & Staff Dashboard</p>
            {% if error %} <div class="bg-red-50 text-red-700 text-xs p-3 rounded-xl mb-4 border border-red-200">{{ error }}</div> {% endif %}
            <form action="/login" method="POST" class="space-y-4">
                {% if next %}<input type="hidden" name="next" value="{{ next }}">{% endif %}
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Email Address</label>
                    <input type="email" name="email" required class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Password</label>
                    <input type="password" name="password" required class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition text-sm">Log In</button>
            </form>
            <p class="text-center mt-6 text-xs text-slate-500">Need an account? <a href="/signup" class="text-blue-600 font-bold hover:underline">Sign up</a></p>
            </div>
        </div>
    </div>
    <footer class="text-center py-4 text-xs text-slate-400">© 2026 Carehive Homecare Limited</footer>
</body>
</html>
"""

SETTINGS_HTML = COMMON_HEAD + """
<body class="bg-slate-50 text-slate-800 min-h-screen flex flex-col justify-between">
    <nav class="bg-white border-b border-slate-100 py-4 px-6 flex justify-between items-center">
        <a href="/" class="flex items-center gap-2">
            <div class="w-8 h-8 rounded-lg bg-blue-600 flex items-center justify-center text-white font-bold text-xs">CH</div>
            <span class="text-lg font-bold text-slate-900 tracking-tight">Care<span class="text-blue-600">Hive</span> Portal</span>
        </a>
        <a href="/dashboard" class="text-xs font-semibold text-slate-600 hover:text-blue-600">← Back to Dashboard</a>
    </nav>
    <div class="max-w-md w-full mx-auto p-6 my-8">
        <div class="bg-white p-8 rounded-3xl shadow-xl border border-slate-100 relative overflow-hidden">
            <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="" class="pointer-events-none select-none absolute inset-0 m-auto w-56 h-56 object-contain opacity-[0.06] z-0" onerror="this.style.display='none';">
            <div class="relative z-10">
            <h2 class="text-2xl font-bold text-slate-900 text-center mb-1"><i class="fa-solid fa-user-gear text-blue-600 mr-2"></i>Account Settings</h2>
            <p class="text-xs text-slate-500 text-center mb-6">Update your profile details and password</p>
            {% if message %} <div class="bg-emerald-50 text-emerald-800 text-xs p-3 rounded-xl mb-4 border border-emerald-200">{{ message }}</div> {% endif %}
            <form action="/settings" method="POST" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Email Address</label>
                    <input type="email" value="{{ user['email'] }}" disabled class="w-full p-3 border border-slate-200 rounded-xl text-sm bg-slate-100 text-slate-500 cursor-not-allowed">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">Full Name</label>
                    <input type="text" name="fullname" value="{{ user['fullname'] }}" required class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <div>
                    <label class="block text-xs font-semibold text-slate-600 uppercase mb-1">New Password (Optional)</label>
                    <input type="password" name="password" placeholder="••••••••" class="w-full p-3 border border-slate-200 rounded-xl text-sm">
                </div>
                <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl shadow-md transition text-sm">Save Changes</button>
            </form>
            </div>
        </div>
    </div>
    <footer class="text-center py-4 text-xs text-slate-400">© 2026 Carehive Homecare Limited</footer>
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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-100 text-slate-800">
    <div class="flex h-screen overflow-hidden">
        <div id="sidebar-backdrop" onclick="toggleSidebar(false)" class="hidden fixed inset-0 bg-slate-900/60 z-30 md:hidden"></div>

        <aside id="dashboard-sidebar" class="w-64 bg-slate-900 text-slate-300 flex flex-col justify-between fixed md:static inset-y-0 left-0 z-40 -translate-x-full md:translate-x-0 transition-transform duration-300">
            <div>
                <div class="p-6 border-b border-slate-800 flex flex-col items-center text-center gap-3 relative">
                    <button onclick="toggleSidebar(false)" class="md:hidden absolute top-3 right-3 text-slate-400 hover:text-white p-1" aria-label="Close menu">
                        <i class="fa-solid fa-xmark text-lg"></i>
                    </button>
                    <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" class="w-20 h-20 rounded-xl object-contain bg-white p-1 border" onerror="this.src='https://placehold.co/100x100?text=CH';">
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
                    {% if perms.get('view_files') %}
                    <a href="/files" class="flex items-center gap-3 px-4 py-3 hover:bg-slate-800 hover:text-white rounded-xl font-medium transition">
                        <i class="fa-solid fa-folder-open w-5 text-yellow-400"></i> Files & PDF Tickets
                    </a>
                    {% endif %}
                    <a href="/" class="flex items-center gap-3 px-4 py-3 hover:bg-slate-800 hover:text-white rounded-xl font-medium transition">
                        <i class="fa-solid fa-globe w-5 text-emerald-400"></i> Public Website
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

        <div class="flex-1 flex flex-col overflow-y-auto min-w-0">
            <header class="bg-white border-b border-slate-200 px-4 sm:px-8 py-4 flex justify-between items-center sticky top-0 z-20">
                <div class="flex items-center gap-3">
                    <button onclick="toggleSidebar(true)" class="md:hidden text-slate-600 hover:text-blue-600 p-2 -ml-2" aria-label="Open menu">
                        <i class="fa-solid fa-bars text-lg"></i>
                    </button>
                    <div>
                        <h1 class="text-xl sm:text-2xl font-bold text-slate-900">Dashboard Overview</h1>
                        <p class="text-xs text-slate-500 hidden sm:block">Welcome back, {{ session['user']['fullname'] }}</p>
                    </div>
                </div>
                <div class="flex items-center gap-2 sm:gap-4">
                    <a href="/settings" class="hidden sm:flex text-xs font-semibold text-slate-600 hover:text-blue-600 items-center gap-1.5 bg-slate-100 px-3 py-1.5 rounded-lg border">
                        <i class="fa-solid fa-gear"></i> Settings
                    </a>
                    <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold uppercase tracking-wider
                        {% if session['user']['role'] == 'admin' %} bg-purple-100 text-purple-800 border border-purple-200 {% else %} bg-blue-100 text-blue-800 border border-blue-200 {% endif %}">
                        <i class="fa-solid {% if session['user']['role'] == 'admin' %}fa-shield-halved{% else %}fa-user{% endif %}"></i>
                        {% if session['user']['role'] == 'admin' and session['user']['email'] == 'admin@carehive.com' %}Master Admin{% else %}{{ session['user']['role'] }}{% endif %}
                    </span>
                </div>
            </header>

            <main class="p-4 sm:p-8 space-y-8">
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
                <div class="grid sm:grid-cols-3 gap-4 sm:gap-6">
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

                <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
                    <h3 class="text-lg font-bold text-slate-900 mb-1"><i class="fa-solid fa-user-plus text-blue-600 mr-2"></i> Register New Worker</h3>
                    <p class="text-xs text-slate-500 mb-4">Step 1 of 2 — this just registers their account. They won't have any access until you activate them below and assign a role.</p>
                    {% if worker_form_error %}<div class="bg-red-50 text-red-700 text-xs p-3 rounded-xl mb-4 border border-red-200">{{ worker_form_error }}</div>{% endif %}
                    <form action="/admin/create-worker" method="POST" enctype="multipart/form-data" class="relative">
                        <img src="/static/images/{{ 'company-logo.jpeg'|url_encode_path }}" alt="" class="pointer-events-none select-none absolute inset-0 m-auto w-56 h-56 object-contain opacity-[0.06] z-0" onerror="this.style.display='none';">
                        <div class="relative z-10 space-y-4">
                        <div class="grid md:grid-cols-2 gap-4">
                            <input type="text" name="fullname" required placeholder="Worker Full Name" class="p-3 border border-slate-200 rounded-xl text-sm">
                            <input type="tel" name="phone" required placeholder="Phone Number" class="p-3 border border-slate-200 rounded-xl text-sm">
                            <input type="email" name="email" required placeholder="Worker Email" class="p-3 border border-slate-200 rounded-xl text-sm">
                            <input type="password" name="password" required placeholder="Default Password" class="p-3 border border-slate-200 rounded-xl text-sm">
                        </div>
                        <div class="grid md:grid-cols-2 gap-4 bg-slate-50 border border-slate-200 rounded-xl p-4">
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">NIN</label>
                                <input type="text" name="nin" required placeholder="e.g. CM12345678ABCD" pattern="^[A-Za-z]{2}[A-Za-z0-9]{12}$" title="14 characters, starts with 2 letters (e.g. CM/CF)" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">NSSF Number</label>
                                <input type="text" name="nssf_number" required placeholder="10 digit number" pattern="^[0-9]{6,12}$" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">TIN</label>
                                <input type="text" name="tin_number" required placeholder="10 digit URA TIN" pattern="^[0-9]{10}$" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">Passport Number</label>
                                <input type="text" name="passport_number" required placeholder="e.g. B1234567" pattern="^[A-Za-z0-9]{6,9}$" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">Next of Kin — Name</label>
                                <input type="text" name="next_of_kin_name" required placeholder="Full name" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div>
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">Next of Kin — Phone</label>
                                <input type="tel" name="next_of_kin_phone" required placeholder="+256 700 000 000" class="w-full p-2.5 border border-slate-200 rounded-lg text-sm">
                            </div>
                            <div class="md:col-span-2">
                                <label class="block text-xs font-bold text-slate-500 uppercase mb-1">ID Photo (face, for screening)</label>
                                <input type="file" name="id_photo" accept="image/*" required class="w-full p-2 border border-slate-200 rounded-lg text-sm bg-white file:mr-3 file:py-1 file:px-3 file:rounded-lg file:border-0 file:bg-blue-50 file:text-blue-700 file:text-xs file:font-bold">
                                <p class="text-[11px] text-slate-400 mt-1">Only checked for a valid, reasonably-sized image file. This does <strong>not</strong> detect a face or verify it matches their NIN/passport — that needs a paid identity-verification service (see note below the staff table).</p>
                            </div>
                        </div>
                        <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition text-sm">Register Worker (Pending Approval)</button>
                        </div>
                    </form>
                </div>

                <div class="bg-white rounded-2xl shadow-sm border border-amber-200 overflow-hidden">
                    <div class="p-6 border-b border-amber-100 bg-amber-50">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-hourglass-half text-amber-500 mr-2"></i> Pending Worker Registrations</h3>
                        <p class="text-xs text-slate-500 mt-1">Step 2 — pick a role and permissions to activate them, or reject the registration.</p>
                    </div>
                    <div class="divide-y divide-slate-100">
                        {% for worker in pending_workers %}
                        <div class="p-6 space-y-3">
                            <div class="flex flex-wrap items-center justify-between gap-2">
                                <div>
                                    <p class="font-bold text-slate-900">{{ worker['name'] }}</p>
                                    <p class="text-xs text-slate-500">{{ worker['email'] }}{% if worker['phone'] %} &middot; {{ worker['phone'] }}{% endif %}</p>
                                </div>
                                <span class="bg-amber-100 text-amber-800 text-xs px-2.5 py-0.5 rounded-full font-semibold">Pending</span>
                            </div>
                            <form action="/admin/activate-worker" method="POST" class="flex flex-wrap gap-4 items-center bg-slate-50 border border-slate-200 rounded-xl p-4">
                                <input type="hidden" name="email" value="{{ worker['email'] }}">
                                <span class="text-xs font-bold uppercase text-slate-500 w-full -mb-1">Assign Permissions</span>
                                <label class="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" name="perm_view_appointments" checked class="rounded"> View bookings</label>
                                <label class="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" name="perm_create_bookings" checked class="rounded"> Create bookings</label>
                                <label class="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" name="perm_view_files" checked class="rounded"> View files / PDFs</label>
                                <label class="flex items-center gap-2 text-sm text-slate-700"><input type="checkbox" name="perm_manage_staff" class="rounded"> Manage staff accounts</label>
                                <div class="flex gap-2 ml-auto">
                                    <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-4 py-2 rounded-xl text-xs">
                                        <i class="fa-solid fa-check mr-1"></i> Activate as Staff
                                    </button>
                                </div>
                            </form>
                            <form action="/admin/remove-staff" method="POST" onsubmit="return confirm('Reject and remove this registration?');">
                                <input type="hidden" name="email" value="{{ worker['email'] }}">
                                <button type="submit" class="text-xs text-red-600 hover:underline font-semibold">Reject & Remove</button>
                            </form>
                        </div>
                        {% else %}
                        <p class="p-6 text-sm text-slate-400 text-center">No pending worker registrations.</p>
                        {% endfor %}
                    </div>
                </div>

                <div class="bg-white rounded-2xl shadow-sm border border-amber-200 overflow-hidden">
                    <div class="p-6 border-b border-amber-100 bg-amber-50">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-clipboard-question text-amber-500 mr-2"></i> Pending Appointment Approvals</h3>
                        <p class="text-xs text-slate-500 mt-1">Every booking now needs review before it's confirmed. Approving schedules the visit for the date you set below.</p>
                    </div>
                    <div class="divide-y divide-slate-100">
                        {% for appt in pending_appointments %}
                        <div class="p-6 flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <p class="font-bold text-slate-900">{{ appt['full_name'] }} &middot; {{ appt['phone'] }}</p>
                                <p class="text-sm text-slate-600">{{ appt['service'] }}</p>
                                <p class="text-xs text-slate-400">Requested for {{ appt['preferred_date'] }} &middot; {{ appt['location'] }}</p>
                            </div>
                            <div class="flex flex-wrap gap-2 items-center">
                                <form action="/admin/approve-appointment" method="POST" class="flex items-center gap-2">
                                    <input type="hidden" name="appointment_id" value="{{ appt['id'] }}">
                                    <input type="date" name="confirmed_date" value="{{ appt['preferred_date'] }}" class="p-2 border border-slate-200 rounded-lg text-xs">
                                    <button type="submit" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold px-4 py-2 rounded-xl text-xs"><i class="fa-solid fa-check mr-1"></i> Approve & Schedule</button>
                                </form>
                                <form action="/admin/reject-appointment" method="POST" onsubmit="return confirm('Reject this booking request?');">
                                    <input type="hidden" name="appointment_id" value="{{ appt['id'] }}">
                                    <button type="submit" class="bg-red-50 hover:bg-red-100 text-red-600 font-bold px-4 py-2 rounded-xl text-xs border border-red-200"><i class="fa-solid fa-xmark mr-1"></i> Reject</button>
                                </form>
                            </div>
                        </div>
                        {% else %}
                        <p class="p-6 text-sm text-slate-400 text-center">No pending appointment approvals.</p>
                        {% endfor %}
                    </div>
                </div>

                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-user-nurse text-emerald-600 mr-2"></i> Staff on Duty & Permissions</h3>
                    </div>
                    <div class="overflow-x-auto">
                        <table class="w-full text-left text-sm text-slate-600">
                            <thead class="bg-slate-50 text-xs font-semibold uppercase text-slate-400 border-b">
                                <tr>
                                    <th class="p-4">Name / Phone</th>
                                    <th class="p-4">Email</th>
                                    <th class="p-4">Role</th>
                                    <th class="p-4">On Duty</th>
                                    <th class="p-4">Permissions</th>
                                    <th class="p-4"></th>
                                </tr>
                            </thead>
                            <tbody class="divide-y divide-slate-100">
                                {% for staff in staff_members %}
                                <tr>
                                    <td class="p-4 font-medium text-slate-900">
                                        {{ staff['name'] }}
                                        {% if staff['email'] != 'admin@carehive.com' %}
                                        <form action="/admin/edit-staff" method="POST" class="flex items-center gap-1.5 mt-1">
                                            <input type="hidden" name="email" value="{{ staff['email'] }}">
                                            <input type="tel" name="phone" value="{{ staff['phone'] or '' }}" placeholder="Phone" class="p-1.5 border border-slate-200 rounded-lg text-xs w-32 font-normal">
                                            <button type="submit" class="text-[11px] text-blue-600 hover:underline font-semibold">Save</button>
                                        </form>
                                        {% endif %}
                                    </td>
                                    <td class="p-4">{{ staff['email'] }}</td>
                                    <td class="p-4">
                                        {% if staff['email'] == 'admin@carehive.com' %}
                                        <span class="bg-amber-100 text-amber-800 text-xs px-2.5 py-0.5 rounded-full font-semibold">Master Admin</span>
                                        {% else %}
                                        <span class="bg-purple-100 text-purple-800 text-xs px-2.5 py-0.5 rounded-full font-semibold">{{ staff['role'] }}</span>
                                        {% endif %}
                                    </td>
                                    <td class="p-4">
                                        {% if staff['email'] == 'admin@carehive.com' %}
                                        <span class="text-slate-300 italic text-xs">&mdash;</span>
                                        {% else %}
                                        <form action="/admin/toggle-duty" method="POST">
                                            <input type="hidden" name="email" value="{{ staff['email'] }}">
                                            <label class="inline-flex items-center gap-1.5 cursor-pointer">
                                                <input type="checkbox" name="on_duty" onchange="this.form.requestSubmit()" {% if staff['on_duty'] %}checked{% endif %} class="rounded">
                                                {% if staff['on_duty'] %}
                                                <span class="bg-emerald-100 text-emerald-800 text-xs px-2 py-0.5 rounded-full font-semibold">On Duty</span>
                                                {% else %}
                                                <span class="text-slate-400 text-xs">Off duty</span>
                                                {% endif %}
                                            </label>
                                        </form>
                                        {% endif %}
                                    </td>
                                    <td class="p-4 text-xs">
                                        {% if staff['email'] == 'admin@carehive.com' %}
                                        <span class="text-slate-400 italic">Full access (fixed)</span>
                                        {% else %}
                                        <form action="/admin/update-permissions" method="POST" class="flex flex-wrap gap-3 items-center">
                                            <input type="hidden" name="email" value="{{ staff['email'] }}">
                                            <label class="flex items-center gap-1"><input type="checkbox" name="perm_view_appointments" onchange="this.form.requestSubmit()" {% if staff['permissions']['view_appointments'] %}checked{% endif %}> Bookings</label>
                                            <label class="flex items-center gap-1"><input type="checkbox" name="perm_create_bookings" onchange="this.form.requestSubmit()" {% if staff['permissions']['create_bookings'] %}checked{% endif %}> Create</label>
                                            <label class="flex items-center gap-1"><input type="checkbox" name="perm_view_files" onchange="this.form.requestSubmit()" {% if staff['permissions']['view_files'] %}checked{% endif %}> Files</label>
                                            <label class="flex items-center gap-1"><input type="checkbox" name="perm_manage_staff" onchange="this.form.requestSubmit()" {% if staff['permissions']['manage_staff'] %}checked{% endif %}> Manage staff</label>
                                        </form>
                                        {% endif %}
                                    </td>
                                    <td class="p-4 space-y-1">
                                        <button type="button" onclick="openStaffLogModal('{{ staff['email'] }}', '{{ staff['name'] }}')" class="text-xs text-indigo-600 hover:underline font-semibold block">View Full Log</button>
                                        {% if staff['email'] != 'admin@carehive.com' %}
                                        <form action="/admin/remove-staff" method="POST" onsubmit="return confirm('Remove this account?');">
                                            <input type="hidden" name="email" value="{{ staff['email'] }}">
                                            <button type="submit" class="text-xs text-red-600 hover:underline font-semibold">Remove</button>
                                        </form>
                                        {% endif %}
                                    </td>
                                </tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                    <p class="text-[11px] text-slate-400 p-4 border-t border-slate-100">
                        <i class="fa-solid fa-circle-info mr-1"></i> NIN/NSSF/TIN/passport numbers are format-checked only, and ID photos are screened for a detectable face —
                        neither confirms a worker's identity against government records. Real ID verification needs a paid KYC/identity-verification API
                        (e.g. Smile Identity, Onfido) wired in with your own account credentials.
                    </p>
                </div>

                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200 flex flex-wrap items-center justify-between gap-3">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-list-check text-indigo-600 mr-2"></i> Activity Audit Logs</h3>
                        <form method="GET" action="/dashboard" class="flex items-center gap-2">
                            <label class="text-xs font-semibold text-slate-500">Filter by staff:</label>
                            <select name="staff_log" onchange="this.form.requestSubmit()" class="text-xs p-2 border border-slate-200 rounded-lg bg-white">
                                <option value="">All Staff (recent activity)</option>
                                {% for staff in staff_members %}
                                <option value="{{ staff['email'] }}" {% if staff_log_filter == staff['email'] %}selected{% endif %}>{{ staff['name'] }} ({{ staff['email'] }})</option>
                                {% endfor %}
                            </select>
                        </form>
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
                                {% else %}
                                <tr><td colspan="3" class="p-6 text-center text-slate-400">No activity recorded for this staff member yet.</td></tr>
                                {% endfor %}
                            </tbody>
                        </table>
                    </div>
                </div>

                <script>
                    const chartData = {{ chart_data|tojson|safe }};
                    const palette = ['#2c7be5', '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6'];

                    if (chartData.appointments_trend && chartData.appointments_trend.values.length) {
                        new Chart(document.getElementById('trendChart'), {
                            type: 'line',
                            data: {
                                labels: chartData.appointments_trend.labels,
                                datasets: [{
                                    data: chartData.appointments_trend.values,
                                    borderColor: '#2c7be5',
                                    backgroundColor: 'rgba(44,123,229,0.1)',
                                    tension: 0.35,
                                    fill: true
                                }]
                            },
                            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
                        });
                    }

                    if (chartData.reviews_by_rating && chartData.reviews_by_rating.values.length) {
                        new Chart(document.getElementById('ratingChart'), {
                            type: 'doughnut',
                            data: {
                                labels: chartData.reviews_by_rating.labels.map(r => r + ' ★'),
                                datasets: [{ data: chartData.reviews_by_rating.values, backgroundColor: palette }]
                            },
                            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } } }
                        });
                    }

                    if (chartData.appointments_by_service && chartData.appointments_by_service.values.length) {
                        new Chart(document.getElementById('serviceChart'), {
                            type: 'doughnut',
                            data: {
                                labels: chartData.appointments_by_service.labels,
                                datasets: [{ data: chartData.appointments_by_service.values, backgroundColor: palette }]
                            },
                            options: { plugins: { legend: { position: 'bottom', labels: { boxWidth: 12, font: { size: 10 } } } } }
                        });
                    }

                    if (chartData.appointments_by_location && chartData.appointments_by_location.values.length) {
                        new Chart(document.getElementById('locationChart'), {
                            type: 'bar',
                            data: {
                                labels: chartData.appointments_by_location.labels,
                                datasets: [{ data: chartData.appointments_by_location.values, backgroundColor: '#10b981', borderRadius: 6 }]
                            },
                            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true } } }
                        });
                    }

                    if (chartData.users_by_role && chartData.users_by_role.values.length) {
                        new Chart(document.getElementById('roleChart'), {
                            type: 'bar',
                            data: {
                                labels: chartData.users_by_role.labels,
                                datasets: [{ data: chartData.users_by_role.values, backgroundColor: '#8b5cf6', borderRadius: 6 }]
                            },
                            options: { indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { beginAtZero: true } } }
                        });
                    }
                </script>
                {% else %}
                <div class="grid md:grid-cols-3 gap-6">
                    <div class="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 md:col-span-2">
                        <h2 class="text-2xl font-bold text-slate-900 mb-2">Welcome to Your Carehive Portal</h2>
                        <p class="text-slate-600 text-sm mb-6">Manage your home healthcare requests, update your profile details, or book new care visits.</p>
                        <div class="flex flex-wrap gap-4">
                            <a href="/#services" class="bg-blue-600 hover:bg-blue-700 text-white font-bold px-6 py-3 rounded-xl shadow transition text-sm">
                                Book Care Visit
                            </a>
                            <a href="/settings" class="bg-slate-100 hover:bg-slate-200 text-slate-700 font-bold px-6 py-3 rounded-xl border transition text-sm">
                                Account Settings
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

                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-calendar-check text-blue-600 mr-2"></i> My Appointments</h3>
                    </div>
                    <div class="divide-y divide-slate-100">
                        {% for appt in my_appointments %}
                        <div class="p-6 flex flex-wrap items-center justify-between gap-3">
                            <div>
                                <p class="font-bold text-slate-900">{{ appt['service'] }}</p>
                                <p class="text-xs text-slate-400">{{ appt['preferred_date'] }} &middot; {{ appt['location'] }} &middot; Ref: {{ appt['reference'] or 'pending' }}</p>
                            </div>
                            {% if appt['approval_status'] == 'approved' %}
                            <span class="bg-emerald-100 text-emerald-800 text-xs px-3 py-1 rounded-full font-semibold">Approved & Scheduled</span>
                            {% elif appt['approval_status'] == 'rejected' %}
                            <span class="bg-red-100 text-red-700 text-xs px-3 py-1 rounded-full font-semibold">Not Approved</span>
                            {% else %}
                            <span class="bg-amber-100 text-amber-800 text-xs px-3 py-1 rounded-full font-semibold">Pending Approval</span>
                            {% endif %}
                        </div>
                        {% else %}
                        <p class="p-6 text-sm text-slate-400 text-center">You haven't booked any appointments yet.</p>
                        {% endfor %}
                    </div>
                </div>

                <div class="bg-white rounded-2xl shadow-sm border border-slate-200 overflow-hidden">
                    <div class="p-6 border-b border-slate-200">
                        <h3 class="font-bold text-slate-900"><i class="fa-solid fa-clock-rotate-left text-blue-600 mr-2"></i> Recent Account Activity</h3>
                    </div>
                    <div class="p-6">
                        <ul class="divide-y divide-slate-100 text-sm">
                            {% for log in logs %}
                            <li class="py-3 flex justify-between items-center">
                                <span class="font-medium text-slate-800">{{ log['action'] }}</span>
                                <span class="text-xs font-mono text-slate-400">{{ log['timestamp'] }}</span>
                            </li>
                            {% endfor %}
                        </ul>
                    </div>
                </div>
                {% endif %}
            </main>
        </div>
    </div>

    <div id="action-toast" class="hidden fixed top-6 right-6 z-[70] bg-slate-900 text-white px-5 py-3.5 rounded-2xl shadow-2xl flex items-center gap-3 max-w-sm">
        <i class="fa-solid fa-circle-check text-emerald-400 text-lg"></i>
        <span id="action-toast-text" class="text-sm font-medium"></span>
    </div>

    <div id="staff-log-modal" class="hidden fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-center justify-center p-4">
        <div class="max-w-2xl w-full bg-white rounded-3xl shadow-2xl border border-slate-200 max-h-[85vh] flex flex-col overflow-hidden">
            <div class="p-6 border-b border-slate-200 flex items-center justify-between gap-3">
                <div>
                    <h3 id="staff-log-modal-name" class="font-bold text-slate-900 text-lg"></h3>
                    <p id="staff-log-modal-email" class="text-xs text-slate-400 font-mono"></p>
                </div>
                <div class="flex items-center gap-3">
                    <a id="staff-log-download-link" href="#" class="text-xs font-bold text-blue-600 hover:underline flex items-center gap-1"><i class="fa-solid fa-download"></i> Download CSV</a>
                    <button type="button" onclick="closeStaffLogModal()" class="text-slate-400 hover:text-slate-700 text-xl"><i class="fa-solid fa-xmark"></i></button>
                </div>
            </div>
            <div id="staff-log-modal-body" class="overflow-y-auto p-6 space-y-2 text-sm text-slate-600">
                <p class="text-center text-slate-400">Loading...</p>
            </div>
        </div>
    </div>

    <script>
        const TOAST_MESSAGE = {{ toast_message|tojson }};
        if (TOAST_MESSAGE) {
            const toast = document.getElementById('action-toast');
            document.getElementById('action-toast-text').textContent = TOAST_MESSAGE;
            toast.classList.remove('hidden');
            setTimeout(() => toast.classList.add('hidden'), 4000);
            const url = new URL(window.location);
            url.searchParams.delete('toast');
            window.history.replaceState({}, '', url);
        }

        function toggleSidebar(open) {
            const sidebar = document.getElementById('dashboard-sidebar');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (open) {
                sidebar.classList.remove('-translate-x-full');
                backdrop.classList.remove('hidden');
            } else {
                sidebar.classList.add('-translate-x-full');
                backdrop.classList.add('hidden');
            }
        }

        function openStaffLogModal(email, name) {
            document.getElementById('staff-log-modal').classList.remove('hidden');
            document.getElementById('staff-log-modal-name').textContent = name + "'s Activity Log";
            document.getElementById('staff-log-modal-email').textContent = email;
            document.getElementById('staff-log-download-link').href = '/admin/staff-log/' + encodeURIComponent(email) + '/download';
            const body = document.getElementById('staff-log-modal-body');
            body.innerHTML = '<p class="text-center text-slate-400">Loading...</p>';

            fetch('/admin/staff-log/' + encodeURIComponent(email))
                .then(res => res.json())
                .then(data => {
                    if (!data.logs || data.logs.length === 0) {
                        body.innerHTML = '<p class="text-center text-slate-400">No activity recorded for this staff member yet.</p>';
                        return;
                    }
                    body.innerHTML = data.logs.map(log => `
                        <div class="flex items-center justify-between p-3 bg-slate-50 rounded-xl border border-slate-100">
                            <span class="font-medium text-slate-700">${log.action}</span>
                            <span class="text-xs font-mono text-slate-400 shrink-0 ml-3">${log.timestamp}</span>
                        </div>
                    `).join('');
                })
                .catch(() => {
                    body.innerHTML = '<p class="text-center text-red-500">Couldn\'t load activity log.</p>';
                });
        }

        function closeStaffLogModal() {
            document.getElementById('staff-log-modal').classList.add('hidden');
        }
    </script>
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
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
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
                        <th class="p-4">Reference</th>
                        <th class="p-4">Client Name</th>
                        <th class="p-4">Phone</th>
                        <th class="p-4">Service</th>
                        <th class="p-4">Location & GPS Pin</th>
                        <th class="p-4">Preferred Date</th>
                        <th class="p-4">Notes</th>
                        <th class="p-4">Ticket</th>
                    </tr>
                </thead>
                <tbody class="divide-y">
                    {% for appt in appointments %}
                    <tr>
                        <td class="p-4 font-mono text-xs font-bold text-blue-700">{{ appt['reference'] or '—' }}</td>
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
                        <td class="p-4">
                            {% if appt['reference'] %}
                            <a href="/ticket/{{ appt['reference'] }}" target="_blank" class="text-xs font-semibold text-blue-600 hover:underline"><i class="fa-solid fa-file-pdf mr-1"></i>PDF</a>
                            {% endif %}
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""

FILES_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Files | Carehive Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <style> body { font-family: 'Inter', sans-serif; } </style>
</head>
<body class="bg-slate-100 text-slate-800">
    <div class="max-w-5xl mx-auto p-8">
        <div class="flex justify-between items-center mb-8">
            <div>
                <h1 class="text-3xl font-bold text-slate-900">Files</h1>
                <p class="text-sm text-slate-500">Every generated booking PDF ticket, with its barcode and reference.</p>
            </div>
            <a href="/dashboard" class="bg-slate-800 text-white px-4 py-2 rounded-xl text-sm font-semibold hover:bg-slate-900">← Back to Dashboard</a>
        </div>
        <div class="bg-white rounded-2xl shadow border border-slate-200 overflow-hidden">
            <table class="w-full text-left text-sm text-slate-600">
                <thead class="bg-slate-50 text-xs uppercase font-semibold text-slate-400 border-b">
                    <tr>
                        <th class="p-4">File</th>
                        <th class="p-4">Reference</th>
                        <th class="p-4">Customer</th>
                        <th class="p-4">Created</th>
                        <th class="p-4"></th>
                    </tr>
                </thead>
                <tbody class="divide-y">
                    {% for f in files %}
                    <tr>
                        <td class="p-4 font-medium text-slate-900">{{ f['reference'] }}.pdf</td>
                        <td class="p-4 font-mono text-xs text-blue-700">{{ f['reference'] }}</td>
                        <td class="p-4">{{ f['full_name'] }}</td>
                        <td class="p-4 text-xs font-mono">{{ f['created_at'] }}</td>
                        <td class="p-4">
                            <a href="/ticket/{{ f['reference'] }}" target="_blank" class="text-xs font-semibold text-blue-600 hover:underline mr-3"><i class="fa-solid fa-eye mr-1"></i>View</a>
                            <a href="/ticket/{{ f['reference'] }}?download=1" class="text-xs font-semibold text-emerald-600 hover:underline"><i class="fa-solid fa-download mr-1"></i>Download</a>
                        </td>
                    </tr>
                    {% else %}
                    <tr><td colspan="5" class="p-8 text-center text-slate-400">No files yet — these are created automatically whenever someone books an appointment.</td></tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</body>
</html>
"""


# ---------------------------------------------------------
# Booking reference / barcode / PDF generation helpers
# ---------------------------------------------------------
import random
import string
import io
from reportlab.pdfgen import canvas as pdfcanvas
from reportlab.lib.pagesizes import A6
from reportlab.graphics.barcode import code128


def screen_photo_has_face(photo_bytes: bytes):
    """Sanity-screens uploaded photos before they're stored.

    IMPORTANT: this only verifies the upload is a genuine, reasonably-sized
    photo (not a corrupted file, a tiny placeholder, or some other document
    type). It does NOT detect whether a human face is actually in it — real
    face detection needs either a bundled ML model (the OpenCV Haar Cascade
    approach was tried, but the installed opencv-python-headless 5.0
    pre-release dropped cv2.CascadeClassifier in favor of a DNN detector
    that requires an external .onnx model file not available here) or a
    paid cloud vision API (AWS Rekognition, Azure Face, etc). Rejecting
    obviously-wrong uploads is still useful even without true face
    detection, so this stays as a real (lesser) safeguard rather than a
    no-op. Imports PIL lazily so a missing install only disables this one
    check rather than crashing the whole app at startup.
    """
    try:
        from PIL import Image
    except ImportError:
        return True, "Photo screening unavailable (Pillow not installed) — accepted without screening."

    try:
        img = Image.open(io.BytesIO(photo_bytes))
        img.verify()
        img = Image.open(io.BytesIO(photo_bytes))  # verify() consumes the parser; reopen to inspect
        width, height = img.size
        if width < 80 or height < 80:
            return False, "That image is too small to be a usable photo. Please upload a clearer picture."
        if img.format not in ('JPEG', 'PNG', 'WEBP'):
            return False, "Please upload a JPEG, PNG, or WEBP photo."
        return True, "OK"
    except Exception:
        return False, "That file doesn't look like a valid photo. Please try a different image."


def generate_reference(appointment_id: int) -> str:
    """Generates a unique, human-readable booking reference."""
    rand_suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
    return f"CH-{appointment_id:05d}-{rand_suffix}"


def build_ticket_pdf(appointment: dict) -> io.BytesIO:
    """
    Builds a PDF ticket containing the booking details and a Code128 barcode
    encoding the reference number, entirely in memory (no disk writes — the
    production filesystem is read-only, and the ticket is fully derivable
    from the appointment record, so nothing needs to persist as a file).
    """
    reference = appointment['reference']
    buffer = io.BytesIO()

    width, height = A6  # small ticket-sized page
    c = pdfcanvas.Canvas(buffer, pagesize=A6)

    # Header band
    c.setFillColorRGB(0.09, 0.13, 0.17)
    c.rect(0, height - 60, width, 60, fill=1, stroke=0)
    c.setFillColorRGB(1, 1, 1)
    c.setFont('Helvetica-Bold', 14)
    c.drawString(16, height - 38, "Carehive Homecare Limited")
    c.setFont('Helvetica', 8)
    status = (appointment.get('approval_status') or 'pending').capitalize()
    c.drawString(16, height - 52, f"Booking Request — Status: {status}")

    # Body details
    c.setFillColorRGB(0.1, 0.1, 0.1)
    y = height - 85
    line_height = 16

    def draw_line(label, value):
        nonlocal y
        c.setFont('Helvetica-Bold', 8.5)
        c.drawString(16, y, label)
        c.setFont('Helvetica', 8.5)
        c.drawString(95, y, str(value) if value else '-')
        y -= line_height

    draw_line("Reference:", reference)
    draw_line("Status:", status)
    draw_line("Customer:", appointment['full_name'])
    draw_line("Phone:", appointment['phone'])
    draw_line("Service:", appointment['service'])
    draw_line("Date:", appointment['preferred_date'])
    draw_line("Location:", appointment['location'])
    if appointment.get('patient_dob'):
        draw_line("Patient DOB:", appointment['patient_dob'])
    if appointment.get('notes'):
        draw_line("Notes:", appointment['notes'][:60])

    # Barcode (Code128) encoding the reference number
    barcode = code128.Code128(reference, barHeight=16 * 2.834, barWidth=0.9)
    barcode_x = (width - barcode.width) / 2
    barcode_y = 34
    barcode.drawOn(c, barcode_x, barcode_y)

    c.setFont('Helvetica', 7)
    c.drawCentredString(width / 2, 20, reference)

    c.showPage()
    c.save()
    buffer.seek(0)
    return buffer


def create_booking_ticket(appointment_id: int, appointment_row) -> str:
    """Generates and stores the reference for a newly created appointment.
    The PDF itself is built on-demand when /ticket/<reference> is visited."""
    reference = generate_reference(appointment_id)

    conn = get_db_connection()
    conn.execute('UPDATE appointments SET reference = ? WHERE id = ?', (reference, appointment_id))
    conn.commit()
    conn.close()
    return reference


# ---------------------------------------------------------
# Permissions helpers
# ---------------------------------------------------------
import json

DEFAULT_STAFF_PERMISSIONS = {
    "view_appointments": True,
    "create_bookings": True,
    "view_files": True,
    "manage_staff": False,
}


def get_permissions_for_session_user():
    """Returns the effective permissions dict for the currently logged-in user."""
    if 'user' not in session:
        return {}
    if session['user']['role'] == 'admin':
        return {"view_appointments": True, "create_bookings": True, "view_files": True, "manage_staff": True}
    conn = get_db_connection()
    row = conn.execute('SELECT permissions FROM users WHERE email = ?', (session['user']['email'],)).fetchone()
    conn.close()
    if row and row['permissions']:
        try:
            return json.loads(row['permissions'])
        except (ValueError, TypeError):
            return dict(DEFAULT_STAFF_PERMISSIONS)
    return dict(DEFAULT_STAFF_PERMISSIONS)


def require_permission(key):
    """Returns True if the logged-in user is allowed to use a feature gated by `key`."""
    if 'user' not in session:
        return False
    if session['user']['role'] == 'admin':
        return True
    return get_permissions_for_session_user().get(key, False)


# ---------------------------------------------------------
# Application Routes
# ---------------------------------------------------------
@app.before_request
def update_last_active():
    if 'user' in session:
        email = session['user']['email']
        now = datetime.now(timezone.utc)
        if email not in USER_STATUS:
            USER_STATUS[email] = {'login_time': now, 'last_active': now, 'status': 'Active Online'}
        else:
            USER_STATUS[email]['last_active'] = now


@app.route('/api/uganda-geo')
def get_uganda_geo():
    return jsonify(uganda_geo.to_dict())


@app.route('/')
def home():
    conn = get_db_connection()
    reviews = conn.execute('SELECT * FROM reviews ORDER BY id DESC').fetchall()
    avg_rating_row = conn.execute('SELECT AVG(rating) AS avg_rating FROM reviews').fetchone()
    on_duty_count = conn.execute(
        "SELECT COUNT(*) AS cnt FROM users WHERE on_duty = 1 AND role IN ('admin', 'staff')"
    ).fetchone()['cnt']
    conn.close()

    booking_reference = request.args.get('ref')
    booking_error = request.args.get('error')
    today_dt = datetime.now(timezone.utc)
    today = today_dt.strftime('%Y-%m-%d')
    max_booking_date = (today_dt + timedelta(days=60)).strftime('%Y-%m-%d')
    site_stats = {
        'avg_rating': round(avg_rating_row['avg_rating'], 1) if avg_rating_row['avg_rating'] else 5.0,
        'district_count': len(uganda_geo.districts),
        'on_duty_count': on_duty_count,
    }
    return render_template_string(
        INDEX_HTML, reviews=reviews, booking_reference=booking_reference, booking_error=booking_error,
        today=today, max_booking_date=max_booking_date, site_stats=site_stats,
        is_logged_in=bool(session.get('user'))
    )


@app.route('/register', methods=['POST'])
def register_appointment():
    # Booking requires an account so every appointment is tied to a real,
    # authenticated client — anonymous bookings are no longer accepted.
    if 'user' not in session:
        return redirect(url_for('login', next='/'))

    today_str = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    max_date_str = (datetime.now(timezone.utc) + timedelta(days=60)).strftime('%Y-%m-%d')
    preferred_date = request.form.get('preferred_date', '').strip()
    if not (today_str <= preferred_date <= max_date_str):
        return redirect(url_for('home', error="Please choose a visit date between today and 2 months from now."))

    service = request.form.get('service', '').strip()
    if service == 'Other':
        other_detail = request.form.get('service_other_detail', '').strip()
        if not other_detail:
            return redirect(url_for('home', error="Please describe the care you need for an 'Other' service request."))
        service = f"Other: {other_detail}"

    # Every booking now needs admin review before it's confirmed/scheduled —
    # not just "Other" service requests. This lets the admin (or whoever is
    # in charge of forms) confirm the actual visit date as part of approval.
    approval_status = 'pending'

    photo_file = request.files.get('photo')
    if not photo_file or not photo_file.filename:
        return redirect(url_for('home', error="Please upload a photo of the patient."))
    photo_bytes = photo_file.read()
    if len(photo_bytes) > 5 * 1024 * 1024:
        return redirect(url_for('home', error="That photo is too large — please use one under 5MB."))
    photo_ok, photo_reason = screen_photo_has_face(photo_bytes)
    if not photo_ok:
        return redirect(url_for('home', error=photo_reason))

    conn = get_db_connection()
    lat = request.form.get('latitude')
    lng = request.form.get('longitude')

    cursor = conn.cursor()
    cursor.execute(
        '''INSERT INTO appointments
           (full_name, phone, service, location, latitude, longitude, preferred_date, notes,
            patient_dob, gender, photo, approval_status, booked_by_email)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (
            request.form.get('full_name', '').strip(),
            request.form.get('phone', '').strip(),
            service,
            request.form.get('location', '').strip(),
            float(lat) if lat else None,
            float(lng) if lng else None,
            preferred_date,
            request.form.get('notes', '').strip(),
            request.form.get('patient_dob', '').strip(),
            request.form.get('gender', '').strip(),
            psycopg2.Binary(photo_bytes),
            approval_status,
            session['user']['email'],
        )
    )
    appointment_id = cursor.lastrowid
    conn.commit()

    appointment_row = conn.execute('SELECT * FROM appointments WHERE id = ?', (appointment_id,)).fetchone()
    conn.close()

    reference = create_booking_ticket(appointment_id, appointment_row)
    log_activity(session['user']['email'], f"New booking created — reference {reference}")

    return redirect(url_for('home', ref=reference))


@app.route('/ticket/<reference>')
def view_ticket(reference):
    """Builds and serves the PDF ticket for a booking on demand from its
    stored appointment record, entirely in memory."""
    from flask import send_file, abort
    safe_reference = ''.join(c for c in reference if c.isalnum() or c in '-_')

    conn = get_db_connection()
    appointment_row = conn.execute(
        'SELECT * FROM appointments WHERE reference = ?', (safe_reference,)
    ).fetchone()
    conn.close()

    if not appointment_row:
        abort(404, description="Ticket not found.")

    buffer = build_ticket_pdf(dict(appointment_row))
    as_attachment = request.args.get('download') == '1'
    return send_file(buffer, mimetype='application/pdf', as_attachment=as_attachment,
                      download_name=f"{safe_reference}.pdf")


@app.route('/files')
def files_list():
    if 'user' not in session:
        return redirect(url_for('login'))
    if not require_permission('view_files'):
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    files = conn.execute(
        "SELECT reference, full_name, created_at FROM appointments WHERE reference IS NOT NULL ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return render_template_string(FILES_HTML, files=files)


@app.route('/review', methods=['POST'])
def add_review():
    try:
        rating = int(request.form.get('rating', 5))
    except ValueError:
        rating = 5

    conn = get_db_connection()
    conn.execute(
        'INSERT INTO reviews (client_name, rating, comment) VALUES (?, ?, ?)',
        (
            request.form.get('client_name', '').strip(),
            rating,
            request.form.get('comment', '').strip()
        )
    )
    conn.commit()
    conn.close()
    return redirect(url_for('home'))


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        fullname = request.form.get('fullname', '').strip()
        password = request.form.get('password', '')
        date_of_birth = request.form.get('date_of_birth', '').strip()

        if not email or not fullname or not password or not date_of_birth:
            return render_template_string(SIGNUP_HTML, error="All fields are required.", today=today)

        if date_of_birth > today:
            return render_template_string(SIGNUP_HTML, error="Date of birth cannot be in the future.", today=today)

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT email FROM users WHERE email = ?', (email,))
        if cursor.fetchone():
            conn.close()
            return render_template_string(SIGNUP_HTML, error="Email already registered.", today=today)

        hashed_pw = generate_password_hash(password)
        cursor.execute(
            'INSERT INTO users (email, name, role, password, date_of_birth) VALUES (?, ?, ?, ?, ?)',
            (email, fullname, 'client', hashed_pw, date_of_birth)
        )
        conn.commit()
        conn.close()

        log_activity(email, "Registered new client account")
        session['user'] = {'email': email, 'fullname': fullname, 'role': 'client'}
        USER_STATUS[email] = {'login_time': datetime.now(timezone.utc), 'last_active': datetime.now(timezone.utc), 'status': 'Active Online'}
        return redirect(url_for('dashboard'))

    return render_template_string(SIGNUP_HTML, today=today)


MAX_LOGIN_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15


@app.route('/login', methods=['GET', 'POST'])
def login():
    next_url = request.values.get('next', '')
    safe_next = next_url if next_url.startswith('/') and not next_url.startswith('//') else None

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
        user = cursor.fetchone()

        if user and user['locked_until'] and str(user['locked_until']) > datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S'):
            conn.close()
            return render_template_string(
                LOGIN_HTML, next=safe_next,
                error=f"Too many failed attempts. This account is locked for a few minutes — please try again shortly."
            )

        if user and check_password_hash(user['password'], password):
            cursor.execute('UPDATE users SET failed_login_count = 0, locked_until = NULL WHERE email = ?', (email,))
            conn.commit()
            conn.close()

            if user['role'] == 'pending':
                return render_template_string(LOGIN_HTML, next=safe_next, error="Your registration is pending admin approval. Please check back once you've been activated.")

            session['user'] = {'email': user['email'], 'fullname': user['name'], 'role': user['role']}
            USER_STATUS[email] = {'login_time': datetime.now(timezone.utc), 'last_active': datetime.now(timezone.utc), 'status': 'Active Online'}
            log_activity(email, f"Logged in as {user['role']}")
            return redirect(safe_next or url_for('dashboard'))

        if user:
            attempts = (user['failed_login_count'] or 0) + 1
            if attempts >= MAX_LOGIN_ATTEMPTS:
                locked_until = datetime.now(timezone.utc) + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
                cursor.execute('UPDATE users SET failed_login_count = ?, locked_until = ? WHERE email = ?', (attempts, locked_until, email))
                log_activity(email, f"Account locked after {attempts} failed login attempts")
            else:
                cursor.execute('UPDATE users SET failed_login_count = ? WHERE email = ?', (attempts, email))
            conn.commit()
        conn.close()

        return render_template_string(LOGIN_HTML, next=safe_next, error="Invalid email or password.")

    return render_template_string(LOGIN_HTML, next=safe_next)


@app.route('/logout')
def logout():
    if 'user' in session:
        email = session['user']['email']
        log_activity(email, "Logged out of portal")
        USER_STATUS[email] = {'status': 'Logged Out'}
        session.pop('user', None)
    return redirect(url_for('home'))


@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if 'user' not in session:
        return redirect(url_for('login'))

    email = session['user']['email']
    conn = get_db_connection()
    message = None

    if request.method == 'POST':
        fullname = request.form.get('fullname', '').strip()
        new_password = request.form.get('password', '')

        cursor = conn.cursor()
        if new_password:
            hashed_pw = generate_password_hash(new_password)
            cursor.execute('UPDATE users SET name = ?, password = ? WHERE email = ?', (fullname, hashed_pw, email))
        else:
            cursor.execute('UPDATE users SET name = ? WHERE email = ?', (fullname, email))
        conn.commit()

        session['user']['fullname'] = fullname
        log_activity(email, "Updated account settings")
        message = "Account settings successfully updated!"

    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE email = ?', (email,))
    db_user = cursor.fetchone()
    conn.close()

    user_data = {'email': db_user['email'], 'fullname': db_user['name']}
    return render_template_string(SETTINGS_HTML, user=user_data, message=message)


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))

    email = session['user']['email']
    activity = get_user_activity_info(email)
    perms = get_permissions_for_session_user()
    worker_form_error = request.args.get('worker_error')
    toast_message = request.args.get('toast')

    conn = get_db_connection()
    cursor = conn.cursor()

    stats = {}
    chart_data = {}
    logs = []
    staff_members = []
    pending_workers = []
    pending_appointments = []
    my_appointments = []
    staff_log_filter = ''

    if session['user']['role'] == 'admin':
        cursor.execute('SELECT COUNT(*) AS cnt FROM appointments')
        stats['appointments'] = cursor.fetchone()['cnt']

        cursor.execute('SELECT COUNT(*) AS cnt FROM users')
        stats['users'] = cursor.fetchone()['cnt']

        cursor.execute('SELECT COUNT(*) AS cnt FROM reviews')
        stats['reviews'] = cursor.fetchone()['cnt']

        cursor.execute("SELECT name, email, role, permissions, on_duty FROM users WHERE role IN ('admin', 'staff')")
        staff_rows = cursor.fetchall()
        staff_members = []
        for row in staff_rows:
            item = dict(row)
            try:
                item['permissions'] = json.loads(item['permissions']) if item['permissions'] else dict(DEFAULT_STAFF_PERMISSIONS)
            except (ValueError, TypeError):
                item['permissions'] = dict(DEFAULT_STAFF_PERMISSIONS)
            staff_members.append(item)

        cursor.execute("SELECT name, email, phone FROM users WHERE role = 'pending' ORDER BY email")
        pending_workers = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            "SELECT id, full_name, phone, service, preferred_date, location FROM appointments "
            "WHERE approval_status = 'pending' ORDER BY id DESC"
        )
        pending_appointments = [dict(row) for row in cursor.fetchall()]

        staff_log_filter = request.args.get('staff_log', '').strip().lower()
        if staff_log_filter:
            cursor.execute('SELECT email, action, timestamp FROM logs WHERE email = ? ORDER BY id DESC LIMIT 200', (staff_log_filter,))
        else:
            cursor.execute('SELECT email, action, timestamp FROM logs ORDER BY id DESC LIMIT 50')
        logs = [dict(row) for row in cursor.fetchall()]

        cursor.execute("SELECT preferred_date, COUNT(*) AS cnt FROM appointments GROUP BY preferred_date ORDER BY preferred_date ASC")
        trend_rows = cursor.fetchall()
        chart_data['appointments_trend'] = {
            'labels': [row['preferred_date'] for row in trend_rows],
            'values': [row['cnt'] for row in trend_rows]
        }

        cursor.execute("SELECT rating, COUNT(*) AS cnt FROM reviews GROUP BY rating ORDER BY rating DESC")
        rating_rows = cursor.fetchall()
        chart_data['reviews_by_rating'] = {
            'labels': [str(row['rating']) for row in rating_rows],
            'values': [row['cnt'] for row in rating_rows]
        }

        cursor.execute("SELECT AVG(rating) AS avg_rating FROM reviews")
        avg_r = cursor.fetchone()['avg_rating']
        chart_data['avg_rating'] = round(avg_r, 1) if avg_r else 5.0

        cursor.execute("SELECT service, COUNT(*) AS cnt FROM appointments GROUP BY service ORDER BY COUNT(*) DESC")
        service_rows = cursor.fetchall()
        chart_data['appointments_by_service'] = {
            'labels': [row['service'] for row in service_rows],
            'values': [row['cnt'] for row in service_rows]
        }

        cursor.execute("SELECT location FROM appointments")
        loc_rows = cursor.fetchall()
        loc_counts = {}
        for row in loc_rows:
            loc_str = row['location'] or ''
            parts = [p.strip() for p in loc_str.split(',')]
            district = parts[-1] if parts else 'Unknown'
            if 'Live GPS Location' in district or '(' in district:
                district = 'GPS Pinned Location'
            loc_counts[district] = loc_counts.get(district, 0) + 1

        sorted_locs = sorted(loc_counts.items(), key=lambda x: x[1], reverse=True)[:6]
        chart_data['appointments_by_location'] = {
            'labels': [item[0] for item in sorted_locs],
            'values': [item[1] for item in sorted_locs]
        }

        cursor.execute("SELECT role, COUNT(*) AS cnt FROM users GROUP BY role")
        role_rows = cursor.fetchall()
        chart_data['users_by_role'] = {
            'labels': [row['role'].title() for row in role_rows],
            'values': [row['cnt'] for row in role_rows]
        }

    else:
        cursor.execute('SELECT email, action, timestamp FROM logs WHERE email = ? ORDER BY id DESC LIMIT 20', (email,))
        logs = [dict(row) for row in cursor.fetchall()]

        cursor.execute(
            'SELECT reference, service, preferred_date, location, approval_status FROM appointments '
            'WHERE booked_by_email = ? ORDER BY id DESC LIMIT 20', (email,)
        )
        my_appointments = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return render_template_string(
        DASHBOARD_HTML,
        stats=stats,
        chart_data=chart_data,
        logs=logs,
        staff_members=staff_members,
        pending_workers=pending_workers,
        pending_appointments=pending_appointments,
        my_appointments=my_appointments,
        staff_log_filter=staff_log_filter,
        worker_form_error=worker_form_error,
        toast_message=toast_message,
        activity=activity,
        perms=perms
    )


@app.route('/admin')
def admin_appointments():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    conn = get_db_connection()
    appointments = conn.execute('SELECT * FROM appointments ORDER BY id DESC').fetchall()
    conn.close()
    return render_template_string(ADMIN_APPOINTMENTS_HTML, appointments=appointments)


import re

NIN_PATTERN = re.compile(r'^[A-Za-z]{2}[A-Za-z0-9]{12}$')       # e.g. CM12345678ABCD (14 chars)
NSSF_PATTERN = re.compile(r'^[0-9]{6,12}$')
TIN_PATTERN = re.compile(r'^[0-9]{10}$')                          # URA TIN is 10 digits
PASSPORT_PATTERN = re.compile(r'^[A-Za-z0-9]{6,9}$')


@app.route('/admin/create-worker', methods=['POST'])
def admin_create_worker():
    """Step 1: registers a worker into the system with no role or permissions
    yet. They land in the 'pending' pool until an admin activates them via
    /admin/activate-worker.

    NIN/NSSF/TIN/passport are format-validated only (regex checks that they
    look like a real ID number). This is NOT government verification — that
    would require a paid identity-verification/KYC API integration.
    """
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    fullname = request.form.get('fullname', '').strip()
    email = request.form.get('email', '').strip().lower()
    phone = request.form.get('phone', '').strip()
    password = request.form.get('password', '').strip()
    nin = request.form.get('nin', '').strip().upper()
    nssf_number = request.form.get('nssf_number', '').strip()
    tin_number = request.form.get('tin_number', '').strip()
    passport_number = request.form.get('passport_number', '').strip().upper()
    next_of_kin_name = request.form.get('next_of_kin_name', '').strip()
    next_of_kin_phone = request.form.get('next_of_kin_phone', '').strip()

    if not all([fullname, email, phone, password, nin, nssf_number, tin_number,
                passport_number, next_of_kin_name, next_of_kin_phone]):
        return redirect(url_for('dashboard', worker_error="All fields are required, including next of kin details."))

    if not NIN_PATTERN.match(nin):
        return redirect(url_for('dashboard', worker_error="That NIN doesn't look valid — it should be 14 characters, starting with 2 letters (e.g. CM12345678ABCD)."))
    if not NSSF_PATTERN.match(nssf_number):
        return redirect(url_for('dashboard', worker_error="That NSSF number doesn't look valid — digits only."))
    if not TIN_PATTERN.match(tin_number):
        return redirect(url_for('dashboard', worker_error="That TIN doesn't look valid — URA TINs are 10 digits."))
    if not PASSPORT_PATTERN.match(passport_number):
        return redirect(url_for('dashboard', worker_error="That passport number doesn't look valid."))

    id_photo = request.files.get('id_photo')
    if not id_photo or not id_photo.filename:
        return redirect(url_for('dashboard', worker_error="Please upload the worker's ID photo."))
    id_photo_bytes = id_photo.read()
    if len(id_photo_bytes) > 5 * 1024 * 1024:
        return redirect(url_for('dashboard', worker_error="That photo is too large — please use one under 5MB."))
    photo_ok, photo_reason = screen_photo_has_face(id_photo_bytes)
    if not photo_ok:
        return redirect(url_for('dashboard', worker_error=photo_reason))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT email FROM users WHERE email = ?', (email,))
    if cursor.fetchone():
        conn.close()
        return redirect(url_for('dashboard', worker_error="That email is already registered."))

    hashed_pw = generate_password_hash(password)
    cursor.execute(
        '''INSERT INTO users
           (email, name, role, password, phone, status, nin, nssf_number, tin_number,
            passport_number, next_of_kin_name, next_of_kin_phone, id_photo)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (email, fullname, 'pending', hashed_pw, phone, 'pending', nin, nssf_number, tin_number,
         passport_number, next_of_kin_name, next_of_kin_phone, psycopg2.Binary(id_photo_bytes))
    )
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Registered new worker applicant: {email}")

    return redirect(url_for('dashboard', toast=f"Logged: registered worker applicant {email}"))


@app.route('/admin/activate-worker', methods=['POST'])
def admin_activate_worker():
    """Step 2: picks a pending worker registration, assigns permissions, and
    makes them an active staff member."""
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    target_email = request.form.get('email', '').strip().lower()

    permissions = {
        "view_appointments": request.form.get('perm_view_appointments') == 'on',
        "create_bookings": request.form.get('perm_create_bookings') == 'on',
        "view_files": request.form.get('perm_view_files') == 'on',
        "manage_staff": request.form.get('perm_manage_staff') == 'on',
    }

    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET role = 'staff', status = 'active', permissions = ? WHERE email = ? AND role = 'pending'",
        (json.dumps(permissions), target_email)
    )
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Activated worker {target_email} as staff")
    return redirect(url_for('dashboard', toast=f"Logged: activated {target_email} as staff"))


@app.route('/admin/update-permissions', methods=['POST'])
def admin_update_permissions():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    target_email = request.form.get('email', '').strip().lower()
    if target_email == 'admin@carehive.com':
        return redirect(url_for('dashboard'))

    permissions = {
        "view_appointments": request.form.get('perm_view_appointments') == 'on',
        "create_bookings": request.form.get('perm_create_bookings') == 'on',
        "view_files": request.form.get('perm_view_files') == 'on',
        "manage_staff": request.form.get('perm_manage_staff') == 'on',
    }

    conn = get_db_connection()
    conn.execute('UPDATE users SET permissions = ? WHERE email = ?', (json.dumps(permissions), target_email))
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Updated permissions for {target_email}")
    return redirect(url_for('dashboard', toast=f"Logged: updated permissions for {target_email}"))


@app.route('/admin/approve-appointment', methods=['POST'])
def admin_approve_appointment():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    appointment_id = request.form.get('appointment_id', '').strip()
    confirmed_date = request.form.get('confirmed_date', '').strip()

    conn = get_db_connection()
    if confirmed_date:
        conn.execute(
            "UPDATE appointments SET approval_status = 'approved', preferred_date = ? WHERE id = ?",
            (confirmed_date, appointment_id)
        )
    else:
        conn.execute("UPDATE appointments SET approval_status = 'approved' WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Approved and scheduled appointment #{appointment_id} for {confirmed_date}")
    return redirect(url_for('dashboard', toast=f"Logged: approved & scheduled appointment #{appointment_id}"))


@app.route('/admin/reject-appointment', methods=['POST'])
def admin_reject_appointment():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    appointment_id = request.form.get('appointment_id', '').strip()
    conn = get_db_connection()
    conn.execute("UPDATE appointments SET approval_status = 'rejected' WHERE id = ?", (appointment_id,))
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Rejected appointment #{appointment_id}")
    return redirect(url_for('dashboard', toast=f"Logged: rejected appointment #{appointment_id}"))


@app.route('/admin/edit-staff', methods=['POST'])
def admin_edit_staff():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    target_email = request.form.get('email', '').strip().lower()
    if target_email == 'admin@carehive.com':
        return redirect(url_for('dashboard'))

    # Name is fixed at registration and cannot be changed here — only
    # contact details are editable.
    phone = request.form.get('phone', '').strip()

    conn = get_db_connection()
    conn.execute('UPDATE users SET phone = ? WHERE email = ?', (phone, target_email))
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Edited staff details for {target_email}")
    return redirect(url_for('dashboard', toast=f"Logged: updated contact details for {target_email}"))


@app.route('/admin/staff-log/<email>')
def admin_staff_log(email):
    if 'user' not in session or session['user']['role'] != 'admin':
        return jsonify({"error": "unauthorized"}), 403

    conn = get_db_connection()
    user_row = conn.execute('SELECT name, email FROM users WHERE email = ?', (email.strip().lower(),)).fetchone()
    logs = conn.execute(
        'SELECT action, timestamp FROM logs WHERE email = ? ORDER BY id DESC LIMIT 500', (email.strip().lower(),)
    ).fetchall()
    conn.close()

    if not user_row:
        return jsonify({"error": "not found"}), 404

    return jsonify({
        "name": user_row['name'],
        "email": user_row['email'],
        "logs": [dict(row) for row in logs]
    })


@app.route('/admin/staff-log/<email>/download')
def admin_staff_log_download(email):
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    import csv

    conn = get_db_connection()
    logs = conn.execute(
        'SELECT email, action, timestamp FROM logs WHERE email = ? ORDER BY id DESC LIMIT 1000', (email.strip().lower(),)
    ).fetchall()
    conn.close()

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(['Email', 'Action', 'Timestamp'])
    for row in logs:
        writer.writerow([row['email'], row['action'], row['timestamp']])

    output = io.BytesIO(buffer.getvalue().encode('utf-8'))
    safe_email = ''.join(c for c in email if c.isalnum() or c in '@.-_')
    from flask import send_file
    return send_file(
        output, mimetype='text/csv', as_attachment=True,
        download_name=f"activity-log-{safe_email}.csv"
    )


@app.route('/admin/toggle-duty', methods=['POST'])
def admin_toggle_duty():
    """Marks a staff member on/off duty. No cap on how many can be on duty
    at once — that's an operational policy call left entirely to the admin."""
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    target_email = request.form.get('email', '').strip().lower()
    if target_email == 'admin@carehive.com':
        return redirect(url_for('dashboard'))

    on_duty = 1 if request.form.get('on_duty') == 'on' else 0

    conn = get_db_connection()
    conn.execute(
        "UPDATE users SET on_duty = ? WHERE email = ? AND role IN ('admin', 'staff')",
        (on_duty, target_email)
    )
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Marked {target_email} as {'on duty' if on_duty else 'off duty'}")
    return redirect(url_for('dashboard', toast=f"Logged: marked {target_email} as {'on duty' if on_duty else 'off duty'}"))


@app.route('/admin/remove-staff', methods=['POST'])
def admin_remove_staff():
    if 'user' not in session or session['user']['role'] != 'admin':
        return redirect(url_for('login'))

    target_email = request.form.get('email', '').strip().lower()
    if target_email == 'admin@carehive.com':
        return redirect(url_for('dashboard'))

    conn = get_db_connection()
    conn.execute("DELETE FROM users WHERE email = ? AND role != 'admin'", (target_email,))
    conn.commit()
    conn.close()
    log_activity(session['user']['email'], f"Removed staff account {target_email}")
    return redirect(url_for('dashboard', toast=f"Logged: removed staff account {target_email}"))


if __name__ == '__main__':
    init_db()
    print("Starting Carehive Homecare Limited Flask Application...")
    app.run(host='0.0.0.0', port=5000, debug=True)