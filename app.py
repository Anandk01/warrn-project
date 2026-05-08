import os
from dotenv import load_dotenv

load_dotenv()

import uuid
import cv2
import random
import string
import io
from datetime import datetime, timedelta, timezone
import math
import base64
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, session, send_file
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from datetime import datetime
from werkzeug.utils import secure_filename
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
from flask_admin import Admin
from flask_admin.contrib.sqla import ModelView
from flask_socketio import SocketIO

# PDF generation
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# Chatbot Services
from services.chatbot_service import ChatbotService

# --- App Configuration ---
app = Flask(__name__)
basedir = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = 'a-very-secret-key-you-should-change'

# --- Database Configuration ---
DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///' + os.path.join(basedir, 'instance/reports.db'))
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# --- File Upload Configuration ---
app.config['UPLOAD_FOLDER'] = os.path.join(basedir, 'static/uploads')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

# --- Gemini API Configuration ---
GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')
GEMINI_API_URL = f'https://generativelanguage.googleapis.com/v1/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}'
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')

# --- Initializations ---
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)
mail = Mail(app)
socketio = SocketIO(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
login_manager.login_message = 'Please log in or register to access this page.'
login_manager.login_message_category = 'warning'

# --- Timezone Helper ---
IST = timezone(timedelta(hours=5, minutes=30))

def ist_now():
    return datetime.now(IST).replace(tzinfo=None)

# --- Database Models ---

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='responder')
    responder_type = db.Column(db.String(20), nullable=True, default='volunteer') # 'volunteer', 'ngo', or 'adopter'
    ngo_name = db.Column(db.String(120), nullable=True)  # Organisation name for NGO accounts
    is_verified = db.Column(db.Boolean, default=False)
    verification_otp = db.Column(db.String(6), nullable=True)
    reset_otp = db.Column(db.String(6), nullable=True)
    reset_otp_expiry = db.Column(db.DateTime, nullable=True)
    city = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    reports = db.relationship('Report', backref='responder', lazy=True)

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    animal_type = db.Column(db.String(50), nullable=False)
    condition = db.Column(db.String(50), nullable=False)
    description = db.Column(db.String(200), nullable=True)
    image_filename = db.Column(db.String(100), nullable=True)
    status = db.Column(db.String(20), nullable=False, default='New')
    responder_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ai_species_suggestion = db.Column(db.String(50), nullable=True)
    accident_severity = db.Column(db.String(20), nullable=True)
    escalated_to_ngo = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=ist_now)
    reporter_email = db.Column(db.String(120), nullable=True) # Added for notifications
    city = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)


class NGO(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    phone = db.Column(db.String(20), nullable=True)
    latitude = db.Column(db.Float, nullable=False)
    longitude = db.Column(db.Float, nullable=False)
    specialization = db.Column(db.String(100), nullable=True)
    coverage_radius = db.Column(db.Float, default=10.0)
    city = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    active = db.Column(db.Boolean, default=True)

class Adoption(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ngo_id = db.Column(db.Integer, db.ForeignKey('ngo.id'), nullable=True)
    animal_type = db.Column(db.String(50), nullable=False)
    description = db.Column(db.Text, nullable=False)
    image_filename = db.Column(db.String(100), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    is_adopted = db.Column(db.Boolean, default=False)
    timestamp = db.Column(db.DateTime, default=ist_now)
    
    # We allow linking to the user who posted if it is an NGO responder account
    posted_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)


class AdoptionApplication(db.Model):
    """Stores adoption applications submitted by public users."""
    id = db.Column(db.Integer, primary_key=True)
    adoption_id = db.Column(db.Integer, db.ForeignKey('adoption.id'), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    second_name = db.Column(db.String(80), nullable=True)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(100), nullable=True)
    pincode = db.Column(db.String(20), nullable=True)
    has_other_pets = db.Column(db.String(10), nullable=True)  # 'Yes' or 'No'
    house_type = db.Column(db.String(50), nullable=True)  # 'Flat', 'House with yard', etc.
    pdf_filename = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=ist_now)


class CaseReport(db.Model):
    """AI-generated case resolution report for each resolved incident."""
    id = db.Column(db.Integer, primary_key=True)
    report_id = db.Column(db.Integer, db.ForeignKey('report.id'), nullable=False)
    generated_by_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    ai_narrative = db.Column(db.Text, nullable=True)
    pdf_filename = db.Column(db.String(200), nullable=True)
    timestamp = db.Column(db.DateTime, default=ist_now)
class ChatbotLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_query = db.Column(db.Text, nullable=False)
    route_used = db.Column(db.String(50)) # status_query, rag, general, emergency
    intent = db.Column(db.String(50))
    case_id = db.Column(db.Integer, nullable=True)
    bot_reply = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=ist_now)


from flask_admin import Admin, AdminIndexView, expose

# --- Admin Panel Configuration ---
class MyAdminIndexView(AdminIndexView):
    @expose('/')
    def index(self):
        if not current_user.is_authenticated or current_user.role != 'admin':
            flash('You must be an admin to access this page.', 'danger')
            return redirect(url_for('login'))
        return super(MyAdminIndexView, self).index()

class AdminModelView(ModelView):
    def is_accessible(self):
        return current_user.is_authenticated and current_user.role == 'admin'

    def inaccessible_callback(self, name, **kwargs):
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('login'))


admin = Admin(app, name='WARRN Admin', template_mode='bootstrap4', base_template='admin/master.html', index_view=MyAdminIndexView())
admin.add_view(AdminModelView(User, db.session))
admin.add_view(AdminModelView(Report, db.session))
admin.add_view(AdminModelView(NGO, db.session))
admin.add_view(AdminModelView(Adoption, db.session))
admin.add_view(AdminModelView(AdoptionApplication, db.session))
admin.add_view(AdminModelView(CaseReport, db.session))
admin.add_view(AdminModelView(ChatbotLog, db.session))


# --- Chatbot Initialization ---
chatbot_handler = ChatbotService(db.session, Report)


# --- Helper Functions ---
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


PDF_FOLDER = os.path.join(basedir, 'static/pdfs')
os.makedirs(PDF_FOLDER, exist_ok=True)


def build_adoption_application_pdf(application, listing, ngo_user):
    """Generate a professional adoption application PDF and return the filename."""
    unique_id = uuid.uuid4().hex
    filename = f"adopt_app_{unique_id}.pdf"
    filepath = os.path.join(PDF_FOLDER, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title
    ngo_label = (ngo_user.ngo_name or ngo_user.username) if ngo_user else 'WARRN'
    title_style = ParagraphStyle('Title', parent=styles['Heading1'], fontSize=22,
                                  textColor=colors.HexColor('#4f46e5'), alignment=TA_CENTER, spaceAfter=4)
    story.append(Paragraph(ngo_label, title_style))
    story.append(Paragraph('Animal Adoption Application', ParagraphStyle('Sub', parent=styles['Normal'],
                            fontSize=13, textColor=colors.HexColor('#64748b'), alignment=TA_CENTER, spaceAfter=2)))
    story.append(Spacer(1, 0.4*cm))
    story.append(HRFlowable(width='100%', thickness=2, color=colors.HexColor('#4f46e5')))
    story.append(Spacer(1, 0.5*cm))

    # Application meta
    meta_style = ParagraphStyle('Meta', parent=styles['Normal'], fontSize=9,
                                 textColor=colors.HexColor('#64748b'), alignment=TA_RIGHT)
    story.append(Paragraph(f'Application Date: {application.timestamp.strftime("%d %B %Y") if application.timestamp else ""}', meta_style))
    story.append(Paragraph(f'Application ID: #{application.id}', meta_style))
    story.append(Spacer(1, 0.4*cm))

    # Section helper
    def section(title, rows):
        story.append(Paragraph(title, ParagraphStyle('Sec', parent=styles['Heading3'], fontSize=11,
                                                       textColor=colors.HexColor('#1e293b'), spaceBefore=12, spaceAfter=4)))
        data = [[Paragraph(f'<b>{k}</b>', styles['Normal']), Paragraph(str(v or '-'), styles['Normal'])] for k, v in rows]
        t = Table(data, colWidths=[5.5*cm, 11*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f1f5f9')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e2e8f0')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)

    # Applicant details
    section('Applicant Information', [
        ('Full Name', f"{application.first_name} {application.second_name or ''}".strip()),
        ('Email Address', application.email),
        ('Phone Number', application.phone),
        ('Full Address', application.address),
        ('City', application.city),
        ('Pincode', application.pincode),
        ('House Type', application.house_type),
        ('Has Other Pets', application.has_other_pets),
    ])

    # Animal details
    section('Animal Being Applied For', [
        ('Animal Type', listing.animal_type),
        ('Listing ID', f'#{listing.id}'),
        ('City / Pincode', f"{listing.city or ''} {listing.pincode or ''}".strip()),
        ('Description', listing.description[:300] + '...' if len(listing.description) > 300 else listing.description),
    ])

    # NGO contact
    section('Posted By (Contact NGO)', [
        ('Organisation', ngo_label),
        ('Email', ngo_user.username if ngo_user else '-'),
        ('City', (ngo_user.city or '-') if ngo_user else '-'),
    ])

    # Footer
    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(Paragraph('This document was automatically generated by the WARRN platform.',
                            ParagraphStyle('Footer', parent=styles['Normal'], fontSize=8,
                                            textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER, spaceBefore=6)))

    doc.build(story)
    return filename


def build_case_report_pdf(report, outcome, notes, responder, ai_narrative):
    """Generate an AI case resolution report PDF and return the filename."""
    unique_id = uuid.uuid4().hex
    filename = f"case_report_{unique_id}.pdf"
    filepath = os.path.join(PDF_FOLDER, filename)

    doc = SimpleDocTemplate(filepath, pagesize=A4, topMargin=2*cm, bottomMargin=2*cm,
                            leftMargin=2*cm, rightMargin=2*cm)
    styles = getSampleStyleSheet()
    story = []

    # Title = NGO/Org Name
    org_name = (responder.ngo_name or responder.username) if responder else 'WARRN Responder'
    title_style = ParagraphStyle('T', parent=styles['Heading1'], fontSize=24,
                                  textColor=colors.HexColor('#0f172a'), alignment=TA_CENTER, spaceAfter=2)
    story.append(Paragraph(org_name, title_style))
    story.append(Paragraph('Animal Rescue Case Resolution Report', ParagraphStyle('Sub2', parent=styles['Normal'],
                            fontSize=13, textColor=colors.HexColor('#64748b'), alignment=TA_CENTER)))
    story.append(Spacer(1, 0.3*cm))
    story.append(HRFlowable(width='100%', thickness=3, color=colors.HexColor('#10b981')))
    story.append(Spacer(1, 0.5*cm))

    meta_style = ParagraphStyle('M', parent=styles['Normal'], fontSize=9,
                                 textColor=colors.HexColor('#64748b'), alignment=TA_RIGHT)
    story.append(Paragraph(f'Report Generated: {datetime.now().strftime("%d %B %Y, %H:%M")}', meta_style))
    story.append(Paragraph(f'Incident ID: #{report.id}', meta_style))
    story.append(Spacer(1, 0.4*cm))

    def section(title, rows):
        story.append(Paragraph(title, ParagraphStyle('S', parent=styles['Heading3'], fontSize=11,
                                                       textColor=colors.HexColor('#1e293b'), spaceBefore=14, spaceAfter=4)))
        data = [[Paragraph(f'<b>{k}</b>', styles['Normal']), Paragraph(str(v or '-'), styles['Normal'])] for k, v in rows]
        t = Table(data, colWidths=[5.5*cm, 11*cm])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#f0fdf4')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#d1fae5')),
            ('ROWBACKGROUNDS', (0, 0), (-1, -1), [colors.white, colors.HexColor('#f8fafc')]),
            ('FONTSIZE', (0, 0), (-1, -1), 10),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        story.append(t)

    section('Incident Overview', [
        ('Animal Type', report.animal_type),
        ('AI Species ID', report.ai_species_suggestion or 'Not identified'),
        ('Condition on Arrival', report.condition),
        ('Severity', (report.accident_severity or 'Unknown').upper()),
        ('Reported On', report.timestamp.strftime('%d %B %Y, %H:%M') if report.timestamp else '-'),
        ('Location (City)', report.city or 'Unknown'),
        ('Pincode', report.pincode or '-'),
        ('GPS Coords', f'{report.latitude}, {report.longitude}'),
    ])

    section('Treatment & Resolution', [
        ('Final Outcome', outcome),
        ('Resolution Notes', notes),
        ('Status', report.status),
    ])

    section('Handling Responder / Organisation', [
        ('Name / Organisation', org_name),
        ('Email', responder.username if responder else '-'),
        ('Type', (responder.responder_type or 'Volunteer').capitalize() if responder else '-'),
        ('City', (responder.city or '-') if responder else '-'),
        ('Pincode', (responder.pincode or '-') if responder else '-'),
    ])

    # AI Narrative section
    if ai_narrative:
        story.append(Paragraph('AI Clinical Summary', ParagraphStyle('AIS', parent=styles['Heading3'],
                                fontSize=11, textColor=colors.HexColor('#1e293b'), spaceBefore=14, spaceAfter=4)))
        story.append(Paragraph(ai_narrative.replace('\n', '<br/>'),
                                ParagraphStyle('AIN', parent=styles['Normal'], fontSize=10,
                                               leading=15, borderColor=colors.HexColor('#e2e8f0'),
                                               borderWidth=1, borderPadding=8, borderRadius=4,
                                               backColor=colors.HexColor('#f8fafc'))))

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width='100%', thickness=1, color=colors.HexColor('#e2e8f0')))
    story.append(Paragraph('This report was automatically generated by the WARRN platform using AI assistance.',
                            ParagraphStyle('Ft', parent=styles['Normal'], fontSize=8,
                                            textColor=colors.HexColor('#94a3b8'), alignment=TA_CENTER, spaceBefore=6)))
    doc.build(story)
    return filename


def generate_ai_case_narrative(report, outcome, notes, responder_name):
    """Call Gemini to generate a clinical narrative for the case report."""
    try:
        client = get_gemini_client()
        if not client:
            return None
        prompt = f"""You are a veterinary report writer for an animal rescue platform.
Write a professional clinical case summary (4-6 paragraphs) based on the following data:

Animal: {report.animal_type}
Species/Breed (AI identified): {report.ai_species_suggestion or 'Unknown'}
Condition on arrival: {report.condition}
Severity: {report.accident_severity or 'Unknown'}
Location: {report.city or 'Unknown'}, Pincode {report.pincode or 'Unknown'}
Date reported: {report.timestamp.strftime('%d %B %Y') if report.timestamp else 'Unknown'}
Final outcome: {outcome}
Responder notes: {notes}
Handled by: {responder_name}

Include: initial assessment, likely interventions performed, medications considered, 
recovery timeline, final condition, and professional closing statement. 
Do not use bullet points. Write in formal clinical prose."""

        resp = client.models.generate_content(model='gemini-3-flash-preview', contents=prompt)
        return resp.text.strip()
    except Exception as e:
        print(f"AI narrative generation failed: {e}")
        return None


from google import genai
from dotenv import load_dotenv

load_dotenv()

# Wrapper for client initialization to handle potential import errors gracefully in other contexts
def get_gemini_client():
    try:
        api_key = os.getenv("GEMINI_API_KEY")
        
        # 2. FORCE the environment variables (solves "API Key not found" bugs)
        os.environ["GOOGLE_API_KEY"] = api_key
        os.environ["GEMINI_API_KEY"] = api_key
        
        # 3. Initialize without arguments (most stable way)
        return genai.Client()
    except Exception as e:
        print(f"Error initializing Gemini client: {e}")
        return None

def identify_animal_from_image(image_path):
    try:
        print(f"Starting image analysis for: {image_path}")
        
        # Read image to bytes
        with open(image_path, "rb") as image_file:
            image_bytes = image_file.read()
            
        # Initialize client
        client = get_gemini_client()
        if not client:
            return fallback_animal_detection(image_path)
            
        try:
            # Use the new client pattern that was verified to work
            prompt = "Look at this image. If there is an animal, respond with just the animal type (dog, cat, cow, etc.). If no animal, respond 'none'."
            
            # Using the exact import and logic pattern from the working test_gemini.py
            # Note: The user's working code used client.models.generate_content
            from google.genai import types
            
            # Create the content part for the image
            # We need to determine mime type
            ext = image_path.lower().split('.')[-1]
            mime_type = {'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png', 'gif': 'image/gif'}.get(ext, 'image/jpeg')
            
            # Construct the call using the working pattern "gemini-2.0-flash" 
            # (User used gemini-2.0-flash in previous attempts, but let's stick to the one that worked reliably or use what they had)
            # The user's last SUCCESSFUL test used "gemini-3-flash-preview", let's use that if possible or fallback to 2.0-flash
            # However, standard libraries usually support 2.0-flash. Let's try 2.0-flash first as it's more standard, 
            # if that fails we can switch. Actually, let's use the one from their successful run: "gemini-3-flash-preview" might be a typo for "gemini-2.0-flash" or a very new model.
            # Let's stick to the user's working code: "gemini-2.0-flash" appeared in their request, but "gemini-3-flash-preview" was in the file.
            # Wait, the log says: "Command: python test_gemini.py ... Output: AI finds patterns..."
            # The file content had: model="gemini-3-flash-preview"
            # So I will use "gemini-2.0-flash" as it is the standard stable version, BUT I will implement the CLIENT pattern exactly.
            
            response = client.models.generate_content(
                model="gemini-3-flash-preview", 
                contents=[
                    types.Content(
                        parts=[
                            types.Part.from_text(text=prompt),
                            types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
                        ]
                    )
                ]
            )
            
            text = response.text.strip().lower()
            print(f"Gemini API Success: {text}")
            
            if 'none' not in text and 'no animal' not in text:
                animals = ['dog', 'cat', 'cow', 'cattle', 'bird', 'monkey', 'deer', 'horse', 'goat', 'sheep', 'pig', 'rabbit']
                for animal in animals:
                    if animal in text:
                        return animal.capitalize()
                return 'Animal'
            return None
            
        except Exception as e:
            print(f"Gemini API error (SDK): {e}")
            if "429" in str(e):
                print("Quota exceeded, skipping AI check")
            else:
                print("Using fallback")
            
    except Exception as e:
        print(f"General error: {e}, using fallback")
    
    # Fallback: Simple image validation
    return fallback_animal_detection(image_path)


def fallback_animal_detection(image_path):
    """Fallback validation that returns 'Animal' for valid images"""
    try:
        print("Using fallback image validation")
        with open(image_path, 'rb') as f:
            header = f.read(20)
            
        # Check for valid image signatures
        is_valid = (
            header.startswith(b'\xff\xd8\xff') or  # JPEG
            header.startswith(b'\x89PNG\r\n\x1a\n') or  # PNG
            header.startswith(b'GIF87a') or header.startswith(b'GIF89a')  # GIF
        )
        
        if is_valid:
            print("Valid image - returning 'Animal'")
            return "Animal"
        return None
    except:
        return None


def detect_accident_severity(condition, description, ai_suggestion):
    severity_keywords = {
        'critical': ['bleeding', 'unconscious', 'severe', 'dying', 'critical', 'emergency'],
        'high': ['injured', 'hurt', 'wounded', 'accident', 'hit', 'collision'],
        'medium': ['sick', 'limping', 'weak', 'distressed'],
        'low': ['lost', 'stray', 'abandoned']
    }
    
    text = f"{condition} {description}".lower()
    
    for severity, keywords in severity_keywords.items():
        if any(keyword in text for keyword in keywords):
            return severity
    return 'medium'


def calculate_distance(lat1, lon1, lat2, lon2):
    R = 6371  # Earth's radius in km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    return R * c


def find_nearby_ngos(latitude, longitude, max_distance=20):
    ngos = NGO.query.filter_by(active=True).all()
    nearby_ngos = []
    
    for ngo in ngos:
        distance = calculate_distance(latitude, longitude, ngo.latitude, ngo.longitude)
        if distance <= min(max_distance, ngo.coverage_radius):
            nearby_ngos.append((ngo, distance))
    
    return sorted(nearby_ngos, key=lambda x: x[1])


def send_ngo_alerts(report):
    nearby_ngos = find_nearby_ngos(report.latitude, report.longitude)
    
    if not nearby_ngos:
        return False
    
    map_link = f"https://www.google.com/maps?q={report.latitude},{report.longitude}"
    
    for ngo, distance in nearby_ngos[:3]:  # Alert top 3 closest NGOs
        try:
            msg = Message(
                f'URGENT: Animal Accident Alert - {report.accident_severity.upper()} Priority',
                sender=('WARRN Emergency Alert', app.config['MAIL_USERNAME']),
                recipients=[ngo.email]
            )
            msg.body = f"""ANIMAL ACCIDENT DETECTED

Severity: {report.accident_severity.upper()}
Animal: {report.animal_type}
Condition: {report.condition}
Location: {map_link}
Distance: {distance:.1f} km from your location
Time: {report.timestamp.strftime('%Y-%m-%d %H:%M')}

Description: {report.description}
AI Detection: {report.ai_species_suggestion or 'Not detected'}

Immediate response required. Contact: {ngo.phone or 'N/A'}

Report ID: {report.id}"""
            mail.send(msg)
        except Exception as e:
            print(f"Failed to send alert to {ngo.name}: {e}")
    
    return True


# --- Routes ---
@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/set_location', methods=['POST'])
def set_location():
    """Endpoint applied by client JS to set the current session location"""
    try:
        if 'latitude' in request.form and 'longitude' in request.form:
            session['user_lat'] = float(request.form['latitude'])
            session['user_lon'] = float(request.form['longitude'])
            return jsonify({'status': 'success', 'lat': session['user_lat'], 'lon': session['user_lon']})
    except Exception as e:
        print(f"Error setting location: {e}")
    return jsonify({'status': 'error'})




@app.route('/verify-image', methods=['POST'])
def verify_image():
    if 'image' not in request.files:
        return jsonify({'success': False, 'message': 'No image uploaded'})
    
    file = request.files['image']
    if file.filename == '' or not allowed_file(file.filename):
        return jsonify({'success': False, 'message': 'Invalid image file'})
    
    # Save temporary file for verification
    ext = file.filename.rsplit('.', 1)[1].lower()
    temp_filename = f"temp_{uuid.uuid4().hex}.{ext}"
    temp_path = os.path.join(app.config['UPLOAD_FOLDER'], temp_filename)
    file.save(temp_path)
    
    # Verify with AI
    ai_suggestion = identify_animal_from_image(temp_path)
    
    # Clean up temp file
    try:
        os.remove(temp_path)
    except:
        pass
    
    if ai_suggestion:
        return jsonify({
            'success': True, 
            'detected_animal': ai_suggestion,
            'message': f'Animal detected: {ai_suggestion}'
        })
    else:
        # Allow manual override for cases where AI fails
        return jsonify({
            'success': True,  # Changed to True to allow submission
            'detected_animal': 'Unknown',
            'message': 'Image uploaded successfully. Please verify animal type manually.'
        })


from flask import Response
import detection

# --- Video Analysis Config ---
app.config['VIDEO_UPLOAD_FOLDER'] = os.path.join(basedir, 'static/video_uploads')
os.makedirs(app.config['VIDEO_UPLOAD_FOLDER'], exist_ok=True)

@app.route('/live_feed')
@login_required
def live_feed():
    if current_user.role != 'admin':
        flash('Access denied. Admins only.', 'danger')
        return redirect(url_for('dashboard'))
    mode = request.args.get('mode', 'select')
    filename = session.get('uploaded_video', None)
    return render_template('live_feed.html', mode=mode, filename=filename)

@app.route('/upload_video', methods=['POST'])
@login_required
def upload_video():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    if 'video' not in request.files:
        flash('No file part', 'danger')
        return redirect(url_for('live_feed'))
    file = request.files['video']
    if file.filename == '':
        flash('No selected file', 'danger')
        return redirect(url_for('live_feed'))
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['VIDEO_UPLOAD_FOLDER'], filename)
        file.save(filepath)
        session['uploaded_video'] = filename
        return redirect(url_for('live_feed', mode='upload'))
    return redirect(url_for('live_feed'))

@app.route('/video_feed')
@login_required
def video_feed():
    if current_user.role != 'admin':
        return "Access denied", 403
    mode = request.args.get('mode', 'live')
    source = 0
    
    if mode == 'upload':
        filename = session.get('uploaded_video')
        if filename:
            source = os.path.join(app.config['VIDEO_UPLOAD_FOLDER'], filename)
    
    # Capture location data from session NOW
    user_lat = session.get('user_lat', 15.4404)
    user_lon = session.get('user_lon', 75.0145)
    
    # Capture user identity safely before entering the generator
    user_email = None
    if current_user.is_authenticated:
        user_email = current_user.username

    # Pre-capture the server name / URL root for generating URLs in the callback thread
    server_name = request.host_url.rstrip('/')

    def report_callback(frame, details):
        """Internal callback — runs in generator thread, needs full context."""
        with app.app_context():
            with app.test_request_context():
                try:
                    import sys
                    print(f"!!! AUTO-REPORT TRIGGERED: {details}", file=sys.stderr, flush=True)
                    
                    # 1. Save Image
                    unique_id = uuid.uuid4().hex
                    img_name = f"auto_{unique_id}.jpg"
                    image_path = os.path.join(app.config['UPLOAD_FOLDER'], img_name)
                    saved = cv2.imwrite(image_path, frame)
                    if not saved:
                        print(f"ERROR: cv2.imwrite failed for {image_path}", file=sys.stderr, flush=True)
                        return False
                    print(f"Image saved: {image_path}", file=sys.stderr, flush=True)
                    
                    # 2. Create Report with a fresh session
                    new_report = Report(
                        latitude=user_lat,
                        longitude=user_lon,
                        animal_type='Animal',
                        condition='Critical',
                        description=f"Automated Detection: {details}. Incident detected in {mode} feed.",
                        image_filename=img_name,
                        ai_species_suggestion=details.split()[0] if details else 'Unknown',
                        accident_severity='critical',
                        status='New',
                        reporter_email=user_email
                    )
                    
                    db.session.add(new_report)
                    db.session.commit()
                    print(f"Report [{new_report.id}] saved to DB.", file=sys.stderr, flush=True)
                    
                    # 3. Notify via SocketIO
                    image_url = f"/static/uploads/{img_name}"
                    claim_url = f"/report/{new_report.id}/claim"
                    report_data = {
                        'id': new_report.id, 'lat': user_lat, 'lon': user_lon,
                        'animal': new_report.animal_type, 'condition': 'Critical', 
                        'desc': new_report.description,
                        'time': new_report.timestamp.strftime('%Y-%m-%d %H:%M'), 
                        'status': 'New', 'image_url': image_url,
                        'severity': 'critical',
                        'ai_suggestion': new_report.ai_species_suggestion,
                        'claim_url': claim_url
                    }
                    socketio.emit('new_report', report_data)
                    print(f"SocketIO emit sent for report [{new_report.id}].", file=sys.stderr, flush=True)
                    
                    try:
                        if send_ngo_alerts(new_report):
                            print("NGO Alerts sent.", file=sys.stderr, flush=True)
                    except Exception as ngo_err:
                        print(f"NGO alert failed (non-critical): {ngo_err}", file=sys.stderr, flush=True)
                    
                    return True
                    
                except Exception as e:
                    print(f"FAILED to handle auto-report: {e}", file=sys.stderr, flush=True)
                    import traceback
                    traceback.print_exc(file=sys.stderr)
                    db.session.rollback()
                    return False

    return Response(detection.generate_frames(source, report_callback=report_callback), mimetype='multipart/x-mixed-replace; boundary=frame')




@app.route('/report', methods=['POST'])
def submit_report():
    image_filename = None
    ai_suggestion = None

    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_id = uuid.uuid4().hex
            filename = secure_filename(f"{unique_id}.{ext}")
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(image_path)
            image_filename = filename
            # ai_suggestion = identify_animal_from_image(image_path) # Disabled for manual reports as per request

    # Detect accident severity
    severity = detect_accident_severity(
        request.form['condition'], 
        request.form.get('description', ''), 
        ai_suggestion
    )

    # Auto-fill reporter email if user is logged in
    reporter_email_val = request.form.get('reporter_email')
    if current_user.is_authenticated and not reporter_email_val:
        reporter_email_val = current_user.username

    # Ensure email is lowercase for consistency
    if reporter_email_val:
        reporter_email_val = reporter_email_val.lower()

    new_report = Report(
        latitude=request.form['latitude'], 
        longitude=request.form['longitude'],
        animal_type=request.form['animal_type'], 
        condition=request.form['condition'],
        description=request.form['description'], 
        image_filename=image_filename,
        ai_species_suggestion=ai_suggestion,
        accident_severity=severity,
        reporter_email=reporter_email_val,
        city=request.form.get('city', ''),
        pincode=request.form.get('pincode', '')
    )
    db.session.add(new_report)
    db.session.commit()

    # Send Notification to Reporter (Received)
    if new_report.reporter_email:
        try:
            msg = Message('Report Received - WARRN', 
                sender=('WARRN Team', app.config['MAIL_USERNAME']),
                recipients=[new_report.reporter_email])
            msg.body = f"""Thank you for reporting an animal incident.
            
Report ID: {new_report.id}
Status: Received
Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}

We have received your report and notified nearby responders. You will receive updates as the situation progresses.

Thank you for caring!
The WARRN Team"""
            mail.send(msg)
        except Exception as e:
            print(f"Failed to send user confirmation: {e}")

    # Send alerts to nearby NGOs for accidents
    ngo_alert_sent = False
    if severity in ['critical', 'high']:
        ngo_alert_sent = send_ngo_alerts(new_report)

    image_url = url_for('static', filename=f'uploads/{new_report.image_filename}') if new_report.image_filename else None
    report_data = {
        'id': new_report.id, 'lat': new_report.latitude, 'lon': new_report.longitude,
        'animal': new_report.animal_type, 'condition': new_report.condition, 'desc': new_report.description,
        'time': new_report.timestamp.strftime('%Y-%m-%d %H:%M'), 'status': new_report.status,
        'responder': None, 'image_url': image_url, 'ai_suggestion': new_report.ai_species_suggestion,
        'severity': new_report.accident_severity, 'claim_url': url_for('claim_report', report_id=new_report.id)
    }
    socketio.emit('new_report', report_data)

    try:
        # Match only volunteers in the same general area (first 3 digits of pincode)
        responders = User.query.filter_by(role='responder', is_verified=True).all()
        responder_emails = []
        rp_pin = new_report.pincode or ""
        
        for user in responders:
            u_pin = user.pincode or ""
            if rp_pin != "" and u_pin != "" and u_pin[:3] == rp_pin[:3]:
                if '@' in user.username:
                    responder_emails.append(user.username)
                    
        if responder_emails:
            map_link = f"https://www.google.com/maps?q={new_report.latitude},{new_report.longitude}"
            msg = Message('New Animal Incident Reported!', sender=('WARRN Alert', app.config['MAIL_USERNAME']),
                          recipients=responder_emails)
            msg.body = f"""A new animal incident has been reported.

Severity: {severity.upper()}
Details:
- Animal: {new_report.animal_type}
- Condition: {new_report.condition}
- Location: {map_link}

Please log in to the dashboard to claim it."""
            mail.send(msg)
            
        if ngo_alert_sent:
            flash('Report submitted! Emergency alerts sent to nearby NGOs.', 'success')
        else:
            flash('Report submitted and notification sent.', 'success')
    except Exception as e:
        print(e)
        flash('Report submitted, but failed to send some notifications.', 'warning')

    return redirect(url_for('index'))


@app.route('/api/reports')
def get_reports():
    reports_list = []
    reports = Report.query.order_by(Report.timestamp.desc()).all()
    for report in reports:
        image_url = url_for('static', filename=f'uploads/{report.image_filename}') if report.image_filename else None
        reports_list.append({'lat': report.latitude, 'lon': report.longitude, 'animal': report.animal_type,
                             'condition': report.condition, 'desc': report.description,
                             'time': report.timestamp.strftime('%Y-%m-%d %H:%M'), 'image_url': image_url,
                             'status': report.status, 'ai_suggestion': report.ai_species_suggestion})
    return jsonify(reports_list)


@app.route('/api/chat', methods=['POST'])
def chatbot_api():
    data = request.get_json()
    if not data or 'message' not in data:
        return jsonify({'error': 'No message provided'}), 400
    
    user_message = data['message']
    
    try:
        reply, route, case_id = chatbot_handler.process_query(user_message)
        
        # Log the conversation
        log = ChatbotLog(
            user_query=user_message,
            route_used=route,
            intent=route,
            case_id=case_id,
            bot_reply=reply
        )
        db.session.add(log)
        db.session.commit()
        
        return jsonify({
            'reply': reply,
            'route': route
        })
    except Exception as e:
        print(f"Chatbot Route Error: {e}")
        return jsonify({'reply': "I'm sorry, I'm having trouble processing that right now.", 'route': 'error'}), 500


@app.route('/track', methods=['GET', 'POST'])
def track_reports():
    reports = []
    email = ''
    searched = False
    
    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        if email:
            reports = Report.query.filter(func.lower(Report.reporter_email) == email).order_by(Report.timestamp.desc()).all()
            searched = True
            
    return render_template('track_reports.html', reports=reports, email=email, searched=searched)


@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        if User.query.count() == 0:
            user_role = 'admin'
            responder_type = 'ngo'
            is_verified = True
        else:
            responder_type = request.form.get('responder_type', 'volunteer')
            user_role = 'adopter' if responder_type == 'adopter' else 'responder'
            is_verified = False
            
        email = request.form['username'].lower().strip()
        if User.query.filter_by(username=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))

        city = request.form.get('city', '').strip()
        pincode = request.form.get('pincode', '').strip()
        ngo_name = request.form.get('ngo_name', '').strip() if responder_type == 'ngo' else None
        hashed_password = bcrypt.generate_password_hash(request.form['password']).decode('utf-8')
        new_user = User(
            username=email, 
            password_hash=hashed_password, 
            role=user_role, 
            responder_type=responder_type, 
            is_verified=is_verified,
            city=city,
            pincode=pincode,
            ngo_name=ngo_name
        )
        
        if not is_verified:
            otp = ''.join(random.choices(string.digits, k=6))
            new_user.verification_otp = otp
            try:
                msg = Message('Verify your WARRN Account', sender=('WARRN Admin', app.config.get('MAIL_USERNAME')), recipients=[email])
                msg.body = f"Welcome to WARRN!\n\nYour OTP for email verification is: {otp}\n\nPlease verify your account to start claiming incidents."
                mail.send(msg)
            except Exception as e:
                print(f"Failed to send verify email: {e}")
                
        db.session.add(new_user)
        db.session.commit()
        
        if is_verified:
            flash('Admin account created! You can now log in.', 'success')
            return redirect(url_for('login'))
        else:
            session['unverified_email'] = email
            flash('Account created! Please check your email for the OTP verification code.', 'info')
            return redirect(url_for('verify_email'))
            
    return render_template('register.html')


@app.route('/verify', methods=['GET', 'POST'])
def verify_email():
    email = session.get('unverified_email') or request.args.get('email')
    
    if not email:
        return redirect(url_for('login'))
        
    if request.method == 'POST':
        otp_input = request.form.get('otp', '').strip()
        user = User.query.filter_by(username=email).first()
        
        if user and user.verification_otp == otp_input:
            user.is_verified = True
            user.verification_otp = None
            db.session.commit()
            
            flash('Email verified successfully! You can now log in.', 'success')
            session.pop('unverified_email', None)
            return redirect(url_for('login'))
        else:
            flash('Invalid OTP. Please try again.', 'danger')
            
    return render_template('verify.html', email=email)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('dashboard'))
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'].lower().strip()).first()
        if user and bcrypt.check_password_hash(user.password_hash, request.form['password']):
            if not getattr(user, 'is_verified', True):
                session['unverified_email'] = user.username
                flash('Please verify your email address to log in.', 'warning')
                return redirect(url_for('verify_email'))
            login_user(user, remember=True)
            next_page = request.args.get('next') or request.form.get('next')
            return redirect(next_page) if next_page else redirect(url_for('dashboard'))
        else:
            flash('Login unsuccessful. Please check username and password.', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/forgot_password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email').strip().lower()
        user = User.query.filter_by(username=email).first()
        
        if user:
            # Generate 6-digit OTP
            otp = ''.join(random.choices(string.digits, k=6))
            user.reset_otp = otp
            user.reset_otp_expiry = datetime.utcnow() + timedelta(minutes=15)
            db.session.commit()
            
            # Send Email
            msg = Message('Password Reset OTP - WARRN',
                          sender=app.config.get('MAIL_USERNAME'),
                          recipients=[email])
            msg.body = f"Your OTP for password reset is: {otp}\n\nThis OTP is valid for 15 minutes.\n\nIf you did not request this, please ignore this email."
            try:
                mail.send(msg)
                flash('An OTP has been sent to your email address.', 'info')
                return redirect(url_for('reset_password', email=email))
            except Exception as e:
                print(f"Failed to send email: {e}")
                flash('Error sending email. Please try again later.', 'danger')
        else:
            flash('Email address not found.', 'warning')
            
    return render_template('forgot_password.html')

@app.route('/reset_password', methods=['GET', 'POST'])
def reset_password():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
        
    email = request.args.get('email')
    
    if request.method == 'POST':
        email = request.form.get('email')
        otp_input = request.form.get('otp')
        new_password = request.form.get('password')
        
        user = User.query.filter_by(username=email).first()
        
        if user and user.reset_otp == otp_input:
            if user.reset_otp_expiry and user.reset_otp_expiry > datetime.utcnow():
                # Success - Reset Password
                hashed_password = bcrypt.generate_password_hash(new_password).decode('utf-8')
                user.password_hash = hashed_password
                user.reset_otp = None
                user.reset_otp_expiry = None
                db.session.commit()
                flash('Your password has been reset! You can now login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('OTP has expired. Please request a new one.', 'warning')
                return redirect(url_for('forgot_password'))
        else:
            flash('Invalid OTP. Please try again.', 'danger')
            
    return render_template('reset_password.html', email=email)

print('test code...............')
@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'adopter':
        flash('Adopters cannot access the responder dashboard. Redirecting to adoption portal.', 'info')
        return redirect(url_for('view_adoptions'))
        
    reports = Report.query.all()
    # Smart Sorting: Exact Pincode -> Partial Pincode -> Other
    user_pin = current_user.pincode or ""
    
    def sort_key(report):
        rp_pin = report.pincode or ""
        # 0 = Exact match, 1 = Partial match (first 3), 2 = No match
        match_score = 0 if (rp_pin == user_pin and user_pin != "") else (1 if (rp_pin[:3] == user_pin[:3] and user_pin != "") else 2)
        # Combine score with descending timestamp (use negative timestamp for sorting order)
        ts = report.timestamp.timestamp() if report.timestamp else 0
        return (match_score, -ts)
        
    reports.sort(key=sort_key)
    # Map report_id -> CaseReport for template buttons
    case_reports = {cr.report_id: cr for cr in CaseReport.query.all()}
    
    # User's own adoption listings + incoming requests
    my_listings = Adoption.query.filter_by(posted_by_id=current_user.id).order_by(Adoption.timestamp.desc()).all()
    my_listing_ids = [a.id for a in my_listings]
    adoption_requests = []
    if my_listing_ids:
        adoption_requests = (AdoptionApplication.query
            .filter(AdoptionApplication.adoption_id.in_(my_listing_ids))
            .order_by(AdoptionApplication.timestamp.desc())
            .all())
        listings_map = {a.id: a for a in my_listings}
        for req in adoption_requests:
            req.listing = listings_map.get(req.adoption_id)
    
    return render_template('dashboard.html', reports=reports, case_reports=case_reports,
                           adoption_requests=adoption_requests, my_listings=my_listings)


@app.route('/report/<int:report_id>/claim', methods=['POST'])
@login_required
def claim_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.status == 'New':
        report.responder_id = current_user.id
        report.status = 'Acknowledged'
        db.session.commit()
        
        # Email Reporter (Claimed)
        if report.reporter_email:
            try:
                msg = Message(f'Update: Report #{report.id} Claimed', 
                    sender=('WARRN Team', app.config['MAIL_USERNAME']),
                    recipients=[report.reporter_email])
                msg.body = f"""Good news! A responder has claimed your report.

Report ID: {report.id}
Responder: {current_user.username}
New Status: Acknowledged - Help is on the way!

We will notify you once the situation is resolved.
"""
                mail.send(msg)
            except Exception as e:
                print(f"Failed to send claim notification: {e}")
                
        flash('You have claimed this report.', 'success')
    else:
        flash('This report has already been claimed.', 'warning')
    return redirect(url_for('dashboard'))


@app.route('/report/<int:report_id>/escalate', methods=['POST'])
@login_required
def escalate_report(report_id):
    report = Report.query.get_or_404(report_id)
    if report.responder_id != current_user.id:
        flash('You cannot escalate a report you have not claimed.', 'danger')
        return redirect(url_for('dashboard'))
        
    report.escalated_to_ngo = True
    report.status = 'New'
    report.responder_id = None
    db.session.commit()
    
    ngo_emails = []
    rp_pin = report.pincode or ""
    
    ngo_users = User.query.filter_by(role='responder', responder_type='ngo', is_verified=True).all()
    for u in ngo_users:
        u_pin = u.pincode or ""
        if rp_pin != "" and u_pin != "" and u_pin[:3] == rp_pin[:3] and '@' in u.username:
            ngo_emails.append(u.username)
    
    ngos = NGO.query.filter_by(active=True).all()
    for n in ngos:
        n_pin = n.pincode or ""
        if rp_pin != "" and n_pin != "" and n_pin[:3] == rp_pin[:3] and '@' in n.email:
            ngo_emails.append(n.email)
            
    ngo_emails = list(set(ngo_emails))
    
    if ngo_emails:
        try:
            map_link = f"https://www.google.com/maps?q={report.latitude},{report.longitude}"
            msg = Message(f'ESCALATION: Urgent Animal Incident #{report.id}', 
                        sender=('WARRN Alert', app.config['MAIL_USERNAME']),
                        recipients=ngo_emails)
            msg.body = f"""An incident has been escalated by a volunteer to NGOs!

Priority: URGENT / ESCALATED
Animal: {report.animal_type}
Condition: {report.condition}
Location: {map_link}

The volunteer who initially claimed this requires NGO assistance/facilities. 
Please log in to the dashboard immediately to claim and resolve the situation."""
            mail.send(msg)
        except Exception as e:
            print(f"Failed to send escalation email: {e}")
            
    flash('Incident escalated successfully to NGOs. It has been returned to the dashboard for an NGO to claim.', 'success')
    return redirect(url_for('dashboard'))


    return redirect(url_for('dashboard'))


@app.route('/report/<int:report_id>/resolve_details', methods=['POST'])
@login_required
def resolve_report_with_details(report_id):
    report = Report.query.get_or_404(report_id)
    if report.responder_id != current_user.id:
        flash('You cannot resolve a report you have not claimed.', 'danger')
        return redirect(url_for('dashboard'))
        
    status_outcome = request.form.get('outcome', 'Resolved')
    notes = request.form.get('resolution_notes', '')
    
    # Handle Final Image Upload
    resolution_image_file = None
    if 'resolution_image' in request.files:
        file = request.files['resolution_image']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_id = uuid.uuid4().hex
            filename = f"resolved_{unique_id}.{ext}"
            image_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(image_path)
            resolution_image_file = filename

    # Update Report (We might want to add columns for these later, but for now we update status and maybe append to description or just email)
    # For now, let's just mark it 'Resolved' in DB, but the email sends the details
    report.status = 'Resolved'
    db.session.commit()

    # === AI CASE REPORT GENERATION ===
    try:
        responder_name = current_user.ngo_name or current_user.username
        ai_narrative = generate_ai_case_narrative(report, status_outcome, notes, responder_name)
        pdf_filename = build_case_report_pdf(report, status_outcome, notes, current_user, ai_narrative)

        case_report = CaseReport(
            report_id=report.id,
            generated_by_id=current_user.id,
            ai_narrative=ai_narrative,
            pdf_filename=pdf_filename
        )
        db.session.add(case_report)
        db.session.commit()
    except Exception as e:
        print(f"Case report generation failed: {e}")

    # === EMAIL REPORTER ===
    if report.reporter_email:
        try:
            msg = Message(f'Final Update: Report #{report.id} Resolved',
                sender=('WARRN Team', app.config['MAIL_USERNAME']),
                recipients=[report.reporter_email])
            msg.body = f"""The animal incident you reported has been resolved.

Report ID: {report.id}
Final Outcome: {status_outcome}
Responder Notes: {notes}

Thank you for your assistance in helping this animal.
"""
            if resolution_image_file:
                with app.open_resource(os.path.join(app.config['UPLOAD_FOLDER'], resolution_image_file)) as fp:
                    msg.attach(resolution_image_file, f"image/{ext}", fp.read())
            mail.send(msg)
            flash('Report resolved! AI case report generated and email sent to reporter.', 'success')
        except Exception as e:
            print(f"Failed to send resolution email: {e}")
            flash('Report resolved and AI case report generated. (Email notification failed.)', 'warning')
    else:
        flash('Report resolved! AI case report has been generated and is available for download.', 'success')

    return redirect(url_for('dashboard'))
# ============================================================
# ADOPTION ROUTES
# ============================================================

@app.route('/adoptions')
@login_required
def view_adoptions():
    """Login-required adoption gallery."""
    animal_type = request.args.get('animal_type', '').strip()
    city = request.args.get('city', '').strip()
    pincode = request.args.get('pincode', '').strip()

    query = Adoption.query.filter_by(is_adopted=False)

    if animal_type:
        query = query.filter(Adoption.animal_type == animal_type)
    if city:
        query = query.filter(Adoption.city.ilike(f'%{city}%'))
    if pincode:
        # Priority: exact match first, then partial (first 3 digits)
        exact = Adoption.query.filter_by(is_adopted=False, pincode=pincode)
        partial = Adoption.query.filter(
            Adoption.is_adopted == False,
            Adoption.pincode.like(f'{pincode[:3]}%'),
            Adoption.pincode != pincode
        )
        if animal_type:
            exact = exact.filter(Adoption.animal_type == animal_type)
            partial = partial.filter(Adoption.animal_type == animal_type)
        if city:
            exact = exact.filter(Adoption.city.ilike(f'%{city}%'))
            partial = partial.filter(Adoption.city.ilike(f'%{city}%'))
        adoptions = exact.order_by(Adoption.timestamp.desc()).all() + \
                    partial.order_by(Adoption.timestamp.desc()).all()
        # Attach poster info
        for a in adoptions:
            a.posted_by = User.query.get(a.posted_by_id) if a.posted_by_id else None
        return render_template('adoptions.html',
            adoptions=adoptions,
            total_count=len(adoptions),
            filters={'animal_type': animal_type, 'city': city, 'pincode': pincode}
        )

    adoptions = query.order_by(Adoption.timestamp.desc()).all()
    for a in adoptions:
        a.posted_by = User.query.get(a.posted_by_id) if a.posted_by_id else None

    return render_template('adoptions.html',
        adoptions=adoptions,
        total_count=len(adoptions),
        filters={'animal_type': animal_type, 'city': city, 'pincode': pincode}
    )


@app.route('/adoption/post', methods=['POST'])
@login_required
def post_adoption():
    """NGO/Volunteer posts a resolved animal for adoption."""
    if current_user.role not in ['admin', 'responder']:
        flash('Only responders can post adoption listings.', 'danger')
        return redirect(url_for('view_adoptions'))

    animal_type = request.form.get('animal_type', '').strip()
    description = request.form.get('description', '').strip()
    city = request.form.get('city', current_user.city or '').strip()
    pincode = request.form.get('pincode', current_user.pincode or '').strip()

    if not animal_type or not description:
        flash('Animal type and description are required.', 'danger')
        return redirect(url_for('dashboard'))

    # Handle image upload
    image_filename = None
    if 'image' in request.files:
        file = request.files['image']
        if file and file.filename != '' and allowed_file(file.filename):
            ext = file.filename.rsplit('.', 1)[1].lower()
            unique_id = uuid.uuid4().hex
            filename = f"adopt_{unique_id}.{ext}"
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            image_filename = filename

    listing = Adoption(
        animal_type=animal_type,
        description=description,
        city=city,
        pincode=pincode,
        image_filename=image_filename,
        posted_by_id=current_user.id
    )
    db.session.add(listing)
    db.session.commit()

    flash('Adoption listing posted! It is now visible on the public Adoption Board.', 'success')
    return redirect(url_for('view_adoptions'))


@app.route('/adoption/<int:adoption_id>/apply', methods=['POST'])
@login_required
def apply_for_adoption(adoption_id):
    """Login-required: submit adoption application, generate PDF, email NGO."""
    listing = Adoption.query.get_or_404(adoption_id)
    ngo_user = User.query.get(listing.posted_by_id) if listing.posted_by_id else None

    first_name  = request.form.get('first_name', '').strip()
    second_name = request.form.get('second_name', '').strip()
    email       = request.form.get('email', '').strip()
    phone       = request.form.get('phone', '').strip()
    address     = request.form.get('address', '').strip()
    city        = request.form.get('city', '').strip()
    pincode     = request.form.get('pincode', '').strip()
    has_other_pets = request.form.get('has_other_pets', 'No')
    house_type  = request.form.get('house_type', '').strip()

    if not all([first_name, email, phone, address]):
        flash('Please fill in all required fields.', 'danger')
        return redirect(url_for('view_adoptions'))

    # Save application to DB (no PDF yet, generate after)
    application = AdoptionApplication(
        adoption_id=adoption_id,
        first_name=first_name, second_name=second_name,
        email=email, phone=phone, address=address,
        city=city, pincode=pincode,
        has_other_pets=has_other_pets, house_type=house_type
    )
    db.session.add(application)
    db.session.commit()

    # Generate PDF
    try:
        pdf_filename = build_adoption_application_pdf(application, listing, ngo_user)
        application.pdf_filename = pdf_filename
        db.session.commit()
    except Exception as e:
        print(f"PDF generation failed: {e}")
        pdf_filename = None

    # Email PDF to NGO
    if ngo_user:
        try:
            ngo_label = ngo_user.ngo_name or ngo_user.username
            msg = Message(
                f'New Adoption Application — {listing.animal_type} (Listing #{listing.id})',
                sender=('WARRN Adoptions', app.config['MAIL_USERNAME']),
                recipients=[ngo_user.username]
            )
            msg.body = f"""Hello {ngo_label},

A new adoption application has been submitted for your listing.

Applicant: {first_name} {second_name}
Animal: {listing.animal_type}
Listing ID: #{listing.id}

Please find the full application details attached as a PDF.
You can also view all applications in the WARRN Admin Panel.

— WARRN Platform"""

            if pdf_filename:
                pdf_path = os.path.join(PDF_FOLDER, pdf_filename)
                with open(pdf_path, 'rb') as fp:
                    msg.attach(pdf_filename, 'application/pdf', fp.read())

            mail.send(msg)
        except Exception as e:
            print(f"Failed to email adoption application to NGO: {e}")

    # Confirm email to applicant
    try:
        confirm_msg = Message(
            f'Application Received — {listing.animal_type} Adoption',
            sender=('WARRN Adoptions', app.config['MAIL_USERNAME']),
            recipients=[email]
        )
        ngo_label = (ngo_user.ngo_name or ngo_user.username) if ngo_user else 'the NGO'
        confirm_msg.body = f"""Hello {first_name},

Thank you for your interest in adopting the {listing.animal_type}!

Your application has been received and forwarded to {ngo_label}.
They will review it and contact you at {email} or {phone}.

Application ID: #{application.id}

— WARRN Platform"""
        mail.send(confirm_msg)
    except Exception as e:
        print(f"Failed to send applicant confirmation: {e}")

    flash(f'Your adoption application has been submitted! {(ngo_user.ngo_name or ngo_user.username) if ngo_user else "The NGO"} will contact you soon.', 'success')
    return redirect(url_for('view_adoptions'))


@app.route('/case-report/<int:case_report_id>/download')
@login_required
def download_case_report(case_report_id):
    """Download a generated AI case report PDF."""
    cr = CaseReport.query.get_or_404(case_report_id)
    if current_user.role not in ['admin', 'responder']:
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    if not cr.pdf_filename:
        flash('PDF not yet generated for this report.', 'warning')
        return redirect(url_for('dashboard'))
    pdf_path = os.path.join(PDF_FOLDER, cr.pdf_filename)
    if not os.path.exists(pdf_path):
        flash('PDF file not found.', 'danger')
        return redirect(url_for('dashboard'))
    return send_file(pdf_path, as_attachment=True, download_name=f'WARRN_CaseReport_{cr.report_id}.pdf')


@app.route('/adoption/<int:adoption_id>/mark_adopted', methods=['POST'])
@login_required
def mark_adoption_adopted(adoption_id):
    """Mark an adoption listing as Adopted (hides it from the public board)."""
    listing = Adoption.query.get_or_404(adoption_id)
    if listing.posted_by_id != current_user.id and current_user.role != 'admin':
        flash('You can only manage your own listings.', 'danger')
        return redirect(url_for('dashboard'))
    listing.is_adopted = True
    db.session.commit()
    flash(f'Great news! The {listing.animal_type} has been marked as Adopted and removed from the public board.', 'success')
    return redirect(url_for('dashboard') + '#adoptionsPane')


@app.route('/adoption/<int:adoption_id>/delete', methods=['POST'])
@login_required
def delete_adoption_listing(adoption_id):
    """Permanently delete an adoption listing and all its applications."""
    listing = Adoption.query.get_or_404(adoption_id)
    if listing.posted_by_id != current_user.id and current_user.role != 'admin':
        flash('You can only delete your own listings.', 'danger')
        return redirect(url_for('dashboard'))
    # Delete applications first (FK constraint)
    AdoptionApplication.query.filter_by(adoption_id=adoption_id).delete()
    # Delete image file if present
    if listing.image_filename:
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], listing.image_filename)
        if os.path.exists(img_path):
            os.remove(img_path)
    db.session.delete(listing)
    db.session.commit()
    flash('Adoption listing and all related applications have been removed.', 'success')
    return redirect(url_for('dashboard') + '#adoptionsPane')


@app.route('/analytics')
@login_required
def analytics():
    if current_user.role != 'admin':
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('dashboard'))

    total_reports = Report.query.count()
    reports_by_status = db.session.query(Report.status, func.count(Report.status)).group_by(Report.status).all()
    status_counts = {status: count for status, count in reports_by_status}
    reports_by_animal = db.session.query(Report.animal_type, func.count(Report.animal_type)).group_by(
        Report.animal_type).order_by(func.count(Report.animal_type).desc()).all()
    animal_labels = [item[0] for item in reports_by_animal]
    animal_data = [item[1] for item in reports_by_animal]

    return render_template('analytics.html', total_reports=total_reports, status_counts=status_counts,
                           animal_labels=animal_labels, animal_data=animal_data)


@app.route('/ngos')
@login_required
def manage_ngos():
    if current_user.role != 'admin':
        flash('You must be an admin to access this page.', 'danger')
        return redirect(url_for('dashboard'))
    ngos = NGO.query.all()
    return render_template('ngos.html', ngos=ngos)


@app.route('/ngo/add', methods=['POST'])
@login_required
def add_ngo():
    if current_user.role != 'admin':
        flash('Access denied.', 'danger')
        return redirect(url_for('dashboard'))
    
    new_ngo = NGO(
        name=request.form['name'],
        email=request.form['email'],
        phone=request.form.get('phone'),
        latitude=float(request.form['latitude']),
        longitude=float(request.form['longitude']),
        specialization=request.form.get('specialization'),
        coverage_radius=float(request.form.get('coverage_radius', 10))
    )
    db.session.add(new_ngo)
    db.session.commit()
    flash('NGO added successfully!', 'success')
    return redirect(url_for('manage_ngos'))


# --- Main Execution ---
if __name__ == '__main__':
    with app.app_context():
        instance_path = os.path.join(basedir, 'instance')
        os.makedirs(instance_path, exist_ok=True)
        db.create_all()
    socketio.run(app, debug=True, host='0.0.0.0', allow_unsafe_werkzeug=True)