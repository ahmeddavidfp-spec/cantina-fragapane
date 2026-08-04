# La Cantina Fragapane — Site web

Site du restaurant italien La Cantina Fragapane (Châtelet, Belgique).
Application **Flask** avec back-office d'administration, réservations, menu dynamique,
événements, annonces et newsletter. Base de données **PostgreSQL**.

## Stack
- Python 3.12 / Flask + Gunicorn
- PostgreSQL (via `psycopg2`)
- Front : HTML/CSS/JS (templates Jinja2, pas de framework JS)

## Configuration (variables d'environnement)
| Variable | Rôle | Obligatoire |
|----------|------|-------------|
| `DATABASE_URL` | Connexion Postgres (`postgresql://...?sslmode=require`) | ✅ |
| `SECRET_KEY` | Clé de session Flask (chaîne aléatoire) | ✅ |
| `ADMIN_PASSWORD` | Mot de passe du back-office `/admin` | ✅ |
| `SITE_URL` | URL publique (canonical, SEO) | recommandé |
| `MAIL_USERNAME` / `MAIL_PASSWORD` / `MAIL_TO` | Emails de réservation (SMTP Office365) | optionnel |

> La base s'initialise **automatiquement** au premier démarrage (`init_db()` crée
> les tables et insère les données de départ). Aucune migration manuelle.

## Déploiement — Neon + Render + Cloudflare (gratuit)

### 1. Base de données — Neon
1. Crée un projet sur https://neon.tech (gratuit, persistant).
2. Copie la **connection string** (format `postgresql://...?sslmode=require`).

### 2. App — Render
1. https://render.com → **New › Web Service** → connecte ce dépôt GitHub.
2. Build : `pip install -r requirements.txt` — Start : `gunicorn app:app` (déjà dans le `Procfile`).
   *(ou "New › Blueprint" pour utiliser `render.yaml` directement)*
3. Onglet **Environment** → ajoute :
   - `DATABASE_URL` = la connection string Neon
   - `SECRET_KEY` = une chaîne aléatoire longue
   - `ADMIN_PASSWORD` = un mot de passe fort
   - `SITE_URL` = `https://www.cantinafragapane.be`
4. Deploy. Render fournit une URL `https://cantina-fragapane.onrender.com`.

### 3. Domaine — Cloudflare + LWS
1. Cloudflare → ajoute le site `cantinafragapane.be` → note les 2 nameservers.
2. LWS → remplace les nameservers du domaine par ceux de Cloudflare.
3. Render → **Settings › Custom Domains** → ajoute `www.cantinafragapane.be` (et l'apex).
4. Cloudflare DNS → `CNAME www → cantina-fragapane.onrender.com` (Proxied),
   + redirection apex `cantinafragapane.be → www`.

> ⚠️ Plan gratuit Render : l'app se met en veille après ~15 min d'inactivité
> (premier chargement ~30-50 s). Neon reste persistant.

## Développement local
```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # puis renseigne DATABASE_URL (une base Postgres locale ou Neon)
python app.py          # http://localhost:8080
```
