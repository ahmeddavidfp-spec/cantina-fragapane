import os
import uuid
import smtplib
import psycopg2
import psycopg2.extras
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps
from werkzeug.utils import secure_filename
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
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'fragapane2024')

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
        ('email',             'brenda4859@outlook.be'),
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

def send_contact_email(name, sender_email, phone, message):
    server   = os.environ.get('MAIL_SERVER', 'smtp.office365.com')
    port     = int(os.environ.get('MAIL_PORT', '587'))
    username = os.environ.get('MAIL_USERNAME', '')
    password = os.environ.get('MAIL_PASSWORD', '')
    to_addr  = os.environ.get('MAIL_TO', username)

    if not username or not password:
        return False

    msg = MIMEMultipart()
    msg['From']    = username
    msg['To']      = to_addr
    msg['Subject'] = f'[Cantina Fragapane] Message de {name}'
    body = (f"Nom : {name}\nEmail : {sender_email}\nTéléphone : {phone}\n\n"
            f"Message :\n{message}")
    msg.attach(MIMEText(body, 'plain', 'utf-8'))

    with smtplib.SMTP(server, port) as srv:
        srv.starttls()
        srv.login(username, password)
        srv.send_message(msg)
    return True


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
    return dict(info=info, announcements=announcements, evenements=evenements,
                open_status=open_status, now=datetime.now())


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

@app.route('/')
def index():
    hours = get_hours()
    featured = query('''
        SELECT m.*, c.name AS cat_name
        FROM menu_items m
        JOIN menu_categories c ON m.category_id = c.id
        WHERE m.featured=1 AND m.available=1
        ORDER BY m.sort_order
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
    return render_template('menu.html', menu_data=menu_data)


@app.route('/a-propos')
def a_propos():
    return render_template('a_propos.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact():
    hours = get_hours()
    if request.method == 'POST':
        name    = request.form.get('name', '').strip()
        email   = request.form.get('email', '').strip()
        phone   = request.form.get('phone', '').strip()
        message = request.form.get('message', '').strip()
        if name and message:
            try:
                sent = send_contact_email(name, email, phone, message)
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
        name   = request.form.get('name', '').strip()
        phone  = request.form.get('phone', '').strip()
        date   = request.form.get('date', '').strip()
        time   = request.form.get('time', '').strip()
        guests = request.form.get('guests', '').strip()
        notes  = request.form.get('notes', '').strip()
        if name and phone and date and time and guests:
            execute(
                'INSERT INTO reservations (name,phone,date,time,guests,notes) VALUES (%s,%s,%s,%s,%s,%s)',
                (name, phone, date, time, int(guests), notes or None))
            try:
                body = (f"Nouvelle demande de réservation :\n\n"
                        f"Nom : {name}\nTéléphone : {phone}\n"
                        f"Date : {date} à {time}\nPersonnes : {guests}\n"
                        f"Notes : {notes or '—'}")
                send_contact_email(name, '', phone,
                                   f"[RÉSERVATION] {date} {time} – {guests} pers.\n\n{body}")
            except Exception:
                pass
            flash('Demande reçue ! Nous vous confirmons par téléphone dans les 2h.', 'success')
        else:
            flash('Veuillez remplir tous les champs obligatoires.', 'error')
        return redirect(url_for('reservation'))
    return render_template('reservation.html')


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


@app.route('/sitemap.xml')
def sitemap():
    from flask import Response
    pages = [
        ('/', '1.0', 'weekly'),
        ('/menu', '0.9', 'weekly'),
        ('/livraison', '0.9', 'monthly'),
        ('/a-propos', '0.8', 'monthly'),
        ('/contact', '0.8', 'monthly'),
    ]
    base = 'https://web-production-e3877.up.railway.app'
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for path, priority, freq in pages:
        xml.append(f'  <url><loc>{base}{path}</loc>'
                   f'<changefreq>{freq}</changefreq>'
                   f'<priority>{priority}</priority></url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    from flask import Response
    txt = ('User-agent: *\n'
           'Allow: /\n'
           'Disallow: /admin\n'
           'Sitemap: https://web-production-e3877.up.railway.app/sitemap.xml\n')
    return Response(txt, mimetype='text/plain')


# ── Admin – auth ──────────────────────────────────────────────────────────────

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if session.get('admin'):
        return redirect(url_for('admin_dashboard'))
    error = None
    if request.method == 'POST':
        if request.form.get('password') == ADMIN_PASSWORD:
            session['admin'] = True
            flash("Bienvenue dans l'espace admin !", 'success')
            return redirect(url_for('admin_dashboard'))
        error = 'Mot de passe incorrect.'
    return render_template('admin/login.html', error=error)


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
    icon = request.form.get('icon', '🍽️').strip() or '🍽️'
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
    icon = request.form.get('icon', '').strip() or '🍽️'
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
