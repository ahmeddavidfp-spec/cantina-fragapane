"""Tests minimaux pour /robots.txt et /llms.txt.

Lancer :  CF_SKIP_STARTUP=1 pytest -q
(la variable évite d'ouvrir une connexion base de données à l'import de l'app.)
"""
import os

os.environ.setdefault('CF_SKIP_STARTUP', '1')  # pas de init_db() ni de webhook au chargement

import pytest

from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as c:
        yield c


def test_robots_txt(client):
    r = client.get('/robots.txt')
    assert r.status_code == 200
    assert r.mimetype == 'text/plain'
    body = r.get_data(as_text=True)
    assert 'User-agent: *' in body
    assert 'Allow: /' in body
    assert 'Disallow: /admin' in body          # l'admin reste interdit
    assert 'Sitemap:' in body                  # la ligne Sitemap est présente
    assert '/sitemap.xml' in body


def test_llms_txt(client):
    r = client.get('/llms.txt')
    assert r.status_code == 200
    assert r.mimetype == 'text/plain'
    body = r.get_data(as_text=True)
    assert '# La Cantina Fragapane' in body     # titre
    assert 'Châtelet' in body                    # restaurant italien à Châtelet
    assert '/menu' in body and '/reservation' in body and '/evenements-prives' in body
    assert 'Scribeo' in body                     # créateur crédité
    assert '—' not in body and '–' not in body   # aucun tiret long
