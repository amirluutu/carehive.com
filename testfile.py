import sqlite3
import hashlib
import json
import os
from flask import Flask, render_template_string, render_template, request, redirect, url_for, session, send_from_directory, flash
from datetime import datetime, timezone
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'super-secret-carehive-key'
DB_NAME = 'carehive.db'

# Configure upload folder and allowed extensions
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

# Create upload directory if it doesn't exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Create default images if they don't exist
def create_default_images():
    """Create placeholder images if they don't exist"""
    images_needed = ['nursing-care.jpg', 'broncure.png', 'baby-care.png', 'elderly-care.jpg', 'home-nursing.jpg']
    
    for image_name in images_needed:
        image_path = os.path.join(UPLOAD_FOLDER, image_name)
        if not os.path.exists(image_path):
            try:
                from PIL import Image, ImageDraw, ImageFont
                img = Image.new('RGB', (800, 600), color=(70, 130, 180))
                draw = ImageDraw.Draw(img)
                
                try:
                    font = ImageFont.truetype("arial.ttf", 40)
                except:
                    font = ImageFont.load_default()
                
                text = image_name.replace('.jpg', '').replace('.png', '').replace('-', ' ').title()
                bbox = draw.textbbox((0, 0), text, font=font)
                text_width = bbox[2] - bbox[0]
                text_height = bbox[3] - bbox[1]
                
                x = (800 - text_width) // 2
                y = (600 - text_height) // 2
                
                draw.text((x, y), text, fill=(255, 255, 255), font=font)
                img.save(image_path)
                
            except ImportError:
                with open(image_path, 'w') as f:
                    f.write("Placeholder image")

# Initialize default images
create_default_images()

# --- SECURITY HELPER ---
def hash_password(password):
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def log_action(email, action):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    timestamp = datetime.now(timezone.utc).isoformat()
    cursor.execute('INSERT INTO logs (email, action, timestamp) VALUES (?, ?, ?)', 
                   (email, action, timestamp))
    conn.commit()
    conn.close()

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            password TEXT NOT NULL,
            created_at TEXT NOT NULL
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
            full
