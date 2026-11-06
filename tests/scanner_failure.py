"""Run only while the LAB scanner is deliberately stopped by the operator."""
from email.message import EmailMessage
import json
from pathlib import Path
import smtplib
import ssl
import uuid
state=json.loads(Path('/var/vmail/.qualification/persistence.json').read_text())
user=state['user'];ctx=ssl.create_default_context(cafile='/run/tls/ca.crt')
message=EmailMessage();message['From']=user;message['To']=user
message['Subject']='Scanner outage '+uuid.uuid4().hex
message.set_content('Unique synthetic attachment during a scanner outage.')
message.add_attachment(uuid.uuid4().bytes*30,maintype='application',subtype='octet-stream',filename='outage.bin')
with smtplib.SMTP('mail.lab.invalid',587,timeout=90) as s:
    s.ehlo();s.starttls(context=ctx);s.ehlo();s.login(user,'Synthetic-Only-Password!2026')
    try:s.send_message(message)
    except smtplib.SMTPDataError as exc:
        assert 400<=exc.smtp_code<500,exc.smtp_code
    else:raise AssertionError('Mail accepted while the virus scanner was unavailable')
print(json.dumps({'test':'Scanner outage produces retryable SMTP failure','passed':True}))
