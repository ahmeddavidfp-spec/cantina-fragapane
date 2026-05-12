import os
import sqlite3
from datetime import datetime
from functools import wraps
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash, g)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cantina-fragapane-secret-2024')

ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'fragapane2024')
DATABASE = os.path.join(os.path.dirname(__file__), 'cantina.db')


# ── Database ──────────────────────────────────────────────────────────────────

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db:
        db.close()


def query(sql, args=(), one=False):
    cur = get_db().execute(sql, args)
    rv = cur.fetchall()
    return (rv[0] if rv else None) if one else rv


def execute(sql, args=()):
    db = get_db()
    db.execute(sql, args)
    db.commit()


# ── Init & Seed ───────────────────────────────────────────────────────────────

def init_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    db.executescript('''
        CREATE TABLE IF NOT EXISTS menu_categories (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT NOT NULL,
            icon       TEXT DEFAULT '🍽️',
            sort_order INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS menu_items (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            category_id INTEGER NOT NULL,
            name        TEXT NOT NULL,
            description TEXT,
            price       REAL,
            allergens   TEXT,
            available   INTEGER DEFAULT 1,
            featured    INTEGER DEFAULT 0,
            sort_order  INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS hours (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            day_name    TEXT NOT NULL,
            day_order   INTEGER NOT NULL,
            lunch_open  TEXT,
            lunch_close TEXT,
            dinner_open  TEXT,
            dinner_close TEXT,
            is_closed   INTEGER DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS info (
            key   TEXT PRIMARY KEY,
            value TEXT
        );
        CREATE TABLE IF NOT EXISTS announcements (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            message    TEXT NOT NULL,
            active     INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    ''')

    if db.execute('SELECT COUNT(*) FROM menu_categories').fetchone()[0] == 0:
        _seed(db)

    db.commit()
    db.close()


def _seed(db):
    cats = [
        ('Antipasti',        '🫒', 1),
        ('Pasta Fresca',     '🍝', 2),
        ('Carni & Grigliata','🥩', 3),
        ('Dolci',            '🍮', 4),
    ]
    for name, icon, order in cats:
        db.execute('INSERT INTO menu_categories (name, icon, sort_order) VALUES (?,?,?)',
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
        db.execute('''INSERT INTO menu_items
            (category_id,name,description,price,allergens,available,featured,sort_order)
            VALUES (?,?,?,?,?,?,?,?)''', it)

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
        db.execute('''INSERT INTO hours
            (day_name,day_order,lunch_open,lunch_close,dinner_open,dinner_close,is_closed)
            VALUES (?,?,?,?,?,?,?)''', h)

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
        db.execute('INSERT OR REPLACE INTO info (key,value) VALUES (?,?)', (key, val))


# ── Auth ──────────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return decorated


# ── Context processors ────────────────────────────────────────────────────────

@app.context_processor
def inject_globals():
    info = {r['key']: r['value']
            for r in query('SELECT key, value FROM info')}
    announcements = query(
        'SELECT * FROM announcements WHERE active=1 ORDER BY created_at DESC')
    return dict(info=info, announcements=announcements, now=datetime.now())


# ── Helpers ───────────────────────────────────────────────────────────────────

def get_hours():
    return query('SELECT * FROM hours ORDER BY day_order')


def get_full_menu():
    cats = query('SELECT * FROM menu_categories ORDER BY sort_order')
    result = []
    for cat in cats:
        items = query(
            'SELECT * FROM menu_items WHERE category_id=? AND available=1 ORDER BY sort_order',
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


@app.route('/contact')
def contact():
    hours = get_hours()
    return render_template('contact.html', hours=hours)


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
        'categories': query('SELECT COUNT(*) AS c FROM menu_categories', one=True)['c'],
        'plats':      query('SELECT COUNT(*) AS c FROM menu_items WHERE available=1', one=True)['c'],
        'annonces':   query('SELECT COUNT(*) AS c FROM announcements WHERE active=1', one=True)['c'],
    }
    return render_template('admin/dashboard.html', stats=stats)


# ── Admin – menu ──────────────────────────────────────────────────────────────

@app.route('/admin/menu')
@login_required
def admin_menu():
    cats = query('SELECT * FROM menu_categories ORDER BY sort_order')
    items_by_cat = {
        cat['id']: query(
            'SELECT * FROM menu_items WHERE category_id=? ORDER BY sort_order',
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
        execute('INSERT INTO menu_categories (name,icon,sort_order) VALUES (?,?,?)',
                (name, icon, max_o + 1))
        flash(f'Catégorie « {name} » ajoutée.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/categorie/<int:cat_id>/modifier', methods=['POST'])
@login_required
def admin_edit_category(cat_id):
    name = request.form.get('name', '').strip()
    icon = request.form.get('icon', '').strip() or '🍽️'
    if name:
        execute('UPDATE menu_categories SET name=?, icon=? WHERE id=?', (name, icon, cat_id))
        flash('Catégorie mise à jour.', 'success')
    return redirect(url_for('admin_menu'))


@app.route('/admin/menu/categorie/<int:cat_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_category(cat_id):
    execute('DELETE FROM menu_items WHERE category_id=?', (cat_id,))
    execute('DELETE FROM menu_categories WHERE id=?', (cat_id,))
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
        max_o = (query('SELECT MAX(sort_order) AS m FROM menu_items WHERE category_id=?',
                       (cat_id,), one=True)['m'] or 0)
        execute('''INSERT INTO menu_items
            (category_id,name,description,price,allergens,available,featured,sort_order)
            VALUES (?,?,?,?,?,?,?,?)''',
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
               SET name=?, description=?, price=?, allergens=?, available=?, featured=?
               WHERE id=?''',
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
    execute('DELETE FROM menu_items WHERE id=?', (item_id,))
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

    for h in all_hours:
        hid = h['id']
        is_closed = 1 if request.form.get(f'h_{hid}_is_closed') else 0
        execute('UPDATE hours SET is_closed=? WHERE id=?', (is_closed, hid))

        for field in ('lunch_open', 'lunch_close', 'dinner_open', 'dinner_close'):
            val = request.form.get(f'h_{hid}_{field}', '').strip() or None
            execute(f'UPDATE hours SET {field}=? WHERE id=?', (val, hid))

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
               'reservation_note','price_range','google_maps_embed']
    for key in allowed:
        val = request.form.get(key, '').strip()
        execute('INSERT OR REPLACE INTO info (key,value) VALUES (?,?)', (key, val))
    flash('Informations mises à jour.', 'success')
    return redirect(url_for('admin_info'))


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
        execute('INSERT INTO announcements (message, active) VALUES (?,1)', (msg,))
        flash('Annonce ajoutée.', 'success')
    return redirect(url_for('admin_announcements'))


@app.route('/admin/annonces/<int:ann_id>/toggle', methods=['POST'])
@login_required
def admin_toggle_announcement(ann_id):
    ann = query('SELECT active FROM announcements WHERE id=?', (ann_id,), one=True)
    if ann:
        execute('UPDATE announcements SET active=? WHERE id=?',
                (0 if ann['active'] else 1, ann_id))
    return redirect(url_for('admin_announcements'))


@app.route('/admin/annonces/<int:ann_id>/supprimer', methods=['POST'])
@login_required
def admin_delete_announcement(ann_id):
    execute('DELETE FROM announcements WHERE id=?', (ann_id,))
    flash('Annonce supprimée.', 'success')
    return redirect(url_for('admin_announcements'))


# ── Startup ───────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
else:
    init_db()
