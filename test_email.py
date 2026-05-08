
import os
from dotenv import load_dotenv
from flask import Flask
from flask_mail import Mail, Message

load_dotenv()

app = Flask(__name__)

# Config
app.config['MAIL_SERVER'] = 'smtp.googlemail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEBUG'] = True # Enable debug to see more info

print(f"Testing Email Configuration:")
print(f"Username: {app.config['MAIL_USERNAME']}")
print(f"Password Length: {len(app.config['MAIL_PASSWORD']) if app.config['MAIL_PASSWORD'] else 0}")

mail = Mail(app)

with app.app_context():
    try:
        print("Attempting to connect and send email...")
        msg = Message('WARRN Test Email', 
                    sender=('WARRN Test', app.config['MAIL_USERNAME']),
                    recipients=[app.config['MAIL_USERNAME']]) # Send to self
        msg.body = "This is a test email to verify configuration."
        mail.send(msg)
        print("SUCCESS: Email sent successfully!")
    except Exception as e:
        print(f"FAILURE: Could not send email.")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
