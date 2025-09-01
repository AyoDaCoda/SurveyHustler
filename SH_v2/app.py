import os
import random
from datetime import datetime, timedelta, UTC, timezone
from sqlalchemy.orm.attributes import flag_modified
import pandas
import gspread as gspread
from flask import Flask, request, render_template, jsonify, redirect, url_for, session # Import session
from flask_sqlalchemy import SQLAlchemy
from google.oauth2.gdch_credentials import ServiceAccountCredentials
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
import re
from google.oauth2 import service_account
from googleapiclient.discovery import build
from dotenv import load_dotenv
import json

from google.oauth2.service_account import Credentials

# New imports needed for email sending (if you haven't re-added them yet)
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

#AI
import google.generativeai as genai
import requests
import hmac
import hashlib

# Get the directory of the current script (app.py)
basedir = os.path.abspath(os.path.dirname(__file__))

env_path = os.path.join(basedir, '.env')

# Load environment variables from .env file in the same directory
# Using verbose=True can help debug if dotenv is finding and loading files
load_dotenv(os.path.join(basedir, 'surveyhustler.env'), override=True, verbose=True)

# print(f"DEBUG: FLASK_SECRET_KEY after load_dotenv = {os.getenv('FLASK_SECRET_KEY')}") # This is the critical one!

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY')

GSPREAD_KEY_PATH = os.path.join(basedir, 'surveyhustler-api-8baa5c0c1239.json')


gc = None
try:
    gc = gspread.service_account(filename=GOOGLE_CREDENTIALS_PATH)
    print("INFO: gspread client initialized successfully.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize gspread client: {e}")

try:
    # Use os.getenv to retrieve the entire JSON string from your .env file
    creds_json = os.getenv('GOOGLE_SERVICE_ACCOUNT_CREDENTIALS')
    if creds_json:
        # Parse the JSON string into a Python dictionary
        credentials_dict = json.loads(creds_json)

        # Use gspread.service_account_from_dict for authentication
        gc = gspread.service_account_from_dict(credentials_dict)
        print("INFO: gspread client initialized successfully.")
    else:
        print("ERROR: GOOGLE_SERVICE_ACCOUNT_CREDENTIALS not found in environment variables.")
except Exception as e:
    print(f"CRITICAL ERROR: Failed to initialize gspread client: {e}")

if not app.config['SECRET_KEY']:
    raise ValueError("No FLASK_SECRET_KEY set for Flask application")

db = SQLAlchemy(app)

# Existing OTP storage
otp_storage = {}

# Existing REQUIRED_EDITOR_EMAIL
REQUIRED_EDITOR_EMAIL = "ayomideabod@gmail.com"

SENDER_EMAIL = os.environ.get("EMAIL_USER")
SENDER_PASSWORD = os.environ.get("EMAIL_PASS")
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587 # 587 for TLS

#KoraPay stuff
KORAPAY_SECRET_KEY = os.getenv("KORAPAY_SECRET_KEY")
KORAPAY_PUBLIC_KEY = os.getenv("KORAPAY_PUBLIC_KEY")
KORAPAY_API_BASE_URL = "https://api.korapay.com/v1"
KORAPAY_WEBHOOK_SECRET = os.getenv("KORAPAY_WEBHOOK_SECRET")


# --------------------- MODELS ---------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tg_id = db.Column(db.String(100), unique=True)
    first_name = db.Column(db.String(100))
    last_name = db.Column(db.String(100))
    email = db.Column(db.String(100), unique=True)
    phone = db.Column(db.String(20))
    gender = db.Column(db.String(10))
    password = db.Column(db.String(200))
    role = db.Column(db.String(50))

    institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=True)
    college_id = db.Column(db.Integer, db.ForeignKey('college.id'), nullable=True)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=True)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)

    institution = db.Column(db.String(100))
    college = db.Column(db.String(100))
    department = db.Column(db.String(100))
    course = db.Column(db.String(100))
    level = db.Column(db.String(10))

    wallet = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    otp_code = db.Column(db.String(6), nullable=True)
    otp_expiration = db.Column(db.DateTime(timezone=True), nullable=True)
    surveys = db.relationship('Survey', backref='owner', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.email}>'

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Survey(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    responder_link = db.Column(db.String(500))  # for users to answer
    sheet_link = db.Column(db.String(500))
    duration = db.Column(db.Float)
    responses = db.Column(db.Integer)
    reward = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # New fields for filtering
    apply_filter = db.Column(db.Boolean, default=False)
    from sqlalchemy.dialects.postgresql import JSONB
    filters_json = db.Column(JSONB, nullable=True)
    filters = db.relationship('SurveyFilter', back_populates='survey', uselist=False)

# Model to store the filtering criteria for a survey
class SurveyFilter(db.Model):
    __tablename__ = 'survey_filter'
    id = db.Column(db.Integer, primary_key=True)
    survey_id = db.Column(db.Integer, db.ForeignKey('survey.id'), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=True)
    level_id = db.Column(db.Integer, db.ForeignKey('level.id'), nullable=True)

    # Relationships
    survey = db.relationship('Survey', backref='filter', uselist=False)
    course = db.relationship('Course', foreign_keys=[course_id], backref='survey_filters')
    level = db.relationship('Level', foreign_keys=[level_id], backref='survey_filters')

    def __repr__(self):
        return f"<SurveyFilter survey_id={self.survey_id}, course_id={self.course_id}, level_id={self.level_id}>"

class PaymentTransaction(db.Model):
    """
    Model to track Korapay payment transactions for surveys.
    This helps us handle webhooks and confirm payments before survey creation.
    """
    id = db.Column(db.Integer, primary_key=True)
    transaction_reference = db.Column(db.String(255), unique=True, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    amount = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(50), default='pending') # Can be 'pending', 'success', 'failed'
    survey_data = db.Column(db.JSON, nullable=False) # Store the survey payload here until confirmed
    created_at = db.Column(db.DateTime, default=datetime.now(UTC))
    updated_at = db.Column(db.DateTime, onupdate=datetime.now(UTC))

# --------------------- ACADEMIC HIERARCHY ---------------------
class Institution(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    colleges = db.relationship('College', backref='institution', cascade="all, delete-orphan")

class College(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    institution_id = db.Column(db.Integer, db.ForeignKey('institution.id'), nullable=False)
    departments = db.relationship('Department', backref='college', cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint('name', 'institution_id', name='_college_name_institution_uc'),)

class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    college_id = db.Column(db.Integer, db.ForeignKey('college.id'), nullable=False)
    courses = db.relationship('Course', backref='department', cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint('name', 'college_id', name='_department_name_college_uc'),)

class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'), nullable=False)
    # NEW: Re-establish relationship to Level
    levels = db.relationship('Level', backref='course', lazy=True)
    __table_args__ = (db.UniqueConstraint('name', 'department_id', name='_course_department_uc'),)
    filters = db.relationship('SurveyFilter', back_populates='course')

class Level(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    value = db.Column(db.String(10), nullable=False) # No longer unique globally, can be repeated per course
    # NEW: Add foreign key back to Course
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    __table_args__ = (db.UniqueConstraint('value', 'course_id', name='_level_course_uc'),) # Level value must be unique per course
    filters = db.relationship('SurveyFilter', back_populates='level')

# --------------------- GOOGLE UTILS ---------------------

def extract_file_id(url):
    """
    Extracts the file ID from a Google Forms or Google Sheets URL.
    Returns None if no valid ID is found.
    """
    if not isinstance(url, str):
        return None

    # Check for the /forms/d/e/ format, which is common for Google Forms
    match = re.search(r'/d/e/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    # Check for the /forms/d/ or /spreadsheets/d/ format
    match = re.search(r'/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)

    return None

def check_editor_access(form_link):
    try:
        print("[check_editor_access] Checking access for:", form_link)

        SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']
        creds = service_account.Credentials.from_service_account_info(
            credentials_dict, scopes=SCOPES
        )
        drive = build('drive', 'v3', credentials=creds)

        file_id = extract_file_id(form_link)
        if not file_id:
            print("[check_editor_access] Invalid file ID")
            return False

        print("[check_editor_access] Extracted file ID:", file_id)

        perms = drive.permissions().list(fileId=file_id, fields="permissions(emailAddress)").execute()
        emails = [p.get("emailAddress") for p in perms.get("permissions", [])]
        print("[check_editor_access] Emails found:", emails)

        result = REQUIRED_EDITOR_EMAIL in emails
        print("[check_editor_access] Access allowed:", result)
        return result

    except Exception as e:
        print("[check_editor_access] Drive API error:", e)
        return False

def get_all_survey_data(sheet_link):
    """
    Retrieves all survey data from a Google Sheet and returns it as a list of dictionaries.
    """
    global gc
    if gc is None:
        print("CRITICAL ERROR: gspread client (gc) is not initialized. Cannot access sheets.")
        return []

    try:
        spreadsheet_id = sheet_link.split("/d/")[1].split("/")[0]
        sheet = gc.open_by_key(spreadsheet_id)
        worksheet = sheet.get_worksheet(0)

        # This function is perfect for AI analysis as it returns a list of dictionaries
        data = worksheet.get_all_records()

        print(f"DEBUG: Successfully retrieved {len(data)} records from sheet.")
        return data

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: Spreadsheet not found for link: {sheet_link}")
        return []
    except Exception as e:
        print(f"ERROR: An unexpected error occurred accessing Google Sheet {sheet_link}: {e}")
        return []

def get_all_survey_data_from_sheet(sheet_link):
    """
    Retrieves all survey data from a Google Sheet and returns it as a list of dictionaries.
    """
    global gc
    if gc is None:
        return []

    try:
        spreadsheet_id = sheet_link.split("/d/")[1].split("/")[0]
        sheet = gc.open_by_key(spreadsheet_id)
        worksheet = sheet.get_worksheet(0)

        data = worksheet.get_all_records()
        return data

    except Exception as e:
        print(f"ERROR: An unexpected error occurred accessing Google Sheet {sheet_link}: {e}")
        return []

def get_response_count_from_sheet(sheet_link, include_emails=False, include_timestamps=False):
    global gc
    if gc is None:
        print("CRITICAL ERROR: gspread client (gc) is not initialized. Cannot access sheets.")
        return [] if include_emails else 0

    try:
        if "spreadsheets/d/" not in sheet_link:
            print(f"ERROR: Invalid sheet link format: {sheet_link}")
            return [] if include_emails else 0

        spreadsheet_id = sheet_link.split("/d/")[1].split("/")[0]
        sheet = gc.open_by_key(spreadsheet_id)
        worksheet = sheet.get_worksheet(0)

        all_data = worksheet.get_all_values()
        if not all_data:
            print(f"DEBUG: Sheet {sheet_link} is empty.")
            return [] if include_emails else 0

        headers = [h.strip().lower() for h in all_data[0]]
        data_rows = all_data[1:]

        print(f"DEBUG: Headers found in sheet {sheet_link}: {headers}")

        email_column_index = -1
        timestamp_column_index = -1
        possible_email_headers = ['email address', 'email', 'your email', 'email id']
        possible_timestamp_headers = ['timestamp', 'start_time']

        for i, header in enumerate(headers):
            if header in possible_email_headers:
                email_column_index = i
            if header in possible_timestamp_headers:
                timestamp_column_index = i

        if email_column_index == -1:
            print(f"ERROR: No identifiable email column found in sheet {sheet_link}.")
            return [] if include_emails else len(data_rows)

        if include_timestamps and timestamp_column_index == -1:
            print(f"ERROR: A timestamp column was requested but not found in sheet {sheet_link}.")
            return []  # Return empty list if timestamps are needed but not found.

        if include_emails:
            entries = []
            for row_idx, row in enumerate(data_rows):
                if len(row) > email_column_index and len(row) > timestamp_column_index:
                    email_value = row[email_column_index].strip().lower()
                    timestamp_value = row[timestamp_column_index].strip()

                    if "@" in email_value and "." in email_value:
                        entries.append({
                            "email": email_value,
                            "timestamp": timestamp_value
                        })

            print(f"DEBUG: Found {len(entries)} valid entries in sheet {sheet_link}.")
            return entries
        else:
            return len(data_rows)

    except gspread.exceptions.SpreadsheetNotFound:
        print(f"ERROR: Spreadsheet not found for link: {sheet_link}")
        return [] if include_emails else 0
    except gspread.exceptions.WorksheetNotFound:
        print(f"ERROR: No worksheet found for link: {sheet_link}")
        return [] if include_emails else 0
    except Exception as e:
        print(f"ERROR: An unexpected error occurred accessing Google Sheet {sheet_link}: {e}")
        return [] if include_emails else 0

# --------------------- EMAIL SENDER FUNCTION ---------------------

def send_otp_email(user_email, otp_code):
    if SENDER_EMAIL == "your_gmail_address@gmail.com" or SENDER_PASSWORD == "your_gmail_app_password":
        print(f"Simulating OTP email to {user_email}. OTP Code: {otp_code}")
        return True # Simulate success if credentials are not set

    message = MIMEMultipart("alternative")
    message["Subject"] = "Your SurveyHustler OTP"
    message["From"] = SENDER_EMAIL
    message["To"] = user_email

    text = f"Hi,\n\nYour One-Time Password (OTP) for SurveyHustler is: {otp_code}\n\nThis OTP is valid for 5 minutes."
    html = f"""\
    <html>
    <body>
        <p>Hi,<br><br>
        Your One-Time Password (OTP) for SurveyHustler is: <strong>{otp_code}</strong><br><br>
        This OTP is valid for 5 minutes.<br><br>
        Thanks,<br>
        The SurveyHustler Team
        </p>
    </body>
    </html>
    """
    part1 = MIMEText(text, "plain")
    part2 = MIMEText(html, "html")
    message.attach(part1)
    message.attach(part2)

    context = ssl.create_default_context()
    try:
        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.ehlo()
            server.starttls(context=context)
            server.ehlo()
            server.login(SENDER_EMAIL, SENDER_PASSWORD)
            server.sendmail(SENDER_EMAIL, user_email, message.as_string())
        print(f"OTP email sent to {user_email}")
        return True
    except Exception as e:
        print(f"Failed to send OTP email to {user_email}: {e}")
        return False

# --------------------- ROUTES ---------------------
@app.cli.command('seed')
def seed():
    from sqlalchemy.exc import IntegrityError
    from sqlalchemy import text # NEW IMPORT

    with db.engine.connect() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE;"))
        connection.execute(text("CREATE SCHEMA public;"))
        connection.commit() # Commit the schema recreation

    db.create_all() # Now recreate all tables after the schema reset

    cu = Institution(name="Covenant University")
    db.session.add(cu)

    # ... (rest of your existing colleges_data and seeding logic) ...
    colleges_data = {
        "CST": {
            "CIS": ["Computer science", "MIS"],
            "Architecture": ["Architecture"],
            "Biology": ["Biology"],
            "Mathematics": ["Mathematics"],
            "Physics": ["Quantum physics", "Industrial Physics"]
        },
        "COE": {
            "EIE": ["Computer engineering", "Electrical engineering"],
            "MECH": ["Mechanical engineering"],
            "PET": ["Petroleum engineering"]
        },
        "CMSS": {
            "Economics": ["Economics"],
            "Accounting": ["Accounting"],
            "Finance": ["Fintech", "Business Finance"],
            "Marketing": ["Marketing"],
            "Mass communication": ["Mass communication"]
        },
        "CLDS": {
            "Psychology": ["Psychology"],
            "Political science": ["Political science"],
            "International relations": ["International relations"]
        }
    }

    standard_levels = ['100', '200', '300', '400']  # Common levels for most courses
    engineering_levels = ['100', '200', '300', '400', '500']  # For engineering courses

    for college_name, departments in colleges_data.items():
        college = College(name=college_name, institution=cu)
        db.session.add(college)

        for dept_name, courses in departments.items():
            dept = Department(name=dept_name, college=college)
            db.session.add(dept)

            for course_name in courses:
                course = Course(name=course_name, department=dept)
                db.session.add(course)

                levels_for_this_course = standard_levels
                if college_name == "COE":  # Example: Engineering might have 500 level for undergrad
                    levels_for_this_course = engineering_levels
                    # You can add more complex logic here if certain courses have unique levels

                for lvl_val in levels_for_this_course:
                    db.session.add(Level(value=lvl_val, course=course))  # Link level to course

    try:
        db.session.commit()
        print("✅ Database seeded successfully.")
    except IntegrityError as e:
        db.session.rollback()
        print("⚠️ Seed failed due to integrity error:", e)




#REGISTER
@app.route('/')
def index():
    return redirect('/register')

@app.route('/register')
def register():
    return render_template('register.html', tg_id=request.args.get("tg_id", ""), server_url=os.getenv("SERVER_URL"))

# New API endpoint to send OTP
# app.py (Modify or add this route, e.g., before other API routes)
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    first_name = data.get('first_name')
    last_name = data.get('last_name')
    gender = data.get('gender')
    phone = data.get('phone')
    tg_id = data.get('tg_id') # Get telegram ID from the frontend

    # Basic validation for personal details
    if not all([email, password, first_name, last_name, phone, gender]):
        return jsonify({'status': 'error', 'message': 'Missing required personal details'}), 400

    # Check if email or phone is already fully registered
    existing_user_email = User.query.filter_by(email=email).first()
    if existing_user_email and existing_user_email.role != 'unverified': # 'unverified' is a temporary role
        return jsonify({'status': 'error', 'message': 'Email already registered and verified.'}), 409

    existing_user_phone = User.query.filter_by(phone=phone).first()
    if existing_user_phone and existing_user_phone.role != 'unverified':
        return jsonify({'status': 'error', 'message': 'Phone number already registered and verified.'}), 409

    hashed_password = generate_password_hash(password)

    # Generate OTP
    otp_code = str(random.randint(100000, 999999)) # 6-digit OTP
    otp_expiration = datetime.now(UTC) + timedelta(minutes=5) # OTP valid for 5 minutes

    try:
        # Find existing unverified user or create a new one
        user = User.query.filter_by(email=email).first() # Should already be checked above, but as fallback
        if user:
            # User exists but is unverified or needs OTP update
            user.password = hashed_password
            user.first_name = first_name
            user.last_name = last_name
            user.gender = gender
            user.phone = phone
            user.otp_code = otp_code
            user.otp_expiration = otp_expiration
            user.role = 'unverified' # Ensure role is unverified until final step
            user.tg_id = tg_id # Update tg_id if user is re-registering
        else:
            user = User(
                email=email,
                password=hashed_password,
                first_name = first_name,
                last_name = last_name,
                gender=gender,
                phone=phone,
                role='unverified', # Set initial role as unverified
                otp_code=otp_code,
                otp_expiration=otp_expiration,
                tg_id=tg_id # Save Telegram ID
            )
            db.session.add(user)

        db.session.commit()

        # Store the email in session to identify the user for OTP verification
        session['pending_otp_email'] = email
        session.modified = True

        if send_otp_email(user.email, otp_code):
            return jsonify({
                'status': 'success',
                'message': 'OTP sent to your email. Please check and enter it to proceed.',
                'otp_sent': True
            }), 200
        else:
            # If email sending fails, you might want to log this or return a different message
            # For now, we'll still report success but with a warning.
            return jsonify({
                'status': 'success',
                'message': 'OTP generated, but failed to send email. Please check your email and try again, or contact support if issue persists.'
            }), 200

        return jsonify({
            'status': 'success',
            'message': 'OTP sent to your email/phone. Please check and enter it to proceed.',
            'otp_sent': True # Indicates that OTP has been initiated
        }), 200

    except Exception as e:
        db.session.rollback()
        print(f"Error during initial registration/OTP sending: {e}")
        return jsonify({'status': 'error', 'message': f'Internal server error: {e}'}), 500

# app.py (Add this new route)
@app.route('/api/verify_otp', methods=['POST'])
def verify_otp():
    data = request.json
    otp_entered = data.get('otp_code')
    email = session.get('pending_otp_email') # Retrieve email from session

    if not email:
        return jsonify({'status': 'error', 'message': 'Session expired or registration not initiated. Please start registration again.'}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found for OTP verification.'}), 404

    if not user.otp_code or not user.otp_expiration:
        return jsonify({'status': 'error', 'message': 'No active OTP for this user. Please request a new one.'}), 400

    if user.otp_expiration < datetime.now(UTC):
        user.otp_code = None # Clear expired OTP
        user.otp_expiration = None
        db.session.commit()
        return jsonify({'status': 'error', 'message': 'OTP has expired. Please request a new one.'}), 400

    if user.otp_code == otp_entered:
        # OTP is valid! Clear it from the database
        user.otp_code = None
        user.otp_expiration = None
        db.session.commit()
        # Keep 'pending_otp_email' in session to allow proceeding to academic details
        return jsonify({'status': 'success', 'message': 'OTP verified successfully. Proceed to academic details.'}), 200
    else:
        return jsonify({'status': 'error', 'message': 'Invalid OTP. Please try again.'}), 400

# app.py (Add this new route)
@app.route('/api/register', methods=['POST'])
def complete_registration():
    data = request.json
    email = session.get('pending_otp_email') # Retrieve email from session

    if not email:
        return jsonify({'status': 'error', 'message': 'Session expired or OTP not verified. Please restart registration.'}), 400

    user = User.query.filter_by(email=email).first()

    if not user:
        return jsonify({'status': 'error', 'message': 'User not found for final registration.'}), 404

    # Extract academic details and role
    institution_id = data.get('institution') # This will be the ID
    role = data.get('role') # 'Student' or 'Creator'
    college_id = data.get('college') # This will be the ID
    department_id = data.get('department') # This will be the ID
    course_id = data.get('course') # This will be the ID (optional)
    level = data.get('level')

    print(f"DEBUG_REGISTER: Received data: {data}")
    print(f"DEBUG_REGISTER: institution_id: {institution_id}, college_id: {college_id}, department_id: {department_id}")
    print(f"DEBUG_REGISTER: course_id: {course_id}, level: {level}, role: {role}")

    # Basic validation for academic details
    if not all([institution_id, role, college_id, department_id, level]):
        return jsonify({'status': 'error', 'message': 'Missing required academic details'}), 400

    try:
        institution_obj = Institution.query.get(institution_id)
        user.institution_id = institution_id
        user.institution = institution_obj.name if institution_obj else None

        college_obj = College.query.get(college_id)
        user.college_id = college_id
        user.college = college_obj.name if college_obj else None

        department_obj = Department.query.get(department_id)
        user.department_id = department_id
        user.department = department_obj.name if department_obj else None

        course_obj = Course.query.get(course_id)
        print(f"DEBUG_REGISTER: Course object found: {course_obj is not None}. Name: {course_obj.name if course_obj else 'N/A'}")
        user.course_id = course_id
        user.course = course_obj.name if course_obj else None

        # These fields are simple strings/enums
        user.level = level
        user.role = role

        db.session.add(user)
        db.session.commit()

        db.session.refresh(user)
        print(f"DEBUG_REGISTER_POST_COMMIT: Course of study saved as: {user.course}")
        session.pop('pending_otp_email', None) # Clear session data after successful final registration
        session.modified = True

        return jsonify({
            'status': 'success',
            'message': 'Registration complete! Welcome to SurveyHustler.'
        }), 200
    except Exception as e:
        db.session.rollback()
        print(f"Error during final registration (academic details): {e}")
        return jsonify({'status': 'error', 'message': f'Internal server error during final registration: {e}'}), 500

@app.route('/api/check_user/<tg_id>')
def check_user(tg_id):
    user = User.query.filter_by(tg_id=str(tg_id)).first()
    if not user:
        return jsonify({'registered': False})
    return jsonify({'registered': True, 'user': {'wallet': user.wallet, 'first_name': user.first_name}})

@app.route('/api/login', methods=['POST'])
def api_login():
    data = request.json
    user = User.query.filter_by(email=data['email']).first()
    if user and check_password_hash(user.password, data['password']) and str(user.tg_id) == str(data['tg_id']):
        return jsonify({'success': True, 'name': f"{user.first_name} {user.last_name}"})
    return jsonify({'success': False, 'error': 'Invalid credentials'})




#UPLOAD SURVEYS
@app.route('/upload_survey_login')
def upload_survey_login():
    return render_template('upload_login.html', tg_id=request.args.get("tg_id", ""), server_url=os.getenv("SERVER_URL"))

@app.route('/form_setup')
def form_setup():
    return render_template('form_setup.html', tg_id=request.args.get("tg_id", ""), server_url=os.getenv("SERVER_URL"))

@app.route('/survey_details')
def survey_details():
    return render_template('survey_details.html', server_url=os.getenv("SERVER_URL"))

@app.route('/success')
def success():
    return "Changes saved! Go back to your Telegram bot."

@app.route('/api/options')
def get_options():
    institutions_data = []
    institutions = Institution.query.all()

    for inst in institutions:
        inst_colleges = []
        for col in inst.colleges:
            col_departments = []
            for dept in col.departments:
                dept_courses = []
                for course in dept.courses:
                    course_levels = [lvl.value for lvl in course.levels]
                    dept_courses.append({
                        "id": course.id,
                        "name": course.name,
                        "levels": course_levels
                    })
                col_departments.append({
                    "id":dept.id,
                    "name": dept.name,
                    "courses": dept_courses
                })
            inst_colleges.append({
                "id": col.id,
                "name": col.name,
                "departments": col_departments
            })
        institutions_data.append({
            "id": inst.id,
            "name": inst.name,
            "colleges": inst_colleges
        })
    return jsonify({"institutions": institutions_data})




#KORAPAY
@app.route('/api/initiate_survey_payment', methods=['POST'])
def initiate_survey_payment():
    data = request.json
    user_id = data.get('tg_id')
    amount = data.get('total_cost')
    redirect_url = data.get('redirect_url')
    survey_data = data  # Store all the survey data for later use

    if not all([user_id, amount, redirect_url]):
        return jsonify({'message': 'Missing required fields'}), 400

    # Create a unique transaction reference
    transaction_reference = f"SURVEY_{user_id}_{int(datetime.now().timestamp())}_{random.randint(1000, 9999)}"

    # Store a pending transaction in the database
    new_transaction = PaymentTransaction(
        transaction_reference=transaction_reference,
        user_id=user_id,
        amount=amount,
        survey_data=survey_data
    )
    db.session.add(new_transaction)
    db.session.commit()

    # Prepare Korapay request
    payload = {
        "amount": amount,
        "currency": "NGN",
        "narration": f"Payment for survey upload by user {user_id}",
        "redirect_url": redirect_url,
        "reference": transaction_reference
    }
    headers = {
        "Authorization": f"Bearer {KORAPAY_SECRET_KEY}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(f"{KORAPAY_API_BASE_URL}/collections/pay", json=payload, headers=headers)
        response.raise_for_status()
        kora_data = response.json()

        if kora_data.get('status') == 'success':
            return jsonify({
                'status': 'success',
                'checkout_url': kora_data['data']['checkout_url']
            })
        else:
            new_transaction.status = 'failed'
            db.session.commit()
            return jsonify({'message': kora_data.get('message', 'Failed to initiate payment')}), 400

    except requests.exceptions.RequestException as e:
        print(f"Error initiating Korapay payment: {e}")
        new_transaction.status = 'failed'
        db.session.commit()
        return jsonify({'message': 'Failed to connect to payment gateway'}), 500

# NEW: Webhook endpoint to receive payment confirmation from Korapay
@app.route('/api/korapay_webhook', methods=['POST'])
def korapay_webhook():
    payload = request.get_data()
    signature_header = request.headers.get('X-Kora-Signature')

    if not signature_header or not KORAPAY_WEBHOOK_SECRET:
        return jsonify({'message': 'Missing signature or webhook secret'}), 400

    # Verify webhook signature (using HMAC-SHA256)
    hash_object = hmac.new(
        bytes(KORAPAY_WEBHOOK_SECRET, 'utf-8'),
        msg=payload,
        digestmod=hashlib.sha256
    )
    expected_signature = hash_object.hexdigest()

    if expected_signature != signature_header:
        print(f"Webhook signature mismatch. Expected: {expected_signature}, Received: {signature_header}")
        return jsonify({'message': 'Invalid signature'}), 403

    try:
        data = request.json
        if data['event'] == 'charge.success':
            reference = data['data']['reference']
            transaction = PaymentTransaction.query.filter_by(transaction_reference=reference).first()

            if transaction and transaction.status == 'pending':
                transaction.status = 'success'
                survey_data = transaction.survey_data

                # Create the Survey record
                user_tg_id = survey_data.get('tg_id')
                user = User.query.filter_by(tg_id=user_tg_id).first()
                if not user:
                    return jsonify({'message': 'User not found for transaction'}), 404

                survey_cost = survey_data.get('total_cost')
                new_survey = Survey(
                    title=survey_data.get('surveyName'),
                    description=survey_data.get('description'),
                    duration=survey_data.get('duration'),
                    requester_id=user.id,
                    reward_per_response=survey_data.get('reward_per_response'),
                    desired_responses=survey_data.get('desired_responses'),
                    responder_link=survey_data.get('responder_link'),
                    sheet_link=survey_data.get('sheet_link'),
                    total_responses=0,
                    status="active",
                    cost=survey_cost,
                    apply_filter=survey_data.get('apply_filter'),
                    filters=survey_data.get('filters'),
                    views=0
                )
                db.session.add(new_survey)
                db.session.commit()
                print(f"Webhook: Successfully created survey {new_survey.title} for user {user.tg_id}")
                return jsonify({'status': 'ok'}), 200

            else:
                return jsonify({'message': 'Transaction already processed or not found'}), 200

        elif data['event'] == 'charge.failed':
            reference = data['data']['reference']
            transaction = PaymentTransaction.query.filter_by(transaction_reference=reference).first()
            if transaction:
                transaction.status = 'failed'
                db.session.commit()
                print(f"Webhook: Payment failed for transaction {reference}")
                return jsonify({'status': 'ok'}), 200

        return jsonify({'message': 'Event type not handled'}), 200

    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({'message': 'Internal Server Error'}), 500




#EDIT NICHE
@app.route('/api/update_multiple_niches/<int:survey_id>', methods=['POST'])
def update_multiple_niches(survey_id):
    try:
        data = request.json
        tg_id = data.get('tg_id')
        updated_niches = data.get('updated_niches')

        survey = Survey.query.get(survey_id)
        if not survey:
            return jsonify({"error": "Survey not found"}), 404

        # Verify the user has ownership
        user = User.query.filter_by(tg_id=str(tg_id)).first()
        if not user or user.id != survey.user_id:
            return jsonify({"error": "Unauthorized"}), 403

        current_filters = survey.filters_json if survey.filters_json else []

        # Update each niche in the list
        for niche_data in updated_niches:
            current_filter_data = niche_data.get('current_filter_data')
            new_gender = niche_data.get('new_gender')
            new_option_id = int(niche_data.get('new_option_id')) # Ensure this is an integer

            # Find the correct filter dictionary to update using option_id and filter_by
            found = False
            for i, filter_dict in enumerate(current_filters):
                if (filter_dict.get('option_id') == current_filter_data.get('option_id') and
                    filter_dict.get('filter_by') == current_filter_data.get('filter_by')):
                    # Update the found filter
                    current_filters[i]['gender'] = new_gender
                    current_filters[i]['option_id'] = new_option_id
                    found = True
                    break

            if not found:
                # This case should not happen if the flow is correct, but is good practice
                return jsonify({"error": "Current niche not found in survey filters"}), 404

        # Assign the modified list back to the survey object
        survey.filters_json = current_filters
        print(f"DEBUG: Filters JSON before commit: {survey.filters_json}")
        flag_modified(survey, "filters_json")
        db.session.add(survey)
        db.session.commit() # This line was missing

        return jsonify({"message": "Niche updated successfully"}), 200

    except Exception as e:
        db.session.rollback() # This is crucial for handling errors
        print(f"Error updating niche: {e}")
        return jsonify({"error": "Internal server error"}), 500

@app.route('/api/get_survey_details/<int:survey_id>', methods=['GET'])
def get_survey_details(survey_id):
    try:
        data = request.get_json()
        tg_id = data.get('tg_id')

        user = User.query.filter_by(tg_id=str(tg_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        survey = Survey.query.filter_by(id=survey_id, user_id=user.id).first()
        if not survey:
            return jsonify({"error": "Survey not found or you do not have permission to view it"}), 404

        responses_count = get_response_count_from_sheet(survey.sheet_link)

        niches = []
        raw_filters = []
        if survey.apply_filter and isinstance(survey.filters_json, list) and survey.filters_json:
            for filter_dict in survey.filters_json:
                gender = filter_dict.get('gender', '').lower()
                filter_by = filter_dict.get('filter_by', '').lower()

                # Store the raw filter data
                raw_filters.append(filter_dict)

                option_name = None
                if filter_by == 'college':
                    option = College.query.filter_by(id=filter_dict.get('option_id')).first()
                    if option:
                        option_name = option.name
                elif filter_by == 'department':
                    option = Department.query.filter_by(id=filter_dict.get('option_id')).first()
                    if option:
                        option_name = option.name
                elif filter_by == 'course':
                    option = Course.query.filter_by(id=filter_dict.get('option_id')).first()
                    if option:
                        option_name = option.name

                if option_name:
                    if gender == 'both':
                        niches.append(f"{option_name} students")
                    elif gender == 'male':
                        niches.append(f"{option_name} males")
                    elif gender == 'female':
                        niches.append(f"{option_name} females")
                    else:
                        niches.append(option_name)

        if not niches:
            niche_string = "Everyone"
        else:
            niche_string = ', '.join(niches)

        return jsonify({
            "survey": {
                "id": survey.id,
                "title": survey.title,
                "description": survey.description,
                "response_count": responses_count,
                "response_limit": survey.responses,
                "responder_link": survey.responder_link,
                "niche": niche_string,
                "raw_filters": raw_filters,
                "created_at": survey.created_at.isoformat() if survey.created_at else None
            }
        }), 200

    except Exception as e:
        print(f"Error getting survey details: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500

@app.route('/api/get_niche_options/<string:filter_by_type>', methods=['GET'])
def get_niche_options(filter_by_type):
    try:
        options = []
        if filter_by_type == 'college':
            colleges = College.query.all()
            options = [{'name': college.name, 'value': college.id} for college in colleges]
        elif filter_by_type == 'department':
            departments = Department.query.all()
            options = [{'name': department.name, 'value': department.id} for department in departments]
        elif filter_by_type == 'course':
            courses = Course.query.all()
            options = [{'name': course.name, 'value': course.id} for course in courses]

        return jsonify({"options": options}), 200

    except Exception as e:
        print(f"Error fetching niche options for {filter_by_type}: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500





#DISCONTINUE SURVEY
@app.route('/api/delete_survey/<int:survey_id>', methods=['DELETE'])
def api_delete_survey(survey_id):
    survey = db.session.get(Survey, survey_id)
    if not survey:
        return jsonify({'error': 'Survey not found'}), 404

    try:
        db.session.delete(survey)
        db.session.commit()
        return jsonify({'message': 'Survey discontinued successfully'})
    except Exception as e:
        db.session.rollback()
        print("❌ Survey deletion error:", e)
        return jsonify({'error': 'Database error. Try again'}), 500




#VIEW MY SURVEYS
@app.route('/api/my_surveys/<int:tg_id>')
def my_surveys(tg_id):
    print(f"DEBUG: my_surveys endpoint hit for tg_id: {tg_id}") # Add this
    user = User.query.filter_by(tg_id=str(tg_id)).first() # NECESSARY CHANGE: Convert tg_id to string
    if not user:
        print(f"DEBUG: User with tg_id {tg_id} not found.") # Add this
        return jsonify([]), 200

    print(f"DEBUG: Found user {user.id}, fetching surveys.") # Add this
    surveys = Survey.query.filter_by(user_id=user.id).all()
    print(f"DEBUG: Found {len(surveys)} surveys for user {user.id}.") # Add this

    surveys_data = []
    for s in surveys:
        try:
            print(f"DEBUG: Processing survey ID {s.id}, title: {s.title}") # Add this
            current_responses = get_response_count_from_sheet(s.sheet_link)
            print(f"DEBUG: Survey {s.id} responses: {current_responses}") # Add this
            status = "Complete" if current_responses >= s.responses else "Incomplete"

            niche_display = "No specific niche"
            levels_display = ""  # Initialize here, will be populated if filters exist

            if s.filters_json:
                filter_descriptions = []
                unique_levels = set()

                for f in s.filters_json:
                    institution_name = db.session.get(Institution, f.get('institution_id')).name if f.get(
                        'institution_id') else 'N/A'
                    filter_by_type = f.get('filter_by')
                    option_name = 'N/A'

                    if filter_by_type == 'college':
                        option_name = db.session.get(College, f.get('option_id')).name if f.get('option_id') else 'N/A'
                    elif filter_by_type == 'department':
                        option_name = db.session.get(Department, f.get('option_id')).name if f.get(
                            'option_id') else 'N/A'
                    elif filter_by_type == 'course':
                        option_name = db.session.get(Course, f.get('option_id')).name if f.get('option_id') else 'N/A'

                    level_val = f.get('level')
                    if level_val:
                        unique_levels.add(level_val)

                    desc_parts = []
                    if institution_name != 'N/A': desc_parts.append(institution_name)
                    if filter_by_type and option_name != 'N/A': desc_parts.append(
                        f"{filter_by_type.capitalize()}: {option_name}")
                    if f.get('gender') and f['gender'] != 'Both': desc_parts.append(f"Gender: {f['gender']}")
                    if f.get('role') and f['role'] != 'All': desc_parts.append(f"Role: {f['role']}")

                    if desc_parts:
                        filter_descriptions.append(", ".join(desc_parts))

                if filter_descriptions:
                    niche_display = "; ".join(filter_descriptions)

                if unique_levels:
                    sorted_levels = sorted(list(unique_levels), key=lambda x: int(x) if x.isdigit() else x)
                    levels_display = ", ".join(sorted_levels)
                else:
                    levels_display = "All"
            else:
                niche_display = "Everyone"
                levels_display = "Everyone"

            date_uploaded_str = s.created_at.strftime("%Y-%m-%d") if s.created_at else "N/A"

            surveys_data.append({
                'id': s.id,
                'title': s.title,
                'description': s.description,
                'duration': s.duration,
                'reward': s.reward,
                'responses': current_responses,
                'target': s.responses,
                'status': status,
                'niche': niche_display,
                'levels': levels_display,
                'responder_link': s.responder_link,
                'sheet_link': s.sheet_link,
                'date_uploaded': date_uploaded_str
            })
        except Exception as e:
            print(f"❌ Error processing survey ID {s.id} for user {tg_id}: {e}")
            continue
    print(f"DEBUG: Returning {len(surveys_data)} processed surveys.") # Add this
    return jsonify(surveys_data), 200

@app.route("/api/my_survey_by_id/<int:survey_id>", methods=["GET"])
def get_my_survey_by_id(survey_id):
    """
    Retrieves a single survey by its ID.
    """
    try:
        tg_id = request.args.get("tg_id", type=int)
        if not tg_id:
            return jsonify({"error": "tg_id parameter is required"}), 400

        user = User.query.filter_by(tg_id=str(tg_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        survey = Survey.query.filter_by(id=survey_id, user_id=user.id).first()

        if not survey:
            return jsonify({"error": "Survey not found or you do not have permission to view it"}), 404

        # Initialize display strings
        niche_display = "Everyone"
        levels_display = "Everyone"

        # Check for filters and process them
        if survey.filters_json:
            filter_descriptions = []
            unique_levels = set()

            for f in survey.filters_json:
                institution_name = db.session.get(Institution, f.get('institution_id')).name if f.get(
                    'institution_id') else 'N/A'
                filter_by_type = f.get('filter_by')
                option_name = 'N/A'

                if filter_by_type == 'college':
                    option_name = db.session.get(College, f.get('option_id')).name if f.get('option_id') else 'N/A'
                elif filter_by_type == 'department':
                    option_name = db.session.get(Department, f.get('option_id')).name if f.get('option_id') else 'N/A'
                elif filter_by_type == 'course':
                    option_name = db.session.get(Course, f.get('option_id')).name if f.get('option_id') else 'N/A'

                level_val = f.get('level')
                if level_val:
                    unique_levels.add(level_val)

                desc_parts = []
                if institution_name != 'N/A': desc_parts.append(institution_name)
                if filter_by_type and option_name != 'N/A': desc_parts.append(
                    f"{filter_by_type.capitalize()}: {option_name}")
                if f.get('gender') and f['gender'] != 'Both': desc_parts.append(f"Gender: {f['gender']}")
                if f.get('role') and f['role'] != 'All': desc_parts.append(f"Role: {f['role']}")

                if desc_parts:
                    filter_descriptions.append(", ".join(desc_parts))

            if filter_descriptions:
                niche_display = "; ".join(filter_descriptions)

            if unique_levels:
                sorted_levels = sorted(list(unique_levels), key=lambda x: int(x) if x.isdigit() else x)
                levels_display = ", ".join(sorted_levels)

        current_responses = get_response_count_from_sheet(survey.sheet_link)
        survey_data = {
            "id": getattr(survey, 'id', None),
            "title": getattr(survey, 'title', None),
            "description": getattr(survey, 'description', None),
            "reward": getattr(survey, 'reward', None),
            "duration": getattr(survey, 'duration', None),
            "target": getattr(survey, 'responses', 0),
            "responses": current_responses,
            "responder_link": getattr(survey, 'responder_link', None),
            "sheet_link": getattr(survey, 'sheet_link', None),
            "created_at": getattr(survey, 'created_at', None).isoformat() if getattr(survey, 'created_at',
                                                                                     None) else None,
            "niche": niche_display,
            "levels": levels_display
        }
        return jsonify(survey_data), 200

    except Exception as e:
        print(f"Error fetching survey by ID: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500




#ANSWER SURVEYS
@app.route('/api/eligible_surveys/<tg_id>')
def eligible_surveys(tg_id):
    user = User.query.filter_by(tg_id=tg_id).first()
    if not user:
        return jsonify({'surveys': []})

    all_surveys = Survey.query.all()
    eligible = []
    user_email_lower = user.email.lower()

    user_profile = {
        'institution_id': user.institution_id,
        'college_id': user.college_id,
        'department_id': user.department_id,
        'course_id': user.course_id,
        'gender': user.gender,
        'level': user.level
    }

    for s in all_surveys:
        # Check if the user is the creator of the survey
        if user.id == s.user_id:
            print(f"DEBUG: Skipping survey {s.id} because user {user.id} is the creator.")
            continue

        # --- CORRECTED LOGIC TO CHECK FOR EXISTING RESPONSES ---
        try:
            # Fetch all entries (emails and timestamps)
            sheet_entries = get_response_count_from_sheet(s.sheet_link, include_emails=True, include_timestamps=True)

            # Check if the user's email exists in any of the returned dictionaries
            has_responded = any(entry.get('email') == user_email_lower for entry in sheet_entries)

            if has_responded:
                print(f"DEBUG: User {user.tg_id} already responded to survey {s.id}.")
                continue  # Skip this survey
            else:
                print(f"DEBUG: User {user.tg_id} has not yet responded to survey {s.id}.")
        except Exception as e:
            print(f"ERROR: Failed to get sheet entries for survey {s.id} (link: {s.sheet_link}): {e}")
            continue

        # --- The rest of your filter logic is correct and remains unchanged ---
        is_eligible_for_survey = False
        if not s.apply_filter or not s.filters_json:
            is_eligible_for_survey = True
        else:
            print(f"DEBUG: Applying filters for survey {s.id}. Filters: {s.filters_json}")
            for survey_filter in s.filters_json:
                filter_match = True

                institution_filter = survey_filter.get('institution_id')
                if institution_filter and user_profile['institution_id'] != institution_filter:
                    filter_match = False

                gender_filter = survey_filter.get('gender')
                if filter_match and gender_filter and gender_filter != 'Both' and user_profile[
                    'gender'] != gender_filter:
                    filter_match = False

                filter_by_type = survey_filter.get('filter_by')
                option_id_filter = survey_filter.get('option_id')

                if filter_match and filter_by_type and option_id_filter:
                    if filter_by_type == 'college' and user_profile['college_id'] != option_id_filter:
                        filter_match = False
                    elif filter_by_type == 'department' and user_profile['department_id'] != option_id_filter:
                        filter_match = False
                    elif filter_by_type == 'course' and user_profile['course_id'] != option_id_filter:
                        filter_match = False

                level_filter = survey_filter.get('level')
                if filter_match and level_filter and level_filter != 'All' and user_profile['level'] != level_filter:
                    filter_match = False

                if filter_match:
                    is_eligible_for_survey = True
                    print(f"DEBUG: User {user.tg_id} matched a filter for survey {s.id}.")
                    break
            if not is_eligible_for_survey:
                print(f"DEBUG: User {user.tg_id} did not match any filter for survey {s.id}.")

        if is_eligible_for_survey:
            current_responses_count = len(sheet_entries) if sheet_entries is not None else 0
            if s.responder_link:
                eligible.append({
                    'title': s.title,
                    'description': s.description,
                    'reward': s.reward,
                    'duration': s.duration,
                    "responder_link": s.responder_link,
                    'responses': current_responses_count,
                    'target': s.responses,
                    "survey_id": s.id
                })

    eligible.sort(key=lambda x: x['reward'], reverse=True)
    return jsonify({'surveys': eligible})

@app.route('/api/verify_sheet_access', methods=['POST'])
def verify_sheet_access():
    data = request.json
    sheet_link = data.get("sheet_link")

    if not sheet_link:
        return jsonify({"verified": False, "reason": "No sheet link provided."}), 400

    try:
        # Attempt to access the sheet. We don't need the data, just to see if it errors.
        _ = get_response_count_from_sheet(sheet_link, include_emails=False)
        return jsonify({"verified": True}), 200
    except Exception as e:
        print(f"Error verifying sheet access for {sheet_link}: {e}")
        return jsonify({"verified": False, "reason": f"Failed to access sheet: {str(e)}"}), 500

# app.py
@app.route('/api/check_entry', methods=['POST'])
def check_entry():
    data = request.json
    tg_id = str(data.get("tg_id"))
    incoming_responder_link = data.get("form_link")
    start_time_str = data.get("start_time")

    print("Start time string: ", start_time_str)

    user = User.query.filter_by(tg_id=tg_id).first()
    if not user:
        return jsonify({"verified": False, "reason": "User not found."}), 404

    incoming_id = extract_file_id(incoming_responder_link)

    surveys = Survey.query.all()
    survey = next((s for s in surveys if extract_file_id(s.responder_link) == incoming_id), None)
    if not survey:
        return jsonify({"verified": False, "reason": "Survey not found or link mismatch."}), 404

    if not survey.sheet_link:
        return jsonify({"verified": False, "reason": "Survey is missing sheet link."}), 400

    try:
        # The bot is already sending an ISO format timestamp with timezone info
        start_time = datetime.fromisoformat(start_time_str).astimezone(timezone.utc)
    except ValueError:
        return jsonify({"verified": False, "reason": "Invalid start time format received from bot."}), 400

    time_elapsed = (datetime.now(timezone.utc) - start_time).total_seconds()

    try:
        duration_minutes = float(survey.duration)
        min_time_required = duration_minutes * 60
    except (ValueError, TypeError):
        return jsonify({"verified": False, "reason": "Invalid survey duration format. Contact support."}), 400

    if time_elapsed < min_time_required:
        return jsonify({"verified": False,
                        "reason": f"You submitted the survey too quickly ({int(time_elapsed)}s < {int(min_time_required)}s). Please allow at least {duration_minutes} minutes."}), 400

    entries = get_response_count_from_sheet(survey.sheet_link, include_emails=True, include_timestamps=True)

    if not entries:
        print(f"DEBUG: No entries found in the sheet for survey {survey.id}.")
        return jsonify({"verified": False, "reason": "No entries found in the response sheet."}), 404

    found_valid_entry = False
    user_email_lower = user.email.lower()

    # Define the timezones explicitly.
    # We assume the Google Sheet is set to Lagos/UTC+1.
    sheet_timezone = timezone(timedelta(hours=1))

    timestamp_formats = [
        '%m/%d/%Y %H:%M:%S',
        '%d/%m/%Y %H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%m/%d/%Y %H:%M:%S %p'
    ]

    for entry in entries:
        if 'email' in entry and entry.get('email').lower() == user_email_lower:
            raw_timestamp = entry.get('timestamp')
            if not raw_timestamp:
                continue

            entry_time = None
            for fmt in timestamp_formats:
                try:
                    # Parse the timestamp as a naive datetime object first
                    naive_entry_time = datetime.strptime(raw_timestamp, fmt)
                    # Correctly set its timezone to the sheet's timezone (e.g., UTC+1)
                    entry_time = naive_entry_time.replace(tzinfo=sheet_timezone)
                    # Now convert the entry time to UTC for a direct comparison with start_time
                    entry_time_utc = entry_time.astimezone(timezone.utc)
                    print(f"DEBUG: Successfully parsed and converted timestamp '{raw_timestamp}' to UTC: '{entry_time_utc}'.")
                    break
                except ValueError:
                    continue

            if entry_time_utc:
                print(f"DEBUG: Comparing times for user {user.tg_id}:")
                print(f"  Start Time (from bot session): {start_time}")
                print(f"  Entry Time (from Google Sheet): {entry_time_utc}")

                # Crucial Fix: Only a new entry's timestamp will be after the start time.
                if entry_time_utc > start_time:
                    found_valid_entry = True
                    break  # Found a valid entry, no need to check others
                else:
                    print(f"DEBUG: Entry found but timestamp ({entry_time_utc}) is not after start_time ({start_time}).")
            else:
                print(f"ERROR: Could not parse timestamp '{raw_timestamp}' from sheet for user {user.email}.")
                return jsonify({"verified": False,
                                "reason": f"Could not parse the timestamp from the response sheet. The timestamp format may be unexpected: '{raw_timestamp}'."}), 400

    if not found_valid_entry:
        return jsonify({"verified": False,
                        "reason": "We couldn't find a new entry in the response sheet that was submitted after you started the survey. Please ensure you submitted the survey and used the correct email."}), 404

    user.wallet += survey.reward
    db.session.commit()

    return jsonify({"verified": True, "reward": survey.reward})

@app.route("/api/survey_by_id/<int:survey_id>", methods=['GET'])
def get_survey_by_id(survey_id):
    survey = db.session.get(Survey, survey_id)
    if not survey:
        return jsonify({"error": "Survey not found"}), 404

    # The filter logic is now moved here, so the bot gets fresh data
    niche_display = "No specific niche"
    levels_display = ""

    if survey.apply_filter and survey.filters_json:
        filter_descriptions = []
        unique_levels = set()

        for f in survey.filters_json:
            institution_name = db.session.get(Institution, f.get('institution_id')).name if f.get(
                'institution_id') else 'N/A'
            filter_by_type = f.get('filter_by')
            option_name = 'N/A'

            if filter_by_type == 'college':
                option_name = db.session.get(College, f.get('option_id')).name if f.get('option_id') else 'N/A'
            elif filter_by_type == 'department':
                option_name = db.session.get(Department, f.get('option_id')).name if f.get('option_id') else 'N/A'
            elif filter_by_type == 'course':
                option_name = db.session.get(Course, f.get('option_id')).name if f.get('option_id') else 'N/A'

            level_val = f.get('level')
            if level_val:
                unique_levels.add(level_val)

            desc_parts = []
            if institution_name != 'N/A': desc_parts.append(institution_name)
            if filter_by_type and option_name != 'N/A': desc_parts.append(
                f"{filter_by_type.capitalize()}: {option_name}")
            if f.get('gender') and f['gender'] != 'Both': desc_parts.append(f"Gender: {f['gender']}")
            if f.get('role') and f['role'] != 'All': desc_parts.append(f"Role: {f['role']}")

            if desc_parts:
                filter_descriptions.append(", ".join(desc_parts))

        if filter_descriptions:
            niche_display = "; ".join(filter_descriptions)

        if unique_levels:
            sorted_levels = sorted(list(unique_levels), key=lambda x: int(x) if x.isdigit() else x)
            levels_display = f"Levels: ({', '.join(sorted_levels)})"

    try:
        current_responses = get_response_count_from_sheet(survey.sheet_link)
    except:
        current_responses = 0

    return jsonify({
        "survey_id": survey.id,
        "title": survey.title,
        "responses": current_responses,
        "description": survey.description,
        "reward": survey.reward,
        "duration": survey.duration,
        "responder_link": survey.responder_link,
        "sheet_link": survey.sheet_link,
        "target": survey.responses,
        "filters_json": survey.filters_json,
        'niche': niche_display,
        'levels': levels_display
    })




#AI ANALYSIS
@app.route('/api/get_survey_data/<int:survey_id>', methods=['POST'])
def get_survey_data(survey_id):
    try:
        tg_id = request.get_json().get('tg_id')
        if not tg_id:
            return jsonify({"error": "tg_id parameter is required"}), 400

        user = User.query.filter_by(tg_id=str(tg_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        survey = Survey.query.filter_by(id=survey_id, user_id=user.id).first()
        if not survey:
            return jsonify({"error": "Survey not found or you do not have permission to view it"}), 404

        data = get_all_survey_data_from_sheet(survey.sheet_link)

        return jsonify({
            "data": data,
            "title": survey.title,
            "description": survey.description
        }), 200

    except Exception as e:
        print(f"Error fetching survey data: {e}")
        return jsonify({"error": "An internal server error occurred"}), 500

@app.route('/api/analyze_survey_with_ai/<int:survey_id>', methods=['POST'])
def analyze_survey_with_ai(survey_id):
    try:
        data = request.get_json()
        tg_id = data.get('tg_id')

        # Fix: Convert the integer tg_id to a string before the query
        if tg_id:
            tg_id = str(tg_id)

        user = User.query.filter_by(tg_id=tg_id).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        survey = Survey.query.filter_by(id=survey_id, user_id=user.id).first()
        if not survey:
            return jsonify({"error": "Survey not found or you do not have permission to view it"}), 404

        # Fetch the survey data from the sheet using the new function
        try:
            survey_data = get_all_survey_data(survey.sheet_link)
        except Exception as e:
            return jsonify({"error": f"Failed to retrieve survey data: {e}"}), 500

        if not survey_data:
            return jsonify({"analysis": "The survey sheet is empty. No analysis can be performed."}), 200

        # Create a detailed prompt for the AI model
        prompt = f"""
        You are an expert survey data analyst.

        Analyze the following survey data and provide a concise summary, key findings, and actionable recommendations.

        Survey Title: {survey.title}
        Survey Description: {survey.description}
        Number of Responses: {len(survey_data)}

        Raw Data:
        {json.dumps(survey_data, indent=2)}

        Provide your analysis in a structured, easy-to-read format.
        """

        # Call the AI model
        try:
            model = genai.GenerativeModel('gemini-1.5-flash')
            response = model.generate_content(prompt)
            ai_analysis = response.text
        except Exception as e:
            return jsonify({"error": f"AI model error: {e}"}), 500

        return jsonify({
            "analysis": ai_analysis
        }), 200

    except Exception as e:
        # This will catch any other unexpected errors and return a proper JSON response
        print(f"Error during AI analysis: {e}")
        return jsonify({
            "error": "An internal server error occurred during AI analysis."
        }), 500

@app.route('/api/ai_chat/<int:survey_id>', methods=['POST'])
def ai_chat(survey_id):
    try:
        data = request.get_json()
        tg_id = data.get('tg_id')
        user_query = data.get('user_query', '')
        survey_data = data.get('survey_data', [])
        conversation_history = data.get('conversation_history', [])

        if not tg_id or not user_query:
            return jsonify({"error": "Missing user ID or query"}), 400

        user = User.query.filter_by(tg_id=str(tg_id)).first()
        if not user:
            return jsonify({"error": "User not found"}), 404

        survey = Survey.query.filter_by(id=survey_id, user_id=user.id).first()
        if not survey:
            return jsonify({"error": "Survey not found or you do not have permission to view it"}), 404

        df = pandas.DataFrame(survey_data)
        response_text = ""

        # Simple Statistical Analysis with Pandas
        query_lower = user_query.lower()

        # Check for simple queries first to avoid unnecessary AI calls
        if 'average' in query_lower or 'mean' in query_lower:
            numeric_cols = df.select_dtypes(include=['number']).columns
            if not numeric_cols.empty:
                averages = df[numeric_cols].mean().to_dict()
                response_text = "Here are the averages of the numeric columns:\n"
                for col, val in averages.items():
                    response_text += f"- {col}: {val:.2f}\n"
            else:
                response_text = "I couldn't find any numeric data to calculate the average."

        elif 'most frequent' in query_lower or 'common' in query_lower:
            common_answers = {}
            for col in df.columns:
                if df[col].dtype == 'object':
                    mode = df[col].mode()
                    if not mode.empty:
                        common_answers[col] = mode[0]
            if common_answers:
                response_text = "Here are the most common answers for each category:\n"
                for col, val in common_answers.items():
                    response_text += f"- {col}: {val}\n"
            else:
                response_text = "I couldn't find any categorical data to analyze."

        else:
            # Default to AI analysis for other queries
            system_instruction = f"""
                You are a specialized AI assistant for Survey Hustler, a Telegram bot designed for students of Covenant University (CU).
                Your primary function is to serve as a statistical and analytical chatbot.

                **Your Purpose:**
                - To provide analysis on survey data uploaded by final-year CU students (Survey Creators).
                - To assist CU students (Survey Respondents) with inquiries about platform features and how to get responses, earn money, etc.

                **Your Knowledge is Strictly Limited to:**
                1.  The specific survey data provided for this session.
                2.  General concepts in statistics and data analysis.
                3.  Information about the Survey Hustler platform, its features, and how users interact with it.

                **Survey Hustler Features and Information:**
                - **Platform:** A Telegram bot designed for students of Covenant University (CU).
                - **Survey Creators:** Final-year CU students who upload surveys and specify a payment per respondent[cite: 8].
                - **Survey Respondents:** Other CU students who answer surveys to earn money, with matching based on biodata[cite: 9].
                - **Key Features:** Upload surveys, answer surveys, redeem cash, view and analyze surveys, and get customer support[cite: 16, 21, 23, 24, 34, 54, 63, 71, 84, 91].
                - **Getting more responses:** A user can get more responses by uploading their survey to the platform using the 'Upload Surveys' feature[cite: 34].

                **Important Rules:**
                - You **must not** answer questions outside of this scope.
                - If a user asks a question about an unrelated topic (e.g., "why is the sky blue?"), you must politely decline and state your purpose. Example response: "I'm sorry, but I am a statistical bot for Survey Hustler. My knowledge is limited to data analysis and the features of this platform."

                Survey Title: {survey.title}
                Survey Description: {survey.description}
                Number of Responses: {len(survey_data)}
                Raw Data:
                {json.dumps(survey_data, indent=2)}

                User's Query: {user_query}

                Based on the raw data, conversation history, and your knowledge of Survey Hustler, provide a concise and accurate response to the user's query.
            """

            try:
                model = genai.GenerativeModel('gemini-1.5-flash')
                response = model.generate_content(system_instruction)
                response_text = response.text
            except Exception as e:
                return jsonify({"error": f"AI model error: {e}"}), 500

        return jsonify({"analysis": response_text}), 200

    except Exception as e:
        print(f"Error during AI chat analysis: {e}")
        return jsonify({"error": "An internal server error occurred during AI analysis."}), 500





# Create your API endpoints for fetching dropdown data (Add these routes)
@app.route('/api/get_institutions', methods=['GET'])
def get_institutions():
    institutions = Institution.query.all()
    return jsonify([{'id': inst.id, 'name': inst.name} for inst in institutions])

@app.route('/api/get_colleges/<int:institution_id>', methods=['GET'])
def get_colleges(institution_id):
    colleges = College.query.filter_by(institution_id=institution_id).all()
    return jsonify([{'id': col.id, 'name': col.name} for col in colleges])

@app.route('/api/get_departments/<int:college_id>', methods=['GET'])
def get_departments(college_id):
    departments = Department.query.filter_by(college_id=college_id).all()
    return jsonify([{'id': dept.id, 'name': dept.name} for dept in departments])

@app.route('/api/get_courses/<int:department_id>', methods=['GET'])
def get_courses(department_id):
    courses = Course.query.filter_by(department_id=department_id).all()
    return jsonify([{'id': course.id, 'name': course.name} for course in courses])

@app.route('/api/get_levels/<string:filter_by_type>/<int:option_id>', methods=['GET'])
def get_levels(filter_by_type, option_id):
    levels = set() # Use a set to store unique level values (e.g., '100', '200')

    if filter_by_type == 'course':
        course = db.session.get(Course, option_id)
        if course:
            for lvl in course.levels:
                levels.add(lvl.value)
    elif filter_by_type == 'department':
        department = db.session.get(Department, option_id)
        if department:
            for course in department.courses:
                for lvl in course.levels:
                    levels.add(lvl.value)
    elif filter_by_type == 'college':
        college = db.session.get(College, option_id)
        if college:
            for department in college.departments:
                for course in department.courses:
                    for lvl in course.levels:
                        levels.add(lvl.value)
    else:
        pass # Returning an empty list if not a recognized filter type/ID

    # Convert set to sorted list for consistent order
    sorted_levels = sorted(list(levels), key=lambda x: int(x) if x.isdigit() else x)
    return jsonify([{'value': lvl, 'name': lvl} for lvl in sorted_levels] + [{'value': 'All', 'name': 'All'}]) # Include 'All' as a general option

# --- End of Filter Option Endpoints ---



# --------------------- START ---------------------
if __name__ == '__main__':
    app.run(debug=True)

