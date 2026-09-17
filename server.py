#!/usr/bin/env python3
"""
Club Robotique ENIM - Install Party
Serveur local (aucune installation requise, Python standard uniquement).

Utilisation:
    python3 server.py

Puis ouvrir dans le navigateur:
    http://localhost:8000            (sur ce PC)
    http://<IP_DE_CE_PC>:8000        (sur les autres appareils, meme WiFi)

Toutes les donnees sont stockees dans members.json, dans ce meme dossier.
"""
import json
import os
import random
import re
import socket
import sqlite3
import threading
import time
import base64
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.environ.get('DB_PATH') or os.path.join(BASE_DIR, 'members.db')
LOCK = threading.Lock()
EMAIL_RE = re.compile(r'^[^\s@]+@[^\s@]+\.[^\s@]+$')
PORT = int(os.environ.get('PORT', 8000))
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'rayenrayen123')

# --- Sauvegarde optionnelle vers GitHub (via l'API GitHub, aucune dependance) ---
# A configurer via variables d'environnement (jamais dans le code) :
#   GITHUB_TOKEN            token d'acces personnel avec droit "contents: write"
#   GITHUB_REPO             "monpseudo/mon-depot"
#   GITHUB_BRANCH           branche cible (defaut: main)
#   GITHUB_BACKUP_PATH      chemin du fichier dans le depot (defaut: backups/members.json)
#   BACKUP_INTERVAL_MINUTES sauvegarde automatique toutes les N minutes (0 = desactive)
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
GITHUB_REPO = os.environ.get('GITHUB_REPO')
GITHUB_BRANCH = os.environ.get('GITHUB_BRANCH', 'main')
GITHUB_BACKUP_PATH = os.environ.get('GITHUB_BACKUP_PATH', 'backups/members.json')
BACKUP_INTERVAL_MINUTES = int(os.environ.get('BACKUP_INTERVAL_MINUTES', '0'))


def get_conn():
    conn = sqlite3.connect(DB_FILE, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute('''CREATE TABLE IF NOT EXISTS members(
        code TEXT PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        phone TEXT,
        email TEXT,
        study TEXT,
        pc TEXT,
        electrique_done INTEGER DEFAULT 0,
        electrique_at INTEGER,
        mecanique_done INTEGER DEFAULT 0,
        mecanique_at INTEGER,
        created_at INTEGER
    )''')
    conn.commit()
    conn.close()


def row_to_member(row):
    return {
        'code': row['code'],
        'firstName': row['first_name'],
        'lastName': row['last_name'],
        'phone': row['phone'],
        'email': row['email'],
        'study': row['study'],
        'pc': row['pc'],
        'electrique': {'done': bool(row['electrique_done']), 'doneAt': row['electrique_at']},
        'mecanique': {'done': bool(row['mecanique_done']), 'doneAt': row['mecanique_at']},
        'createdAt': row['created_at'],
    }


def get_all_members():
    conn = get_conn()
    rows = conn.execute('SELECT * FROM members ORDER BY created_at DESC').fetchall()
    conn.close()
    return [row_to_member(r) for r in rows]


def get_member(code):
    conn = get_conn()
    row = conn.execute('SELECT * FROM members WHERE code=?', (code,)).fetchone()
    conn.close()
    return row_to_member(row) if row else None


def code_exists(code):
    conn = get_conn()
    row = conn.execute('SELECT 1 FROM members WHERE code=?', (code,)).fetchone()
    conn.close()
    return row is not None


def gen_code():
    for _ in range(30):
        code = 'ENIM-%04d' % random.randint(1000, 9999)
        if not code_exists(code):
            return code
    return 'ENIM-%06d' % random.randint(100000, 999999)


def insert_member(member):
    conn = get_conn()
    conn.execute(
        '''INSERT INTO members(code,first_name,last_name,phone,email,study,pc,
           electrique_done,electrique_at,mecanique_done,mecanique_at,created_at)
           VALUES(?,?,?,?,?,?,?,0,NULL,0,NULL,?)''',
        (member['code'], member['firstName'], member['lastName'], member['phone'],
         member['email'], member['study'], member['pc'], member['createdAt']),
    )
    conn.commit()
    conn.close()


def update_checkpoint(code, team):
    col_done = 'electrique_done' if team == 'electrique' else 'mecanique_done'
    col_at = 'electrique_at' if team == 'electrique' else 'mecanique_at'
    conn = get_conn()
    conn.execute(f'UPDATE members SET {col_done}=1, {col_at}=? WHERE code=?', (int(time.time() * 1000), code))
    conn.commit()
    conn.close()


def admin_update_member(code, fields):
    """fields: dict with any of firstName,lastName,phone,email,study,pc,
    electrique (bool), mecanique (bool)."""
    sets = []
    values = []
    col_map = {
        'firstName': 'first_name', 'lastName': 'last_name', 'phone': 'phone',
        'email': 'email', 'study': 'study', 'pc': 'pc',
    }
    for key, col in col_map.items():
        if key in fields:
            sets.append(f'{col}=?')
            values.append(fields[key])

    now = int(time.time() * 1000)
    if 'electrique' in fields:
        sets.append('electrique_done=?')
        values.append(1 if fields['electrique'] else 0)
        sets.append('electrique_at=?')
        values.append(now if fields['electrique'] else None)
    if 'mecanique' in fields:
        sets.append('mecanique_done=?')
        values.append(1 if fields['mecanique'] else 0)
        sets.append('mecanique_at=?')
        values.append(now if fields['mecanique'] else None)

    if not sets:
        return
    values.append(code)
    conn = get_conn()
    conn.execute(f'UPDATE members SET {", ".join(sets)} WHERE code=?', values)
    conn.commit()
    conn.close()


def admin_delete_member(code):
    conn = get_conn()
    conn.execute('DELETE FROM members WHERE code=?', (code,))
    conn.commit()
    conn.close()


def github_backup():
    """Envoie un instantane JSON de tous les membres vers un fichier dans un
    depot GitHub, via l'API Contents (creation ou mise a jour du fichier)."""
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False, "Sauvegarde GitHub non configuree (GITHUB_TOKEN / GITHUB_REPO manquants)."

    try:
        with LOCK:
            members = get_all_members()
        content_bytes = json.dumps(members, ensure_ascii=False, indent=2).encode('utf-8')
        content_b64 = base64.b64encode(content_bytes).decode('ascii')

        api_url = f'https://api.github.com/repos/{GITHUB_REPO}/contents/{GITHUB_BACKUP_PATH}'
        headers = {
            'Authorization': f'token {GITHUB_TOKEN}',
            'Accept': 'application/vnd.github+json',
            'User-Agent': 'club-robotique-enim-backup',
        }

        # Recuperer le sha du fichier existant (necessaire pour le mettre a jour)
        sha = None
        get_req = urllib.request.Request(f'{api_url}?ref={GITHUB_BRANCH}', headers=headers)
        try:
            with urllib.request.urlopen(get_req, timeout=15) as resp:
                sha = json.loads(resp.read().decode('utf-8')).get('sha')
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

        body = {
            'message': f'Backup membres ({time.strftime("%Y-%m-%d %H:%M:%S")}) - {len(members)} membre(s)',
            'content': content_b64,
            'branch': GITHUB_BRANCH,
        }
        if sha:
            body['sha'] = sha

        put_req = urllib.request.Request(
            api_url,
            data=json.dumps(body).encode('utf-8'),
            headers={**headers, 'Content-Type': 'application/json'},
            method='PUT',
        )
        with urllib.request.urlopen(put_req, timeout=15) as resp:
            resp.read()

        return True, f'Sauvegarde envoyee sur GitHub : {GITHUB_REPO}/{GITHUB_BACKUP_PATH} ({len(members)} membre(s)).'
    except urllib.error.HTTPError as e:
        detail = e.read().decode('utf-8', 'ignore') if hasattr(e, 'read') else ''
        return False, f'Erreur GitHub ({e.code}): {detail[:200]}'
    except Exception as e:
        return False, f'Erreur de sauvegarde GitHub : {e}'


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # keep the console clean during the event

    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get('Content-Length', 0) or 0)
        raw = self.rfile.read(length) if length else b'{}'
        try:
            return json.loads(raw.decode('utf-8'))
        except Exception:
            return {}

    def _serve_file(self, filename, content_type):
        path = os.path.join(BASE_DIR, filename)
        try:
            with open(path, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET,POST,OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path

        if path in ('/', '/index.html'):
            self._serve_file('index.html', 'text/html; charset=utf-8')
            return

        if path == '/api/members':
            with LOCK:
                members = get_all_members()
            self._send_json(members)
            return

        m = re.match(r'^/api/members/([A-Za-z0-9\-]+)$', path)
        if m:
            code = m.group(1).upper()
            with LOCK:
                member = get_member(code)
            if member:
                self._send_json(member)
            else:
                self._send_json({'error': 'not_found'}, 404)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        path = urlparse(self.path).path

        if path == '/api/checkin':
            payload = self._read_json()
            fn = (payload.get('firstName') or '').strip()
            ln = (payload.get('lastName') or '').strip()
            phone = (payload.get('phone') or '').strip()
            email = (payload.get('email') or '').strip()
            study = (payload.get('study') or '').strip()
            pc = (payload.get('pc') or '').strip()

            if not fn or not ln:
                self._send_json({'error': "Prénom et nom sont obligatoires."}, 400)
                return
            if not study:
                self._send_json({'error': "La filière d'étude est obligatoire."}, 400)
                return
            if not pc:
                self._send_json({'error': "Le PC est obligatoire."}, 400)
                return

            clean_phone = re.sub(r'\s+', '', phone)
            clean_phone = re.sub(r'^(\+216|216)', '', clean_phone)
            if not re.match(r'^\d{8}$', clean_phone):
                self._send_json(
                    {'error': "Le numéro de téléphone doit contenir exactement 8 chiffres (sans +216)."}, 400
                )
                return

            if not email or not EMAIL_RE.match(email):
                self._send_json({'error': "Veuillez entrer une adresse email valide."}, 400)
                return

            with LOCK:
                code = gen_code()
                member = {
                    'code': code,
                    'firstName': fn,
                    'lastName': ln,
                    'phone': clean_phone,
                    'email': email,
                    'study': study,
                    'pc': pc,
                    'electrique': {'done': False, 'doneAt': None},
                    'mecanique': {'done': False, 'doneAt': None},
                    'createdAt': int(time.time() * 1000),
                }
                insert_member(member)
            self._send_json(member)
            return

        if path == '/api/admin/verify':
            payload = self._read_json()
            if payload.get('password') != ADMIN_PASSWORD:
                self._send_json({'error': 'Mot de passe incorrect.'}, 401)
                return
            self._send_json({'ok': True})
            return

        if path == '/api/admin/update':
            payload = self._read_json()
            if payload.get('password') != ADMIN_PASSWORD:
                self._send_json({'error': 'Mot de passe incorrect.'}, 401)
                return
            code = (payload.get('code') or '').strip().upper()
            if not code:
                self._send_json({'error': 'Code manquant.'}, 400)
                return

            fields = {}
            for key in ('firstName', 'lastName', 'study', 'pc'):
                if key in payload:
                    val = (payload.get(key) or '').strip()
                    if not val:
                        self._send_json({'error': 'Tous les champs texte sont obligatoires.'}, 400)
                        return
                    fields[key] = val

            if 'phone' in payload:
                clean_phone = re.sub(r'\s+', '', payload.get('phone') or '')
                clean_phone = re.sub(r'^(\+216|216)', '', clean_phone)
                if not re.match(r'^\d{8}$', clean_phone):
                    self._send_json(
                        {'error': "Le numéro de téléphone doit contenir exactement 8 chiffres (sans +216)."}, 400
                    )
                    return
                fields['phone'] = clean_phone

            if 'email' in payload:
                email = (payload.get('email') or '').strip()
                if not email or not EMAIL_RE.match(email):
                    self._send_json({'error': "Veuillez entrer une adresse email valide."}, 400)
                    return
                fields['email'] = email

            if 'electrique' in payload:
                fields['electrique'] = bool(payload.get('electrique'))
            if 'mecanique' in payload:
                fields['mecanique'] = bool(payload.get('mecanique'))

            with LOCK:
                member = get_member(code)
                if not member:
                    self._send_json({'error': 'Code introuvable.'}, 404)
                    return
                admin_update_member(code, fields)
                member = get_member(code)
            self._send_json(member)
            return

        if path == '/api/admin/delete':
            payload = self._read_json()
            if payload.get('password') != ADMIN_PASSWORD:
                self._send_json({'error': 'Mot de passe incorrect.'}, 401)
                return
            code = (payload.get('code') or '').strip().upper()
            with LOCK:
                member = get_member(code)
                if not member:
                    self._send_json({'error': 'Code introuvable.'}, 404)
                    return
                admin_delete_member(code)
            self._send_json({'ok': True})
            return

        if path == '/api/admin/backup-github':
            payload = self._read_json()
            if payload.get('password') != ADMIN_PASSWORD:
                self._send_json({'error': 'Mot de passe incorrect.'}, 401)
                return
            ok, message = github_backup()
            self._send_json({'ok': ok, 'message': message}, 200 if ok else 400)
            return

        if path == '/api/checkpoint':
            payload = self._read_json()
            code = (payload.get('code') or '').strip().upper()
            team = payload.get('team')
            if team not in ('electrique', 'mecanique'):
                self._send_json({'error': 'invalid_team'}, 400)
                return
            with LOCK:
                member = get_member(code)
                if not member:
                    self._send_json({'error': 'Code introuvable.'}, 404)
                    return
                update_checkpoint(code, team)
                member = get_member(code)
            self._send_json(member)
            return

        self.send_response(404)
        self.end_headers()


def get_lan_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = '127.0.0.1'
    finally:
        s.close()
    return ip


def backup_loop():
    while True:
        time.sleep(BACKUP_INTERVAL_MINUTES * 60)
        ok, message = github_backup()
        print(('[backup GitHub OK] ' if ok else '[backup GitHub ERREUR] ') + message)


if __name__ == '__main__':
    init_db()
    if BACKUP_INTERVAL_MINUTES > 0 and GITHUB_TOKEN and GITHUB_REPO:
        threading.Thread(target=backup_loop, daemon=True).start()
        print(f'  Sauvegarde automatique GitHub activee toutes les {BACKUP_INTERVAL_MINUTES} min')
    server = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    ip = get_lan_ip()
    print('=' * 56)
    print('  Club Robotique ENIM - Install Party (serveur local)')
    print('=' * 56)
    print(f'  Sur ce PC          : http://localhost:{PORT}')
    print(f'  Sur le reseau WiFi : http://{ip}:{PORT}')
    print('  (les autres appareils doivent etre sur le meme WiFi,')
    print('   sinon voir README.txt pour un acces via internet)')
    print('  Base de donnees : members.db (SQLite)')
    print('  Ctrl+C pour arreter le serveur')
    print('=' * 56)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nServeur arrete.')
