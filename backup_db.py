#!/usr/bin/env python3
"""Sauvegarde de la base Cantina Fragapane → fichier JSON horodaté.
Usage :  DATABASE_URL='postgresql://...neon.tech/neondb?sslmode=require' python3 backup_db.py
Utilisé automatiquement chaque semaine par .github/workflows/backup.yml
"""
import os, sys, json
from datetime import datetime, timezone
import psycopg2, psycopg2.extras

DB = os.environ.get('DATABASE_URL')
if not DB:
    sys.exit("❌ DATABASE_URL manquant.")

TABLES = ['menu_categories', 'menu_items', 'hours', 'info', 'announcements',
          'evenements', 'reservations', 'newsletter_subscribers', 'messages']

conn = psycopg2.connect(DB, cursor_factory=psycopg2.extras.RealDictCursor)
cur = conn.cursor()
dump = {}
for t in TABLES:
    try:
        cur.execute(f'SELECT * FROM "{t}"')
        dump[t] = cur.fetchall()
    except Exception as e:
        dump[t] = {'_error': str(e)}
conn.close()

stamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
fname = f'backup-cantina-{stamp}.json'
with open(fname, 'w', encoding='utf-8') as f:
    json.dump(dump, f, ensure_ascii=False, indent=2, default=str)

print(f"✅ Sauvegarde écrite : {fname}")
for t in TABLES:
    n = len(dump[t]) if isinstance(dump[t], list) else '?'
    print(f"  {t:24} {n} lignes")
