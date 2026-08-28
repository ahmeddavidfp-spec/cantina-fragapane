import os
import json
import uuid
import smtplib
import urllib.request
import urllib.error
import pyotp
import psycopg2
import psycopg2.extras
import time
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from werkzeug.utils import secure_filename
from markupsafe import escape
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g)

UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), 'static', 'images')
ALLOWED_EXTENSIONS = {'jpg', 'jpeg', 'png', 'webp', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def save_upload(file_field):
    f = request.files.get(file_field)
    if f and f.filename and allowed_file(f.filename):
        ext = f.filename.rsplit('.', 1)[1].lower()
        filename = f'cantina-fragapane-evenement-{uuid.uuid4().hex[:8]}.{ext}'
        f.save(os.path.join(UPLOAD_FOLDER, filename))
        return filename
    return None

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cantina-fragapane-secret-2024')
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 2592000  # 30 j : cache des fichiers statiques (perf)
ASSET_VERSION = str(int(time.time()))  # stable pour un déploiement, change à chaque redéploiement

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'fragapane2024')
TOTP_SECRET = os.environ.get('TOTP_SECRET', '')   # Google Authenticator (secret base32)
ADMIN_PIN = os.environ.get('ADMIN_PIN', '')       # PIN de secours à 6 chiffres
SITE_URL = os.environ.get('SITE_URL', 'https://www.cantinafragapane.be')

# ── Anti-brute-force sur /admin/login : 3 essais puis blocage temporaire ──
LOGIN_MAX_ATTEMPTS = 3
LOGIN_BLOCK_MINUTES = 15
_login_attempts = {}   # ip -> {'count': int, 'until': datetime|None}

def _client_ip():
    return (request.headers.get('CF-Connecting-IP')
            or request.headers.get('X-Forwarded-For', '').split(',')[0].strip()
            or request.remote_addr or 'unknown')


@app.after_request
def _security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    resp.headers.setdefault('Permissions-Policy', 'geolocation=(), microphone=(), camera=()')
    resp.headers.setdefault('Strict-Transport-Security', 'max-age=15552000')
    return resp

# Connexion PostgreSQL — on préfère les variables individuelles (plus fiables sur Railway)
import urllib.parse as _urlparse

def _build_database_url():
    pghost = os.environ.get('PGHOST', '')
    pgport = os.environ.get('PGPORT', '5432')
    pguser = os.environ.get('PGUSER', '')
    pgpass = os.environ.get('PGPASSWORD', '')
    pgdb   = os.environ.get('PGDATABASE') or os.environ.get('POSTGRES_DB', '')
    if pghost and pguser:
        return (
            f"postgresql://{_urlparse.quote(pguser, safe='')}:"
            f"{_urlparse.quote(pgpass, safe='')}@{pghost}:{pgport}/{pgdb}"
        )
    # Fallback : DATABASE_URL brute (peut contenir "DATABASE_URL=..." — on nettoie)
    raw = os.environ.get('DATABASE_URL', '')
    if '=' in raw and not raw.startswith(('postgres://', 'postgresql://')):
        raw = raw.split('=', 1)[1]
    if raw:
        return raw
    raise RuntimeError(
        "Aucune variable PostgreSQL trouvée. "
        "Dans Railway → service web → Variables → Raw Editor, ajoute :\n"
        "PGHOST=${{Postgres.PGHOST}}\n"
        "PGPORT=${{Postgres.PGPORT}}\n"
        "PGUSER=${{Postgres.PGUSER}}\n"
        "PGPASSWORD=${{Postgres.PGPASSWORD}}\n"
        "PGDATABASE=${{Postgres.PGDATABASE}}"
    )

DATABASE_URL = _build_database_url()


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = psycopg2.connect(DATABASE_URL,
                                cursor_factory=psycopg2.extras.RealDictCursor)
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().cursor()
    cur.execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    db = get_db()
    cur = db.cursor()
    cur.execute(sql, args)
    db.commit()


# ── Init & Seed ───────────────────────────────────────────────────────────────

def init_db():
    db = psycopg2.connect(DATABASE_URL,
                          cursor_factory=psycopg2.extras.RealDictCursor)
    cur = db.cursor()

    cur.execute('''
        CREATE TABLE IF NOT EXISTS menu_categories (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            icon       TEXT DEFAULT '🍽️',
            sort_order INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS menu_items (
            id          SERIAL PRIMARY KEY,
            category_id INTEGER NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            price       REAL,
            allergens   TEXT,
            available   INTEGER DEFAULT 1,
            featured    INTEGER DEFAULT 0,
            sort_order  INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS hours (
            id           SERIAL PRIMARY KEY,
            day_name     TEXT NOT NULL,
            day_order    INTEGER NOT NULL,
            lunch_open   TEXT,
            lunch_close  TEXT,
            dinner_open  TEXT,
            dinner_close TEXT,
            is_closed    INTEGER DEFAULT 0
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS info (
            key   TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS announcements (
            id         SERIAL PRIMARY KEY,
            message    TEXT NOT NULL,
            active     INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS evenements (
            id          SERIAL PRIMARY KEY,
            titre       TEXT NOT NULL,
            description TEXT,
            date_event  TEXT,
            image       TEXT,
            active      INTEGER DEFAULT 1,
            epingle     INTEGER DEFAULT 0,
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS reservations (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            phone      TEXT NOT NULL,
            date       TEXT NOT NULL,
            time       TEXT NOT NULL,
            guests     INTEGER NOT NULL,
            notes      TEXT,
            status     TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS newsletter_subscribers (
            id         SERIAL PRIMARY KEY,
            email      TEXT UNIQUE NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('''
        CREATE TABLE IF NOT EXISTS messages (
            id         SERIAL PRIMARY KEY,
            name       TEXT NOT NULL,
            email      TEXT,
            phone      TEXT,
            message    TEXT NOT NULL,
            is_read    INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cur.execute('ALTER TABLE reservations ADD COLUMN IF NOT EXISTS email TEXT')
    db.commit()

    cur.execute('SELECT COUNT(*) AS c FROM menu_categories')
    if cur.fetchone()['c'] == 0:
        _seed(db)

    db.commit()
    db.close()


def _seed(db):
    cur = db.cursor()

    cats = [
        ('Antipasti',        '🫒', 1),
        ('Pasta Fresca',     '🍝', 2),
        ('Carni & Grigliata','🥩', 3),
        ('Dolci',            '🍮', 4),
    ]
    for name, icon, order in cats:
        cur.execute(
            'INSERT INTO menu_categories (name, icon, sort_order) VALUES (%s,%s,%s)',
            (name, icon, order))

    items = [
        # Antipasti
        (1,'Planche Mixte Maison',
           "Charcuteries italiennes, fromages affinés, bruschetta et olives marinées",
           18.50,'',1,1,1),
        (1,'Burrata Pugliese',
           "Burrata crémeuse, tomates anciennes, basilic frais et huile d'olive extra vierge",
           14.00,'Lactose',1,1,2),
        (1,'Croquettes au Fromage',
           "Croquettes croustillantes au cœur fondant, sauce tomate maison",
           10.00,'Gluten, Lactose',1,0,3),
        (1,'Carpaccio di Manzo',
           "Fines tranches de bœuf Angus, roquette, parmesan, câpres et citron",
           15.50,'',1,0,4),
        # Pasta
        (2,'Raviolis aux Truffes',
           "Raviolis frais ricotta-épinards, crème à la truffe noire et parmesan",
           22.00,'Gluten, Lactose, Œufs',1,1,1),
        (2,'Tagliatelles à la Chicorée',
           "Tagliatelles fraîches, chicorée braisée, pancetta et pecorino",
           18.50,'Gluten, Lactose, Œufs',1,1,2),
        (2,'Pasta au Saumon',
           "Saumon frais, crème fraîche, aneth et zeste de citron",
           19.00,'Gluten, Lactose, Poisson',1,0,3),
        (2,'Spaghetti Carbonara',
           "La vraie carbonara romaine : guanciale, œuf, pecorino et poivre noir",
           17.00,'Gluten, Lactose, Œufs',1,0,4),
        (2,'Tagliatelles Bolognaise',
           "Ragù maison mijoté 4h, tagliatelles fraîches et parmesan",
           18.00,'Gluten, Lactose, Œufs',1,0,5),
        # Carni
        (3,'Arrosticini Abruzzesi',
           "Brochettes d'agneau traditionnelles des Abruzzes, grillées au feu de bois",
           16.00,'',1,1,1),
        (3,'Brochettes Mixtes',
           "Assortiment de brochettes bœuf & poulet marinés aux herbes italiennes",
           18.00,'',1,0,2),
        (3,'Entrecôte Angus',
           "Entrecôte de bœuf Angus grillée, sauce au choix et frites maison",
           28.00,'Lactose',1,1,3),
        (3,'Escalope à la Milanaise',
           "Escalope de veau panée, citron, câpres et salade fraîche",
           22.00,'Gluten, Lactose, Œufs',1,0,4),
        # Dolci
        (4,'Tiramisu Maison',
           "La recette authentique : mascarpone, espresso, savoiardi et cacao",
           8.00,'Gluten, Lactose, Œufs',1,1,1),
        (4,'Mousse au Chocolat',
           "Mousse légère au chocolat noir 70%, coulis de fruits rouges",
           7.50,'Lactose, Œufs',1,0,2),
        (4,'Panna Cotta',
           "Panna cotta vanille, coulis de fruits de saison",
           7.00,'Lactose',1,0,3),
    ]
    for it in items:
        cur.execute('''INSERT INTO menu_items
            (category_id,name,description,price,allergens,available,featured,sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''', it)

    hours_data = [
        ('Lundi',    1, None,    None,    '18:30','22:00', 0),
        ('Mardi',    2, None,    None,    None,   None,    1),
        ('Mercredi', 3, None,    None,    None,   None,    1),
        ('Jeudi',    4, None,    None,    '18:30','22:00', 0),
        ('Vendredi', 5, None,    None,    '18:30','22:00', 0),
        ('Samedi',   6, '12:00', '14:00', '18:30','22:00', 0),
        ('Dimanche', 7, '12:00', '14:00', '18:30','22:00', 0),
    ]
    for h in hours_data:
        cur.execute('''INSERT INTO hours
            (day_name,day_order,lunch_open,lunch_close,dinner_open,dinner_close,is_closed)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''', h)

    info_data = [
        ('name',              'La Cantina Fragapane'),
        ('tagline',           'Cucina italiana autentica'),
        ('subtitle',          "Le goût de l'Italie au cœur de Châtelet"),
        ('address',           'Rue du Taillis Pré 86'),
        ('city',              '6200 Châtelet, Belgique'),
        ('phone',             '+32 491 22 72 07'),
        ('email',             'info@cantinafragapane.be'),
        ('facebook',          'https://www.facebook.com/p/Cantina-Fragapane-100087290589959/'),
        ('instagram',         ''),
        ('about_short',       "Un petit coin d'Italie au cœur de Châtelet, fondé par Carlo et Brenda "
                              "— un couple uni depuis 27 ans par la passion de la cuisine méditerranéenne."),
        ('about_long',        "Chez La Cantina Fragapane, tout est fait maison avec amour : pâtes fraîches "
                              "du jour, sauces mijotées, desserts gourmands. Nous sélectionnons soigneusement "
                              "nos produits pour vous offrir le meilleur de la gastronomie italienne dans une "
                              "ambiance chaleureuse et familiale. Chaque visite est une invitation au voyage "
                              "— directement dans les saveurs authentiques de l'Italie."),
        ('reservation_note',  'Réservation vivement recommandée, particulièrement le week-end. '
                              'Contactez-nous par téléphone ou par email.'),
        ('price_range',       '€€'),
        ('google_maps_embed', ''),
    ]
    for key, val in info_data:
        cur.execute(
            'INSERT INTO info (key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value',
            (key, val))

    cur.execute('''INSERT INTO evenements (titre, description, date_event, image, active, epingle)
                   VALUES (%s,%s,%s,%s,1,1)''', (
        '⚠️ Dimanche 10 mai – Fête des mères ⚠️',
        'Nous aurons le menu qui sera disponible mais nous aurons également la carte à disposition pour ceux qui ne veulent pas le menu.',
        '2025-05-10',
        'cantina-fragapane-evenement-fete-des-meres-mai-2025.jpeg',
    ))

    db.commit()


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ── Open/closed status ────────────────────────────────────────────────────────

def get_open_status():
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo('Europe/Brussels'))
    except Exception:
        now = datetime.utcnow()

    day_order = now.weekday() + 1  # 1=Lundi … 7=Dimanche
    h = query('SELECT * FROM hours WHERE day_order=%s', (day_order,), one=True)

    if not h or h['is_closed']:
        return {'open': False, 'label': "Fermé aujourd'hui", 'color': 'closed'}

    t = now.strftime('%H:%M')

    if h['lunch_open'] and h['lunch_close']:
        if h['lunch_open'] <= t < h['lunch_close']:
            return {'open': True, 'label': f"Ouvert · jusqu'à {h['lunch_close']}", 'color': 'open'}

    if h['dinner_open'] and h['dinner_close']:
        if h['dinner_open'] <= t < h['dinner_close']:
            return {'open': True, 'label': f"Ouvert · jusqu'à {h['dinner_close']}", 'color': 'open'}

    if h['lunch_close'] and h['dinner_open'] and h['lunch_close'] <= t < h['dinner_open']:
        return {'open': False, 'label': f"Fermé · rouvre à {h['dinner_open']}", 'color': 'soon'}

    if h['lunch_open'] and t < h['lunch_open']:
        return {'open': False, 'label': f"Ouvre à {h['lunch_open']}", 'color': 'soon'}

    if not h['lunch_open'] and h['dinner_open'] and t < h['dinner_open']:
        return {'open': False, 'label': f"Ouvre à {h['dinner_open']}", 'color': 'soon'}

    return {'open': False, 'label': 'Fermé pour ce soir', 'color': 'closed'}


# ── Email contact ─────────────────────────────────────────────────────────────

def _send_via_brevo(subject, body, to_addr, reply_to=None, html=None):
    """Envoi via l'API HTTPS de Brevo (fonctionne depuis Render, contrairement au SMTP direct)."""
    key = os.environ.get('BREVO_API_KEY', '')
    if not key:
        return False
    sender = os.environ.get('MAIL_FROM') or os.environ.get('MAIL_USERNAME') or 'info@cantinafragapane.be'
    payload = {
        "sender":  {"name": "La Cantina Fragapane", "email": sender},
        "to":      [{"email": to_addr}],
        "subject": subject,
        "textContent": body,
    }
    if html:
        payload["htmlContent"] = html
    if reply_to:
        payload["replyTo"] = {"email": reply_to}
    req = urllib.request.Request(
        "https://api.brevo.com/v3/smtp/email",
        data=json.dumps(payload).encode('utf-8'),
        headers={"api-key": key, "content-type": "application/json", "accept": "application/json"},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return 200 <= resp.status < 300
    except urllib.error.HTTPError as e:
        detail = ''
        try:
            detail = e.read().decode('utf-8', 'ignore')[:300]
        except Exception:
            pass
        app.logger.warning('Échec envoi email (Brevo) HTTP %s : %s', e.code, detail)
        return False
    except Exception as e:
        app.logger.warning('Échec envoi email (Brevo) : %s', e)
        return False


def send_contact_email(name, sender_email, phone, message):
    to_addr = os.environ.get('MAIL_TO') or os.environ.get('MAIL_USERNAME') or 'info@cantinafragapane.be'
    subject = f'[Cantina Fragapane] Message de {name}'
    body = (f"Nom : {name}\nEmail : {sender_email}\nTéléphone : {phone}\n\n"
            f"Message :\n{message}")

    # 1) Brevo (API HTTPS) — méthode recommandée depuis Render
    if os.environ.get('BREVO_API_KEY'):
        return _send_via_brevo(subject, body, to_addr, reply_to=sender_email)

    # 2) SMTP direct (repli — souvent bloqué par les hébergeurs cloud)
    server   = os.environ.get('MAIL_SERVER', 'mail.cantinafragapane.be')
    port     = int(os.environ.get('MAIL_PORT', '587'))
    username = os.environ.get('MAIL_USERNAME', '')
    password = os.environ.get('MAIL_PASSWORD', '')
    if not username or not password:
        app.logger.warning('Email non envoyé : ni BREVO_API_KEY ni MAIL_USERNAME/PASSWORD configurés.')
        return False
    msg = MIMEMultipart()
    msg['From']    = username
    msg['To']      = to_addr
    msg['Subject'] = subject
    if sender_email:
        msg['Reply-To'] = sender_email
    msg.attach(MIMEText(body, 'plain', 'utf-8'))
    try:
        if port == 465:
            with smtplib.SMTP_SSL(server, port, timeout=15) as srv:
                srv.login(username, password)
                srv.send_message(msg)
        else:
            with smtplib.SMTP(server, port, timeout=15) as srv:
                srv.starttls()
                srv.login(username, password)
                srv.send_message(msg)
        return True
    except Exception as e:
        app.logger.warning('Échec envoi email (SMTP) : %s', e)
        return False


def _ack_html(name, intro):
    """Modèle HTML de l'accusé de réception envoyé au client (intro = paragraphe central)."""
    safe = escape(name)
    return f"""\
<div style="background:#f4f1ea;padding:24px 12px;font-family:Arial,Helvetica,sans-serif;">
 <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
  <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="max-width:480px;width:100%;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e9e0d3;">
   <tr><td style="padding:0;font-size:0;line-height:0;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
     <td width="33%" style="height:5px;line-height:5px;background:#009246;">&nbsp;</td>
     <td width="34%" style="height:5px;line-height:5px;background:#ffffff;">&nbsp;</td>
     <td width="33%" style="height:5px;line-height:5px;background:#ce2b37;">&nbsp;</td>
    </tr></table>
   </td></tr>
   <tr><td style="background:#15221a;padding:28px 24px;text-align:center;">
    <div style="color:#c9984a;font-size:11px;letter-spacing:3px;text-transform:uppercase;font-weight:bold;">La Cantina</div>
    <div style="color:#ffffff;font-family:Georgia,'Times New Roman',serif;font-size:26px;font-weight:bold;margin-top:2px;">Fragapane</div>
   </td></tr>
   <tr><td style="padding:30px 30px 26px;">
    <p style="font-size:16px;margin:0 0 14px;color:#2b2620;">Bonjour <strong>{safe}</strong>,</p>
    {intro}
    <p style="font-size:15px;line-height:1.65;margin:0 0 24px;color:#4a453e;">Pour une demande urgente ou une réservation du jour, le plus simple est de nous appeler&nbsp;:</p>
    <table role="presentation" cellpadding="0" cellspacing="0" align="center" style="margin:0 auto;"><tr>
     <td style="border-radius:10px;background:#c9984a;"><a href="tel:+32491227207" style="display:inline-block;padding:13px 28px;color:#ffffff;font-weight:bold;font-size:15px;text-decoration:none;">&#128222;&nbsp; +32 491 22 72 07</a></td>
    </tr></table>
   </td></tr>
   <tr><td style="background:#faf7f2;padding:20px 30px;border-top:1px solid #eee3d3;color:#7a7065;font-size:13px;line-height:1.7;text-align:center;">
    <strong style="color:#2b2620;">La Cantina Fragapane</strong><br>
    Rue du Taillis Pré 86, 6200 Châtelet<br>
    <a href="https://www.cantinafragapane.be" style="color:#c9984a;text-decoration:none;">cantinafragapane.be</a> &nbsp;&middot;&nbsp;
    <a href="https://www.cantinafragapane.be/menu" style="color:#c9984a;text-decoration:none;">Voir le menu</a>
   </td></tr>
  </table>
  <p style="color:#a89e8f;font-size:11px;margin:16px 0 0;">Message automatique de confirmation, merci de ne pas y répondre.</p>
 </td></tr></table>
</div>"""


_ACK_P = 'font-size:15px;line-height:1.65;margin:0 0 14px;color:#4a453e;'

def send_customer_ack(name, to_email):
    """Accusé de réception automatique — formulaire de contact."""
    if not to_email or not os.environ.get('BREVO_API_KEY'):
        return False
    subject = "Merci pour votre message – La Cantina Fragapane"
    text = (f"Bonjour {name},\n\nMerci pour votre message ! Nous l'avons bien reçu et nous vous "
            "répondrons dans les meilleurs délais.\n\nPour une demande urgente, appelez-nous au "
            "+32 491 22 72 07.\n\nÀ très bientôt,\nL'équipe de La Cantina Fragapane\n"
            "Rue du Taillis Pré 86, 6200 Châtelet — cantinafragapane.be")
    intro = (f'<p style="{_ACK_P}">Merci pour votre message&nbsp;! Nous l\'avons bien reçu et nous '
             'vous répondrons dans les <strong>meilleurs délais</strong>.</p>')
    return _send_via_brevo(subject, text, to_email, html=_ack_html(name, intro))


def send_reservation_ack(name, to_email, date, time, guests):
    """Accusé de réception automatique — demande de réservation."""
    if not to_email or not os.environ.get('BREVO_API_KEY'):
        return False
    subject = "Votre demande de réservation – La Cantina Fragapane"
    text = (f"Bonjour {name},\n\nNous avons bien reçu votre demande de réservation pour le {date} "
            f"à {time} ({guests} pers.). Nous vous recontactons rapidement pour la confirmer.\n\n"
            "Pour toute urgence, appelez-nous au +32 491 22 72 07.\n\nÀ très bientôt,\n"
            "L'équipe de La Cantina Fragapane\nRue du Taillis Pré 86, 6200 Châtelet — cantinafragapane.be")
    intro = (f'<p style="{_ACK_P}">Nous avons bien reçu votre <strong>demande de réservation</strong> '
             f'pour le <strong>{escape(str(date))}</strong> à <strong>{escape(str(time))}</strong> '
             f'({escape(str(guests))}&nbsp;pers.). Nous vous recontactons rapidement pour la <strong>confirmer</strong>.</p>')
    return _send_via_brevo(subject, text, to_email, html=_ack_html(name, intro))


def build_restaurant_jsonld(info, hours):
    """Génère le JSON-LD Restaurant (fiable, échappement JSON correct)."""
    days_map = {"Lundi": "Monday", "Mardi": "Tuesday", "Mercredi": "Wednesday", "Jeudi": "Thursday",
                "Vendredi": "Friday", "Samedi": "Saturday", "Dimanche": "Sunday"}
    specs = []
    for h in hours:
        if h.get('is_closed'):
            continue
        day = days_map.get(h['day_name'], h['day_name'])
        if h.get('lunch_open') and h.get('lunch_close'):
            specs.append({"@type": "OpeningHoursSpecification", "dayOfWeek": day,
                          "opens": h['lunch_open'], "closes": h['lunch_close']})
        if h.get('dinner_open') and h.get('dinner_close'):
            specs.append({"@type": "OpeningHoursSpecification", "dayOfWeek": day,
                          "opens": h['dinner_open'], "closes": h['dinner_close']})
    city = info.get('city', '')
    locality = city.split(',')[0].strip() if ',' in city else city
    data = {
        "@context": "https://schema.org",
        "@type": "Restaurant",
        "name": info.get('name', 'La Cantina Fragapane'),
        "description": info.get('about_short', "Restaurant italien authentique à Châtelet, fondé par "
                                "Carlo et Brenda. Pâtes fraîches maison, viandes grillées, arrosticinis, "
                                "livraison à domicile."),
        "url": SITE_URL,
        "telephone": info.get('phone', '').replace(' ', ''),
        "email": info.get('email', ''),
        "address": {"@type": "PostalAddress", "streetAddress": info.get('address', ''),
                    "addressLocality": locality, "postalCode": "6200", "addressCountry": "BE"},
        "geo": {"@type": "GeoCoordinates", "latitude": 50.4012, "longitude": 4.5278},
        "servesCuisine": "Italienne",
        "priceRange": info.get('price_range', '€€'),
        "currenciesAccepted": "EUR",
        "openingHoursSpecification": specs,
        "hasMenu": SITE_URL + "/menu",
        "acceptsReservations": True,
        "image": SITE_URL + "/static/images/cantina-fragapane-salle-restaurant-neon-chatelet.jpeg",
    }
    sameas = [x for x in (info.get('facebook'), info.get('instagram')) if x]
    if sameas:
        data["sameAs"] = sameas
    return json.dumps(data, ensure_ascii=False)


# ── Context processors ────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    info = {r['key']: r['value']
            for r in query('SELECT key, value FROM info')}
    announcements = query(
        'SELECT * FROM announcements WHERE active=1 ORDER BY created_at DESC')
    evenements = query(
        'SELECT * FROM evenements WHERE active=1 ORDER BY epingle DESC, date_event DESC LIMIT 6')
    open_status = get_open_status()
    hours_all = query('SELECT * FROM hours ORDER BY day_order')
    restaurant_jsonld = build_restaurant_jsonld(info, hours_all)
    return dict(info=info, announcements=announcements, evenements=evenements,
                open_status=open_status, hours=hours_all, asset_version=ASSET_VERSION,
                restaurant_jsonld=restaurant_jsonld,
                now=datetime.now(), site_url=SITE_URL)


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_hours():
    return query('SELECT * FROM hours ORDER BY day_order')


def get_full_menu():
    cats = query('SELECT * FROM menu_categories ORDER BY sort_order')
    result = []
    for cat in cats:
        items = query(
            'SELECT * FROM menu_items WHERE category_id=%s AND available=1 ORDER BY sort_order',
            (cat['id'],))
        result.append({'category': cat, 'plats': items})
    return result


# ── Public routes ─────────────────────────────────────────────────────────────

@app.route('/healthz')
def healthz():
    """Endpoint ultra-léger pour le keep-alive (aucune requête BDD, réponse instantanée).
    Suffit à réveiller / maintenir éveillé le service Render."""
    return 'ok', 200, {'Cache-Control': 'no-store'}


@app.route('/')
def index():
    hours = get_hours()
    featured = query('''
        SELECT m.*, c.name AS cat_name
        FROM menu_items m
        JOIN menu_categories c ON m.category_id = c.id
        WHERE m.featured=1 AND m.available=1
          AND c.name IN ('Entrées','Pâtes Fraîches','Grillades')
        ORDER BY c.sort_order, m.sort_order
        LIMIT 6
    ''')
    reviews = [
        {'author': 'Christine B.',   'stars': 5,
         'text': "Repas très bon et généreusement servi, personnel très serviable. "
                 "Un vrai petit coin d'Italie !"},
        {'author': 'Cédric H.',      'stars': 5,
         'text': "Toujours au top. Prix super raisonnables, pâtes fraîches cuites "
                 "à la perfection. Je recommande !"},
        {'author': 'Marie-Claire D.','stars': 5,
         'text': "Accueil chaleureux, service rapide, personnel souriant et nourriture "
                 "fraîche. Une adresse à ne pas manquer !"},
    ]
    return render_template('index.html', hours=hours,
                           featured=featured, reviews=reviews)


@app.route('/menu')
def menu():
    menu_data = get_full_menu()
    # Données structurées Menu (rich results Google)
    sections = []
    for entry in menu_data:
        items = []
        for it in entry['plats']:
            mi = {"@type": "MenuItem", "name": it['name']}
            if it.get('description'):
                mi["description"] = it['description']
            if it.get('price'):
                mi["offers"] = {"@type": "Offer", "price": f"{float(it['price']):.2f}", "priceCurrency": "EUR"}
            items.append(mi)
        if items:
            sections.append({"@type": "MenuSection", "name": entry['category']['name'], "hasMenuItem": items})
    menu_jsonld = json.dumps(
        {"@context": "https://schema.org", "@type": "Menu",
         "name": "Menu – La Cantina Fragapane", "inLanguage": "fr",
         "hasMenuSection": sections}, ensure_ascii=False)
    return render_template('menu.html', menu_data=menu_data, menu_jsonld=menu_jsonld)


@app.route('/a-propos')
def a_propos():
    return render_template('a_propos.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    hours = get_hours()
    if request.method == 'POST':
        if request.form.get('website'):          # honeypot anti-spam
            return redirect(url_for('contact'))
        name    = request.form.get('name', '').strip()
        email   = request.form.get('email', '').strip()
        phone   = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()
        if name and message:
            # On enregistre TOUJOURS le message (visible dans /admin), même si l'email échoue
            execute('INSERT INTO messages (name, email, phone, message) VALUES (%s,%s,%s,%s)',
                    (name, email, phone, message))
            try:
                sent = send_contact_email(name, email, phone, message)
                send_customer_ack(name, email)   # accusé de réception automatique au client
                if sent:
                    flash('Votre message a bien été envoyé ! Nous vous répondrons bientôt.', 'success')
                else:
                    flash('Message reçu ! Pour une réponse rapide, appelez-nous directement.', 'success')
            except Exception:
                flash('Erreur d\'envoi. Appelez-nous au +32 491 22 72 07.', 'error')
        else:
            flash('Veuillez remplir votre nom et votre message.', 'error')
        return redirect(url_for('contact'))
    return render_template('contact.html', hours=hours)


@app.route('/livraison')
def livraison():
    return render_template('livraison.html')


@app.route('/reservation', methods=['GET', 'POST'])
def reservation():
    if request.method == 'POST':
        if request.form.get('website'):          # honeypot anti-spam
            return redirect(url_for('reservation'))
        name   = request.form.get('name', '').strip()
        email  = request.form.get('email', '').strip()
        phone  = request.form.get('phone', '').strip()
        date   = request.form.get('date', '').strip()
        time   = request.form.get('time', '').strip()
        guests = request.form.get('guests', '').strip()
        notes  = request.form.get('notes', '').strip()
        if name and phone and date and time and guests.isdigit():
            execute(
                'INSERT INTO reservations (name,email,phone,date,time,guests,notes) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                (name, email or None, phone, date, time, int(guests), notes or None))
            try:
                body = (f"Nouvelle demande de réservation :\n\n"
                        f"Nom : {name}\nEmail : {email or '—'}\nTéléphone : {phone}\n"
                        f"Date : {date} à {time}\nPersonnes : {guests}\n"
                        f"Notes : {notes or '—'}")
                send_contact_email(name, email, phone,
                                   f"[RÉSERVATION] {date} {time} – {guests} pers.\n\n{body}")
                send_reservation_ack(name, email, date, time, guests)
            except Exception:
                pass
            flash('Demande reçue ! Nous vous confirmons par téléphone dans les 2h.', 'success')
        else:
            flash('Veuillez remplir tous les champs obligatoires.', 'error')
        if request.form.get('from') == 'home':
            return redirect(url_for('index') + '#reserver')
        return redirect(url_for('reservation'))
    hours = query('SELECT * FROM hours ORDER BY day_order')
    return render_template('reservation.html', hours=hours)


@app.route('/newsletter/subscribe', methods=['POST'])
def newsletter_subscribe():
    email = request.form.get('email', '').strip().lower()
    if email and '@' in email:
        try:
            execute('INSERT INTO newsletter_subscribers (email) VALUES (%s) ON CONFLICT DO NOTHING', (email,))
            flash('Inscription réussie ! Merci de votre fidélité.', 'success')
        except Exception:
            flash('Une erreur est survenue.', 'error')
    else:
        flash('Adresse email invalide.', 'error')
    return redirect(request.referrer or url_for('index'))


@app.route('/desinscription', methods=['GET', 'POST'])
def newsletter_unsubscribe():
    done = False
    if request.method == 'POST':
        if not request.form.get('website'):      # honeypot
            email = request.form.get('email', '').strip().lower()
            if email:
                execute('DELETE FROM newsletter_subscribers WHERE lower(email)=%s', (email,))
        done = True
    return render_template('desinscription.html', done=done)


@app.route('/galerie')
def galerie():
    photos = [
        {'file': 'cantina-fragapane-salle-restaurant-neon-chatelet.jpeg',
         'alt': 'Salle du restaurant La Cantina Fragapane – néon et ambiance italienne', 'cat': 'Salle'},
        {'file': 'cantina-fragapane-salle-tables-neon-soir-chatelet.jpeg',
         'alt': 'Tables dressées le soir – La Cantina Fragapane Châtelet', 'cat': 'Salle'},
        {'file': 'cantina-fragapane-salle-interieur-cheminee-chatelet.jpeg',
         'alt': 'Intérieur chaleureux avec cheminée – La Cantina Fragapane', 'cat': 'Salle'},
        {'file': 'cantina-fragapane-devanture-vitrine-logo-chatelet.jpeg',
         'alt': 'Devanture et vitrine La Cantina Fragapane – Châtelet', 'cat': 'Restaurant'},
        {'file': 'cantina-fragapane-equipe-famille-carlo-brenda-chatelet.jpeg',
         'alt': 'Carlo, Brenda et leur fils – La Cantina Fragapane', 'cat': 'Équipe'},
        {'file': 'cantina-fragapane-prix-meilleur-restaurant-italien-chatelet-restaurant-guru-2025.jpeg',
         'alt': 'Prix meilleur restaurant italien 2025 – Restaurant Guru', 'cat': 'Restaurant'},
        {'file': 'cantina-fragapane-grande-planche-apero-antipasti-chatelet.jpeg',
         'alt': 'Grande planche apéro antipasti – La Cantina Fragapane', 'cat': 'Plats'},
        {'file': 'cantina-fragapane-planche-antipasti-signature-logo-chatelet.jpeg',
         'alt': 'Planche antipasti signature – La Cantina Fragapane Châtelet', 'cat': 'Plats'},
        {'file': 'cantina-fragapane-croquettes-fromage-salade-chatelet.jpeg',
         'alt': 'Croquettes au fromage et salade fraîche – La Cantina Fragapane', 'cat': 'Plats'},
        {'file': 'cantina-fragapane-casarecce-pesto-ricotta-pro-chatelet.jpeg',
         'alt': 'Casarecce pesto ricotta – Pâtes fraîches maison La Cantina Fragapane', 'cat': 'Pâtes'},
        {'file': 'cantina-fragapane-tagliatelles-bolognaise-sauce-tomate-chatelet.jpeg',
         'alt': 'Tagliatelles bolognaise maison – La Cantina Fragapane', 'cat': 'Pâtes'},
        {'file': 'cantina-fragapane-tagliolini-safran-petits-pois-pancetta-chatelet.jpeg',
         'alt': 'Tagliolini safran petits pois pancetta – La Cantina Fragapane', 'cat': 'Pâtes'},
        {'file': 'cantina-fragapane-spaghetti-fruits-de-mer-tomates-chatelet.jpeg',
         'alt': 'Spaghetti aux fruits de mer – La Cantina Fragapane Châtelet', 'cat': 'Pâtes'},
        {'file': 'cantina-fragapane-escalope-milanaise-spaghetti-tomates-chatelet.jpeg',
         'alt': 'Escalope milanaise et spaghetti tomates – La Cantina Fragapane', 'cat': 'Viandes'},
        {'file': 'cantina-fragapane-plateau-desserts-verrines-chatelet.jpeg',
         'alt': 'Plateau de desserts et verrines – La Cantina Fragapane', 'cat': 'Desserts'},
        {'file': 'cantina-fragapane-logo-trattoria-italienne-chatelet.jpeg',
         'alt': 'Logo La Cantina Fragapane – Trattoria italienne Châtelet', 'cat': 'Restaurant'},
        {'file': 'cantina-fragapane-evenement-fete-des-meres-mai-2025.jpeg',
         'alt': 'Fête des mères mai 2025 – Événement La Cantina Fragapane', 'cat': 'Événements'},
    ]
    return render_template('galerie.html', photos=photos)


@app.route('/faq')
def faq():
    return render_template('faq.html')


@app.route('/evenements-prives')
def evenements_prives():
    return render_template('evenements_prives.html')


@app.route('/mentions-legales')
def mentions_legales():
    return render_template('legal/mentions_legales.html')

@app.route('/confidentialite')
def confidentialite():
    return render_template('legal/confidentialite.html')

@app.route('/cgv')
def cgv():
    return render_template('legal/cgv.html')

@app.route('/cookies')
def cookies_page():
    return render_template('legal/cookies.html')


# Les routes /sitemap.xml et /robots.txt sont définies plus bas (basées sur SITE_URL).


# ── Admin – auth ──────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    error = None
    strong_auth = bool(TOTP_SECRET or ADMIN_PIN)
    if request.method == 'POST':
        ip = _client_ip()
        now = datetime.now()
        rec = _login_attempts.get(ip, {'count': 0, 'until': None})

        # Bloqué ?
        if rec['until'] and rec['until'] > now:
            mins = int((rec['until'] - now).total_seconds() // 60) + 1
            error = f"Trop de tentatives. Réessayez dans {mins} min."
            return render_template('admin/login.html', error=error, strong_auth=strong_auth)

        code = (request.form.get('code') or request.form.get('password') or '').strip().replace(' ', '')
        ok = False
        # 1) Code Google Authenticator (TOTP)
        if TOTP_SECRET and code:
            try:
                if pyotp.TOTP(TOTP_SECRET).verify(code, valid_window=1):
                    ok = True
            except Exception:
                pass
        # 2) PIN de secours à 6 chiffres
        if not ok and ADMIN_PIN and code and code == ADMIN_PIN:
            ok = True
        # 3) Filet de sécurité : ancien mot de passe, uniquement tant que
        #    ni Google Authenticator ni PIN ne sont configurés (évite le blocage).
        if not ok and not TOTP_SECRET and not ADMIN_PIN and code and code == ADMIN_PASSWORD:
            ok = True

        if ok:
            _login_attempts.pop(ip, None)
            session['admin'] = True
            flash("Bienvenue dans l'espace admin !", 'success')
            return redirect(url_for('admin_dashboard'))

        # Échec → on compte, et on bloque après LOGIN_MAX_ATTEMPTS
        rec['count'] += 1
        if rec['count'] >= LOGIN_MAX_ATTEMPTS:
            rec['until'] = now + timedelta(minutes=LOGIN_BLOCK_MINUTES)
            rec['count'] = 0
            error = f"Trop de tentatives. Connexion bloquée pendant {LOGIN_BLOCK_MINUTES} min."
        else:
            left = LOGIN_MAX_ATTEMPTS - rec['count']
            error = f"Code incorrect. Il reste {left} essai{'s' if left > 1 else ''}."
        _login_attempts[ip] = rec

    return render_template('admin/login.html', error=error, strong_auth=strong_auth)


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('admin_login'))


# ── Admin – dashboard ─────────────────────────────────────────────────────────

@app.route('/admin/')
@app.route('/admin')
@login_required
def admin_dashboard():
    stats = {
        'categories':  query('SELECT COUNT(*) AS c FROM menu_categories', one=True)['c'],
        'plats':       query('SELECT COUNT(*) AS c FROM menu_items WHERE available=1', one=True)['c'],
        'annonces':    query('SELECT COUNT(*) AS c FROM announcements WHERE active=1', one=True)['c'],
        'reservations':query('SELECT COUNT(*) AS c FROM reservations WHERE status=%s', ('pending',), one=True)['c'],
        'newsletter':  query('SELECT COUNT(*) AS c FROM newsletter_subscribers', one=True)['c'],
    }
    return render_template('admin/dashboard.html', stats=stats)


# ── Admin – menu ──────────────────────────────────────────────────────────────

@app.route('/admin/menu')
@login_required
def admin_menu():
    cats = query('SELECT * FROM menu_categories ORDER BY sort_order')
    items_by_cat = {
        cat['id']: query(
            'SELECT * FROM menu_items WHERE category_id=%s ORDER BY sort_order',
            (cat['id'],))
        for cat in cats
    }
    return render_template('admin/menu.html', cats=cats, items_by_cat=items_by_cat)


@app.route('/admin/menu/categorie/ajouter', methods=['POST'])
@login_required
def admin_add_category():
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip()
    if name:
        max_o = query('SELECT MAX(sort_order) AS m FROM menu_categories', one=True)['m'] or 0
        execute('INSERT INTO menu_categories (name,icon,sort_order) VALUES (%s,%s,%s)',
                (name, icon, max_o + 1))
        flash(f'Catégorie « {name} » ajoutée.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/categorie/<int:cat_id>/modifier', methods=['POST'])
@login_required
def admin_edit_category(cat_id):
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip()
    if name:
        execute('UPDATE menu_categories SET name=%s, icon=%s WHERE id=%s', (name, icon, cat_id))
        flash('Catégorie mise à jour.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/categorie/<int:cat_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_category(cat_id):
    execute('DELETE FROM menu_items WHERE category_id=%s', (cat_id,))
    execute('DELETE FROM menu_categories WHERE id=%s', (cat_id,))
    flash('Catégorie supprimée.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/plat/ajouter', methods=['POST'])
@login_required
def admin_add_item():
    f = request.form
    cat_id = int(f.get('category_id', 0) or 0)
    name   = f.get('name', '').strip()
    if cat_id and name:
        price = f.get('price', '').strip()
        price = float(price) if price else None
        max_o = (query('SELECT MAX(sort_order) AS m FROM menu_items WHERE category_id=%s',
                       (cat_id,), one=True)['m'] or 0)
        execute('''INSERT INTO menu_items
            (category_id,name,description,price,allergens,available,featured,sort_order)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
                (cat_id, name, f.get('description', ''), price,
                 f.get('allergens', ''),
                 1 if f.get('available') else 0,
                 1 if f.get('featured')  else 0,
                 max_o + 1))
        flash(f'Plat « {name} » ajouté.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/plat/<int:item_id>/modifier', methods=['POST'])
@login_required
def admin_edit_item(item_id):
    f     = request.form
    price = f.get('price', '').strip()
    price = float(price) if price else None
    execute('''UPDATE menu_items
               SET name=%s, description=%s, price=%s, allergens=%s, available=%s, featured=%s
               WHERE id=%s''',
            (f.get('name', ''), f.get('description', ''), price,
             f.get('allergens', ''),
             1 if f.get('available') else 0,
             1 if f.get('featured')  else 0,
             item_id))
    flash('Plat mis à jour.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/plat/<int:item_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_item(item_id):
    execute('DELETE FROM menu_items WHERE id=%s', (item_id,))
    flash('Plat supprimé.', 'success')
    return redirect(url_for('admin_menu'))


# ── Admin – hours ─────────────────────────────────────────────────────────────

@app.route('/admin/horaires')
@login_required
def admin_hours():
    hours = get_hours()
    return render_template('admin/hours.html', hours=hours)


@app.route('/admin/horaires/modifier', methods=['POST'])
@login_required
def admin_edit_hours():
    all_hours = query('SELECT id FROM hours')
    allowed_fields = ('lunch_open', 'lunch_close', 'dinner_open', 'dinner_close')

    for h in all_hours:
        hid = h['id']
        is_closed = 1 if request.form.get(f'h_{hid}_is_closed') else 0
        execute('UPDATE hours SET is_closed=%s WHERE id=%s', (is_closed, hid))

        for field in allowed_fields:
            val = request.form.get(f'h_{hid}_{field}', '').strip() or None
            execute(f'UPDATE hours SET {field}=%s WHERE id=%s', (val, hid))

    flash('Horaires mis à jour.', 'success')
    return redirect(url_for('admin_hours'))


# ── Admin – info ──────────────────────────────────────────────────────────────

@app.route('/admin/informations')
@login_required
def admin_info():
    raw = query('SELECT key, value FROM info')
    info_edit = {r['key']: r['value'] for r in raw}
    return render_template('admin/info.html', info_edit=info_edit)


@app.route('/admin/informations/modifier', methods=['POST'])
@login_required
def admin_edit_info():
    allowed = ['name','tagline','subtitle','address','city','phone','email',
               'facebook','instagram','about_short','about_long',
               'reservation_note','price_range','google_maps_embed','tripadvisor_embed']
    for key in allowed:
        val = request.form.get(key, '').strip()
        execute(
            'INSERT INTO info (key,value) VALUES (%s,%s) ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value',
            (key, val))
    flash('Informations mises à jour.', 'success')
    return redirect(url_for('admin_info'))


# ── Admin – events ───────────────────────────────────────────────────────────

@app.route('/admin/evenements')
@login_required
def admin_events():
    evts = query('SELECT * FROM evenements ORDER BY epingle DESC, date_event DESC, created_at DESC')
    return render_template('admin/events.html', evts=evts)


@app.route('/admin/evenements/ajouter', methods=['POST'])
@login_required
def admin_add_event():
    f = request.form
    image = save_upload('image')
    if not image:
        image = f.get('image_existing', '').strip() or None
    execute('''INSERT INTO evenements (titre, description, date_event, image, active, epingle)
               VALUES (%s,%s,%s,%s,%s,%s)''',
            (f.get('titre','').strip(), f.get('description','').strip(),
             f.get('date_event','').strip() or None, image,
             1 if f.get('active') else 0, 1 if f.get('epingle') else 0))
    flash('Événement ajouté.', 'success')
    return redirect(url_for('admin_events'))


@app.route('/admin/evenements/<int:evt_id>/modifier', methods=['POST'])
@login_required
def admin_edit_event(evt_id):
    f = request.form
    image = save_upload('image')
    if not image:
        image = f.get('image_existing', '').strip() or None
    execute('''UPDATE evenements
               SET titre=%s, description=%s, date_event=%s, image=%s, active=%s, epingle=%s
               WHERE id=%s''',
            (f.get('titre','').strip(), f.get('description','').strip(),
             f.get('date_event','').strip() or None, image,
             1 if f.get('active') else 0, 1 if f.get('epingle') else 0,
             evt_id))
    flash('Événement mis à jour.', 'success')
    return redirect(url_for('admin_events'))


@app.route('/admin/evenements/<int:evt_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_event(evt_id):
    execute('DELETE FROM evenements WHERE id=%s', (evt_id,))
    flash('Événement supprimé.', 'success')
    return redirect(url_for('admin_events'))


@app.route('/admin/evenements/<int:evt_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_event(evt_id):
    evt = query('SELECT active FROM evenements WHERE id=%s', (evt_id,), one=True)
    if evt:
        execute('UPDATE evenements SET active=%s WHERE id=%s',
                (0 if evt['active'] else 1, evt_id))
    return redirect(url_for('admin_events'))


# ── Admin – announcements ─────────────────────────────────────────────────────

@app.route('/admin/annonces')
@login_required
def admin_announcements():
    anns = query('SELECT * FROM announcements ORDER BY created_at DESC')
    return render_template('admin/announcements.html', anns=anns)


@app.route('/admin/annonces/ajouter', methods=['POST'])
@login_required
def admin_add_announcement():
    msg = request.form.get('message', '').strip()
    if msg:
        execute('INSERT INTO announcements (message, active) VALUES (%s,1)', (msg,))
        flash('Annonce ajoutée.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/annonces/<int:ann_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_announcement(ann_id):
    ann = query('SELECT active FROM announcements WHERE id=%s', (ann_id,), one=True)
    if ann:
        execute('UPDATE announcements SET active=%s WHERE id=%s',
                (0 if ann['active'] else 1, ann_id))
    return redirect(url_for('admin_announcements'))


@app.route('/admin/annonces/<int:ann_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_announcement(ann_id):
    execute('DELETE FROM announcements WHERE id=%s', (ann_id,))
    flash('Annonce supprimée.', 'success')
    return redirect(url_for('admin_announcements'))


# ── Admin – reservations ─────────────────────────────────────────────────────

@app.route('/admin/reservations')
@login_required
def admin_reservations():
    resas = query('SELECT * FROM reservations ORDER BY date DESC, time DESC')
    return render_template('admin/reservations.html', resas=resas)


@app.route('/admin/reservations/<int:resa_id>/status', methods=['POST'])
@login_required
def admin_resa_status(resa_id):
    status = request.form.get('status', 'pending')
    if status in ('pending', 'confirmed', 'cancelled'):
        execute('UPDATE reservations SET status=%s WHERE id=%s', (status, resa_id))
    return redirect(url_for('admin_reservations'))


@app.route('/admin/reservations/<int:resa_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_resa(resa_id):
    execute('DELETE FROM reservations WHERE id=%s', (resa_id,))
    flash('Réservation supprimée.', 'success')
    return redirect(url_for('admin_reservations'))


# ── Admin – newsletter ────────────────────────────────────────────────────────

@app.route('/admin/newsletter')
@login_required
def admin_newsletter():
    subs = query('SELECT * FROM newsletter_subscribers ORDER BY created_at DESC')
    return render_template('admin/newsletter.html', subs=subs)


@app.route('/admin/newsletter/<int:sub_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_sub(sub_id):
    execute('DELETE FROM newsletter_subscribers WHERE id=%s', (sub_id,))
    flash('Abonné supprimé.', 'success')
    return redirect(url_for('admin_newsletter'))


# ── Admin – messages de contact ───────────────────────────────────────────────

@app.route('/admin/messages')
@login_required
def admin_messages():
    msgs = query('SELECT * FROM messages ORDER BY created_at DESC')
    execute('UPDATE messages SET is_read=1 WHERE is_read=0')  # marqués lus à l'ouverture
    return render_template('admin/messages.html', msgs=msgs)


@app.route('/admin/messages/<int:msg_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_message(msg_id):
    execute('DELETE FROM messages WHERE id=%s', (msg_id,))
    flash('Message supprimé.', 'success')
    return redirect(url_for('admin_messages'))


# ── Reset Menu ───────────────────────────────────────────────────────────────

@app.route('/admin/reset-menu', methods=['GET', 'POST'])
@login_required
def admin_reset_menu():
    if request.method == 'GET':
        return render_template('admin/reset_menu_confirm.html')

    # POST → effectuer le reset
    db = get_db()
    cur = db.cursor()

    cur.execute('DELETE FROM menu_items')
    cur.execute('DELETE FROM menu_categories')
    # Réinitialise les séquences
    cur.execute("SELECT setval(pg_get_serial_sequence('menu_categories','id'), 1, false)")
    cur.execute("SELECT setval(pg_get_serial_sequence('menu_items','id'), 1, false)")

    # ── Catégories ──────────────────────────────────────────────────────────
    cats = [
        (1,  'Entrées',          '🫒',  1),
        (2,  'Pâtes Fraîches',   '🍝',  2),
        (3,  'Grillades',        '🥩',  3),
        (4,  'Desserts',         '🍮',  4),
        (5,  'Boissons Chaudes', '☕',  5),
        (6,  'Menu Enfants',     '🧒',  6),
        (7,  'Apéritifs',        '🥂',  7),
        (8,  'Cocktails',        '🍹',  8),
        (9,  'Alcools',          '🥃',  9),
        (10, 'Digestifs',        '🍾', 10),
        (11, 'Bières',           '🍺', 11),
        (12, 'Softs',            '🧃', 12),
        (13, 'Schweppes',        '🫧', 13),
    ]
    for cid, name, icon, order in cats:
        cur.execute(
            'INSERT INTO menu_categories (id, name, icon, sort_order) VALUES (%s,%s,%s,%s)',
            (cid, name, icon, order))
    # Avance la séquence après les insertions manuelles
    cur.execute("SELECT setval(pg_get_serial_sequence('menu_categories','id'), 13)")

    # ── Plats ───────────────────────────────────────────────────────────────
    # (category_id, name, description, price, allergens, available, featured, sort_order)
    items = [
        # ── Entrées ──────────────────────────────────────────────────────
        (1, 'La Planche Mixte',
         'Charcuteries italiennes, fromages affinés, bruschetta et olives marinées',
         17.00, '', 1, 1, 1),
        (1, 'La Planche Terre et Mer',
         'Sélection de charcuteries, fruits de mer et accompagnements maison',
         22.00, '', 1, 1, 2),
        (1, 'Scampis Ail ou Piquant',
         'Scampis sautés à l\'ail ou épicés, servis avec pain artisanal',
         17.00, 'Crustacés, Gluten', 1, 0, 3),
        (1, 'Scampis Diabolo',
         'Scampis flambés à la sauce diablo piquante',
         17.00, 'Crustacés, Gluten', 1, 0, 4),

        # ── Pâtes Fraîches ───────────────────────────────────────────────
        (2, 'Napoli',
         'Pâtes fraîches maison, sauce tomate San Marzano et basilic frais',
         16.00, 'Gluten, Œufs', 1, 0, 1),
        (2, 'Aglio e Olio',
         'Pâtes fraîches maison, ail, huile d\'olive extra vierge et persil',
         16.00, 'Gluten, Œufs', 1, 0, 2),
        (2, 'Al Ragù',
         'Pâtes fraîches maison, ragù de viande mijoté à l\'italienne',
         17.00, 'Gluten, Œufs', 1, 1, 3),
        (2, 'Quattro Formaggi',
         'Pâtes fraîches maison, crème aux quatre fromages italiens',
         18.50, 'Gluten, Œufs, Lactose', 1, 1, 4),
        (2, 'Pesto Pistache, Burrata & Mortadelle',
         'Pâtes fraîches maison, pesto pistache maison, burrata crémeuse et mortadelle',
         19.50, 'Gluten, Œufs, Lactose', 1, 1, 5),

        # ── Grillades ────────────────────────────────────────────────────
        (3, 'Arrosticini Traditionnels',
         'Brochettes d\'agneau grillées à la façon traditionnelle abruzzaise',
         2.20, '', 1, 1, 1),
        (3, 'Black Angus',
         'Pièce de Black Angus grillée à la perfection',
         3.00, '', 1, 0, 2),
        (3, 'Poulet Pané',
         'Filet de poulet pané croustillant grillé',
         2.20, 'Gluten', 1, 0, 3),
        (3, 'Calamar Pané',
         'Calamar pané croustillant grillé',
         2.20, 'Gluten, Mollusques', 1, 0, 4),
        (3, 'Brochette Agneau',
         'Brochette d\'agneau grillée',
         2.80, '', 1, 0, 5),
        (3, 'Brochette Bœuf',
         'Brochette de bœuf grillée',
         2.80, '', 1, 0, 6),
        (3, 'Brochette Poulet',
         'Brochette de poulet grillée',
         2.80, '', 1, 0, 7),
        (3, 'Pâtes Classiques (accompagnement)',
         'Pâtes classiques en accompagnement',
         12.00, 'Gluten', 1, 0, 8),
        (3, 'Pâtes Suggestions (accompagnement)',
         'Pâtes du moment en accompagnement',
         13.00, 'Gluten', 1, 0, 9),
        (3, 'Burrata (accompagnement)',
         'Burrata crémeuse en accompagnement',
         4.50, 'Lactose', 1, 0, 10),
        (3, 'Salade (accompagnement)',
         'Salade fraîche en accompagnement',
         5.50, '', 1, 0, 11),
        (3, 'Frites (accompagnement)',
         'Frites maison en accompagnement',
         4.50, '', 1, 0, 12),

        # ── Desserts ─────────────────────────────────────────────────────
        (4, 'Cannoli',
         'Cannoli siciliens au choix parmi 3 parfums',
         6.00, 'Gluten, Lactose', 1, 0, 1),
        (4, 'Tiramisu',
         'Tiramisu maison à la recette traditionnelle',
         8.00, 'Gluten, Lactose, Œufs', 1, 0, 2),
        (4, 'Dame Blanche',
         'Glace vanille, coulis de chocolat blanc chaud',
         8.00, 'Lactose', 1, 0, 3),
        (4, 'Dame Noire',
         'Glace vanille, coulis de chocolat noir chaud',
         8.00, 'Lactose', 1, 0, 4),
        (4, 'Sorbet',
         'Sorbet aux fruits de saison',
         4.50, '', 1, 0, 5),
        (4, 'Moelleux Chocolat',
         'Moelleux au chocolat avec cœur coulant, servi chaud',
         8.00, 'Gluten, Lactose, Œufs', 1, 0, 6),
        (4, 'Café Gourmand',
         'Café accompagné d\'une sélection de petites douceurs maison',
         12.00, 'Gluten, Lactose', 1, 0, 7),
        (4, 'Irish Gourmand',
         'Irish Coffee accompagné d\'une sélection de petites douceurs maison',
         15.00, 'Gluten, Lactose', 1, 0, 8),
        (4, 'Irish Coffee',
         'Whiskey, café chaud, crème fouettée',
         9.00, 'Lactose', 1, 0, 9),
        (4, 'Italian Coffee',
         'Café à l\'italienne avec touche de liqueur',
         9.00, 'Lactose', 1, 0, 10),

        # ── Boissons Chaudes ─────────────────────────────────────────────
        (5, 'Café',
         'Café expresso',
         3.00, '', 1, 0, 1),
        (5, 'Cappuccino',
         'Cappuccino onctueux à l\'italienne',
         3.50, 'Lactose', 1, 0, 2),
        (5, 'Expresso',
         'Expresso serré',
         3.00, '', 1, 0, 3),

        # ── Menu Enfants ─────────────────────────────────────────────────
        (6, 'Le Melone',
         'Menu enfant au melon',
         12.00, '', 1, 0, 1),
        (6, 'La Pasta Bolognata',
         'Pâtes à la sauce bolognaise pour enfants',
         12.00, 'Gluten, Œufs', 1, 0, 2),
        (6, 'La Pasta Prosciutto e Formaggio',
         'Pâtes au jambon et fromage pour enfants',
         12.00, 'Gluten, Œufs, Lactose', 1, 0, 3),

        # ── Apéritifs ────────────────────────────────────────────────────
        (7, 'Prosecco',      'Prosecco pétillant italien',        7.50, '', 1, 0, 1),
        (7, 'Porto',         'Porto rouge ou blanc',              6.00, '', 1, 0, 2),
        (7, 'Campari',       'Campari aperitivo',                 7.00, '', 1, 0, 3),
        (7, 'Cynar',         'Cynar, apéritif à l\'artichaut',   7.00, '', 1, 0, 4),
        (7, 'Pisang',        'Pisang Ambon, liqueur de banane',   7.00, '', 1, 0, 5),
        (7, 'Batida Coco',   'Batida de coco',                    7.00, '', 1, 0, 6),
        (7, 'Martini Blanc', 'Martini Bianco',                    7.00, '', 1, 0, 7),
        (7, 'Martini Rouge', 'Martini Rosso',                     7.00, '', 1, 0, 8),
        (7, 'Martini Bellini','Martini avec Prosecco et pêche',   8.00, '', 1, 0, 9),
        (7, 'Martini Rossini','Martini avec Prosecco et fraise',  8.00, '', 1, 0, 10),

        # ── Cocktails ────────────────────────────────────────────────────
        (8, 'Apéro Maison',              'Cocktail signature de la maison',         9.00, '', 1, 0, 1),
        (8, 'Apérol Spritz',             'Aperol, Prosecco, soda',                  9.00, '', 1, 0, 2),
        (8, 'Mojito',                    'Rhum blanc, menthe, citron vert, soda',   9.00, '', 1, 0, 3),
        (8, 'Mojito Sans Alcool',        'Menthe, citron vert, soda — sans alcool', 5.50, '', 1, 0, 4),
        (8, 'Apérol Spritz Sans Alcool', 'Apérol sans alcool, soda, orange',        5.50, '', 1, 0, 5),
        (8, 'Cocktail Sans Alcool',      'Cocktail fruité sans alcool',             5.50, '', 1, 0, 6),

        # ── Alcools ──────────────────────────────────────────────────────
        (9, 'William Lawson',   'Whisky',                   7.00, '', 1, 0, 1),
        (9, 'Jack Daniels',     'Whiskey américain',        7.50, '', 1, 0, 2),
        (9, 'Bacardi Blanc',    'Rhum blanc',               7.00, '', 1, 0, 3),
        (9, 'Bacardi Brun',     'Rhum ambré',               7.00, '', 1, 0, 4),
        (9, 'Eristoff Blanche', 'Vodka blanche',            7.00, '', 1, 0, 5),
        (9, 'Eristoff Rouge',   'Vodka rouge',              7.00, '', 1, 0, 6),
        (9, 'Bombay Sapphire',  'Gin premium',              7.00, '', 1, 0, 7),

        # ── Digestifs ────────────────────────────────────────────────────
        (10, 'Baileys',          'Crème de whisky irlandais', 7.50, 'Lactose', 1, 0, 1),
        (10, 'Averna',           'Amaro sicilien',            8.50, '', 1, 0, 2),
        (10, 'Amaro Del Capo',   'Amaro calabrais aux herbes', 8.50, '', 1, 0, 3),
        (10, 'Vecchia Romania',  'Brandy roumain',            6.00, '', 1, 0, 4),
        (10, 'Limoncello',       'Liqueur de citron sicilienne', 7.00, '', 1, 0, 5),
        (10, 'Grappa',           'Grappa traditionnelle',     7.00, '', 1, 0, 6),
        (10, 'Grappa Miel',      'Grappa au miel',            7.00, '', 1, 0, 7),
        (10, 'Amaretto',         'Liqueur d\'amande',         7.00, '', 1, 0, 8),
        (10, 'Sambucca',         'Liqueur d\'anis italienne', 7.00, '', 1, 0, 9),

        # ── Bières ───────────────────────────────────────────────────────
        (11, 'Jupiler 25 cl',      'Bière belge pression',  3.50, 'Gluten', 1, 0, 1),
        (11, 'Leffe Blonde 33 cl', 'Bière abbaye blonde',   5.00, 'Gluten', 1, 0, 2),
        (11, 'Moretti 33 cl',      'Bière italienne',       4.50, 'Gluten', 1, 0, 3),
        (11, 'Peroni 33 cl',       'Bière italienne premium',4.50,'Gluten', 1, 0, 4),

        # ── Softs ────────────────────────────────────────────────────────
        (12, 'Aqua Panna 25 cl',          'Eau plate italienne',             3.00, '', 1, 0, 1),
        (12, 'Aqua Panna 50 cl',          'Eau plate italienne',             4.50, '', 1, 0, 2),
        (12, 'San Pellegrino 25 cl',      'Eau gazeuse italienne',           3.50, '', 1, 0, 3),
        (12, 'San Pellegrino 50 cl',      'Eau gazeuse italienne',           4.50, '', 1, 0, 4),
        (12, 'Coca Cola',                 'Coca Cola',                       3.50, '', 1, 0, 5),
        (12, 'Coca Cola Zero',            'Coca Cola Zero sucre',            3.50, '', 1, 0, 6),
        (12, 'Looza Orange/Pomme Cerise', 'Jus de fruits Looza',             3.50, '', 1, 0, 7),
        (12, 'Sprite',                    'Limonade',                        3.50, '', 1, 0, 8),
        (12, 'Fanta',                     'Fanta orange',                    3.50, '', 1, 0, 9),
        (12, 'Ice Tea Pêche',             'Ice Tea saveur pêche',            3.50, '', 1, 0, 10),
        (12, 'Ice Tea Pétillant',         'Ice Tea pétillant',               3.50, '', 1, 0, 11),
        (12, 'Coca Cola 1L',             'Coca Cola grand format',           9.00, '', 1, 0, 12),
        (12, 'Coca Cola Zero 1L',        'Coca Cola Zero grand format',      9.00, '', 1, 0, 13),
        (12, 'San Pellegrino 1L',        'San Pellegrino grand format',      7.50, '', 1, 0, 14),
        (12, 'Aqua Panna 1L',            'Aqua Panna grand format',          7.50, '', 1, 0, 15),

        # ── Schweppes ────────────────────────────────────────────────────
        (13, 'Schweppes Mojito',  'Schweppes saveur mojito',  4.00, '', 1, 0, 1),
        (13, 'Schweppes Tonic',   'Schweppes tonic',          4.00, '', 1, 0, 2),
        (13, 'Schweppes Agrume',  'Schweppes agrumes',        4.00, '', 1, 0, 3),
    ]

    for (cat_id, name, desc, price, allergens, available, featured, sort_order) in items:
        cur.execute(
            '''INSERT INTO menu_items
               (category_id, name, description, price, allergens, available, featured, sort_order)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
            (cat_id, name, desc, price, allergens, available, featured, sort_order))

    cur.execute("SELECT setval(pg_get_serial_sequence('menu_items','id'), %s)",
                (len(items),))
    db.commit()

    flash(f'Menu réinitialisé avec succès — {len(items)} plats dans 13 catégories.', 'success')
    return redirect(url_for('admin_menu'))


# ── SEO ──────────────────────────────────────────────────────────────────────

@app.route('/google58e74cd6796edb1c.html')
def google_verify():
    return app.response_class(
        'google-site-verification: google58e74cd6796edb1c.html',
        mimetype='text/html')


@app.route('/robots.txt')
def robots_txt():
    content = f"""User-agent: *
Allow: /
Disallow: /admin/
Disallow: /admin

Sitemap: {SITE_URL}/sitemap.xml
"""
    return app.response_class(content, mimetype='text/plain')


@app.route('/sitemap.xml')
def sitemap_xml():
    from flask import make_response
    pages = [
        ('/',                   '1.0',  'daily'),
        ('/menu',               '0.9',  'weekly'),
        ('/galerie',            '0.8',  'monthly'),
        ('/evenements-prives',  '0.8',  'monthly'),
        ('/reservation',        '0.8',  'monthly'),
        ('/livraison',          '0.8',  'monthly'),
        ('/a-propos',           '0.7',  'monthly'),
        ('/faq',                '0.7',  'monthly'),
        ('/contact',            '0.7',  'monthly'),
    ]
    today = datetime.now().strftime('%Y-%m-%d')
    urls = '\n'.join(
        f"""  <url>
    <loc>{SITE_URL}{path}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{freq}</changefreq>
    <priority>{priority}</priority>
  </url>"""
        for path, priority, freq in pages
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""
    resp = make_response(xml)
    resp.headers['Content-Type'] = 'application/xml'
    return resp


# ── Error handlers ───────────────────────────────────────────────────────────

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 8080))
    app.run(debug=False, host='0.0.0.0', port=port)
else:
    init_db()
