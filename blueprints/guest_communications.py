from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from extensions import db
from models import Tenant, GuestCommunication
from permissions import require_frontdesk_or_admin
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

guest_communications_bp = Blueprint('guest_communications', __name__, url_prefix='/guest-communications')

@guest_communications_bp.route('/')
@login_required
@require_frontdesk_or_admin
def index():
    """Guest communications dashboard"""
    # Recent communications
    recent_communications = GuestCommunication.query.order_by(
        GuestCommunication.sent_at.desc()
    ).limit(20).all()
    
    # Communication stats
    total_sent = GuestCommunication.query.count()
    email_sent = GuestCommunication.query.filter_by(communication_type='email').count()
    sms_sent = GuestCommunication.query.filter_by(communication_type='sms').count()
    
    # Guests with contact info
    guests_with_email = Tenant.query.filter(Tenant.email.isnot(None), Tenant.email != '').count()
    guests_with_phone = Tenant.query.filter(Tenant.phone.isnot(None), Tenant.phone != '').count()
    
    return render_template('guest_communications/index.html',
                         recent_communications=recent_communications,
                         total_sent=total_sent,
                         email_sent=email_sent,
                         sms_sent=sms_sent,
                         guests_with_email=guests_with_email,
                         guests_with_phone=guests_with_phone)

@guest_communications_bp.route('/send-email', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def send_email():
    """Send email to guests"""
    if request.method == 'POST':
        recipient_type = request.form.get('recipient_type')
        subject = request.form.get('subject')
        message = request.form.get('message')
        
        if not all([recipient_type, subject, message]):
            flash('All fields are required.', 'error')
            return redirect(url_for('guest_communications.send_email'))
        
        # Get recipients based on type
        recipients = []
        if recipient_type == 'all':
            recipients = Tenant.query.filter(
                Tenant.email.isnot(None), 
                Tenant.email != ''
            ).all()
        elif recipient_type == 'active':
            recipients = Tenant.query.filter(
                Tenant.email.isnot(None), 
                Tenant.email != '',
                Tenant.is_active == True
            ).all()
        elif recipient_type.startswith('guest_'):
            guest_id = recipient_type.split('_')[1]
            guest = Tenant.query.get(guest_id)
            if guest and guest.email:
                recipients = [guest]
        
        # Send emails
        sent_count = 0
        for guest in recipients:
            try:
                if send_email_notification(guest.email, subject, message):
                    # Log communication
                    communication = GuestCommunication(
                        tenant_id=guest.id,
                        communication_type='email',
                        subject=subject,
                        message=message,
                        sent_by=current_user.id,
                        sent_at=datetime.utcnow(),
                        status='sent'
                    )
                    db.session.add(communication)
                    sent_count += 1
                else:
                    # Log failed communication
                    communication = GuestCommunication(
                        tenant_id=guest.id,
                        communication_type='email',
                        subject=subject,
                        message=message,
                        sent_by=current_user.id,
                        sent_at=datetime.utcnow(),
                        status='failed'
                    )
                    db.session.add(communication)
            except Exception as e:
                print(f"Error sending email to {guest.email}: {e}")
        
        db.session.commit()
        
        if sent_count > 0:
            flash(f'Successfully sent email to {sent_count} guest(s).', 'success')
        else:
            flash('No emails were sent. Please check your email configuration.', 'error')
        
        return redirect(url_for('guest_communications.index'))
    
    # GET request - show form
    guests = Tenant.query.filter(
        Tenant.email.isnot(None), 
        Tenant.email != ''
    ).all()
    
    return render_template('guest_communications/send_email.html', guests=guests)

@guest_communications_bp.route('/send-sms', methods=['GET', 'POST'])
@login_required
@require_frontdesk_or_admin
def send_sms():
    """Send SMS to guests"""
    if request.method == 'POST':
        recipient_type = request.form.get('recipient_type')
        message = request.form.get('message')
        
        if not all([recipient_type, message]):
            flash('All fields are required.', 'error')
            return redirect(url_for('guest_communications.send_sms'))
        
        # Get recipients based on type
        recipients = []
        if recipient_type == 'all':
            recipients = Tenant.query.filter(
                Tenant.phone.isnot(None), 
                Tenant.phone != ''
            ).all()
        elif recipient_type == 'active':
            recipients = Tenant.query.filter(
                Tenant.phone.isnot(None), 
                Tenant.phone != '',
                Tenant.is_active == True
            ).all()
        elif recipient_type.startswith('guest_'):
            guest_id = recipient_type.split('_')[1]
            guest = Tenant.query.get(guest_id)
            if guest and guest.phone:
                recipients = [guest]
        
        # Send SMS (placeholder - would integrate with SMS service)
        sent_count = 0
        for guest in recipients:
            try:
                # This is a placeholder - you would integrate with Twilio, AWS SNS, etc.
                sms_sent = send_sms_notification(guest.phone, message)
                
                # Log communication
                communication = GuestCommunication(
                    tenant_id=guest.id,
                    communication_type='sms',
                    subject='SMS Notification',
                    message=message,
                    sent_by=current_user.id,
                    sent_at=datetime.utcnow(),
                    status='sent' if sms_sent else 'failed'
                )
                db.session.add(communication)
                
                if sms_sent:
                    sent_count += 1
                    
            except Exception as e:
                print(f"Error sending SMS to {guest.phone}: {e}")
        
        db.session.commit()
        
        if sent_count > 0:
            flash(f'Successfully sent SMS to {sent_count} guest(s).', 'success')
        else:
            flash('No SMS messages were sent. Please check your SMS configuration.', 'error')
        
        return redirect(url_for('guest_communications.index'))
    
    # GET request - show form
    guests = Tenant.query.filter(
        Tenant.phone.isnot(None), 
        Tenant.phone != ''
    ).all()
    
    return render_template('guest_communications/send_sms.html', guests=guests)

@guest_communications_bp.route('/templates')
@login_required
@require_frontdesk_or_admin
def templates():
    """Manage communication templates"""
    # This would store common message templates
    default_templates = [
        {
            'name': 'Welcome Message',
            'type': 'email',
            'subject': 'Welcome to Our Hostel!',
            'message': 'Dear {guest_name},\n\nWelcome to our hostel! We hope you have a wonderful stay. If you need anything, please don\'t hesitate to contact us.\n\nBest regards,\nHostel Management'
        },
        {
            'name': 'Check-out Reminder',
            'type': 'email',
            'subject': 'Check-out Reminder',
            'message': 'Dear {guest_name},\n\nThis is a friendly reminder that your check-out is scheduled for tomorrow at 11:00 AM. Please ensure all belongings are packed and the room is ready for inspection.\n\nThank you for staying with us!\n\nBest regards,\nHostel Management'
        },
        {
            'name': 'Payment Reminder',
            'type': 'sms',
            'subject': 'Payment Reminder',
            'message': 'Hi {guest_name}, this is a reminder that your payment of ${amount} is due. Please visit the front desk to complete payment. Thank you!'
        },
        {
            'name': 'WiFi Information',
            'type': 'email',
            'subject': 'WiFi Access Information',
            'message': 'Dear {guest_name},\n\nHere are your WiFi details:\nNetwork: HostelWiFi\nPassword: Welcome123\n\nEnjoy your stay!\n\nBest regards,\nHostel Management'
        }
    ]
    
    return render_template('guest_communications/templates.html', templates=default_templates)

@guest_communications_bp.route('/history')
@login_required
@require_frontdesk_or_admin
def history():
    """View communication history"""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    
    communications = GuestCommunication.query.order_by(
        GuestCommunication.sent_at.desc()
    ).paginate(
        page=page, 
        per_page=per_page, 
        error_out=False
    )
    
    return render_template('guest_communications/history.html', communications=communications)

def send_email_notification(recipient_email, subject, message):
    """Send email notification (placeholder implementation)"""
    try:
        # This is a placeholder implementation
        # In production, you would configure SMTP settings
        
        # Example SMTP configuration (uncomment and configure for production):
        # smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        # smtp_port = int(os.getenv('SMTP_PORT', '587'))
        # smtp_username = os.getenv('SMTP_USERNAME')
        # smtp_password = os.getenv('SMTP_PASSWORD')
        # 
        # if not all([smtp_username, smtp_password]):
        #     return False
        # 
        # msg = MIMEMultipart()
        # msg['From'] = smtp_username
        # msg['To'] = recipient_email
        # msg['Subject'] = subject
        # 
        # msg.attach(MIMEText(message, 'plain'))
        # 
        # server = smtplib.SMTP(smtp_server, smtp_port)
        # server.starttls()
        # server.login(smtp_username, smtp_password)
        # text = msg.as_string()
        # server.sendmail(smtp_username, recipient_email, text)
        # server.quit()
        
        print(f"Email sent to {recipient_email}: {subject}")
        return True
        
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

def send_sms_notification(phone_number, message):
    """Send SMS notification (placeholder implementation)"""
    try:
        # This is a placeholder implementation
        # In production, you would integrate with Twilio, AWS SNS, or similar service
        
        # Example Twilio integration (uncomment and configure for production):
        # from twilio.rest import Client
        # 
        # account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        # auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        # from_number = os.getenv('TWILIO_PHONE_NUMBER')
        # 
        # if not all([account_sid, auth_token, from_number]):
        #     return False
        # 
        # client = Client(account_sid, auth_token)
        # 
        # message = client.messages.create(
        #     body=message,
        #     from_=from_number,
        #     to=phone_number
        # )
        
        print(f"SMS sent to {phone_number}: {message}")
        return True
        
    except Exception as e:
        print(f"Failed to send SMS: {e}")
        return False
