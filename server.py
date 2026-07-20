#!/usr/bin/env python3
import cgi
import json
import os
import sqlite3
import sys
import uuid
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = ROOT_DIR / 'uploads'
DB_PATH = ROOT_DIR / 'data.db'
PORT = 8000


def init_db():
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON')
    conn.execute('''
        create table if not exists farms (
            id text primary key,
            name text not null
        )
    ''')
    conn.execute('''
        create table if not exists fields (
            id text primary key,
            farm_id text not null references farms(id) on delete cascade,
            name text not null
        )
    ''')
    conn.execute('''
        create table if not exists images (
            id text primary key,
            field_id text not null references fields(id) on delete cascade,
            name text not null,
            storage_path text not null,
            public_url text not null,
            uploaded_at text not null
        )
    ''')
    conn.commit()
    conn.close()


class BackendHandler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    def do_OPTIONS(self):
        self.send_response(204)
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            self.handle_api_get(parsed)
        else:
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/farms':
            self.handle_create_farm()
        elif parsed.path == '/api/fields':
            self.handle_create_field()
        elif parsed.path == '/api/images':
            self.handle_upload_image()
        else:
            self.send_error(404, 'Not found')

    def do_PATCH(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/fields/'):
            field_id = parsed.path.split('/')[-1]
            self.handle_rename_field(field_id)
        else:
            self.send_error(404, 'Not found')

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/fields/'):
            field_id = parsed.path.split('/')[-1]
            self.handle_delete_field(field_id)
        else:
            self.send_error(404, 'Not found')

    def handle_api_get(self, parsed):
        if parsed.path == '/api/farms':
            self.handle_list_farms()
        elif parsed.path.startswith('/api/farms/'):
            farm_id = parsed.path.split('/')[-1]
            self.handle_get_farm(farm_id)
        elif parsed.path == '/api/fields':
            self.handle_list_fields(parsed.query)
        elif parsed.path.startswith('/api/fields/'):
            field_id = parsed.path.split('/')[-1]
            self.handle_get_field(field_id)
        elif parsed.path == '/api/images':
            self.handle_list_images(parsed.query)
        else:
            self.send_error(404, 'Not found')

    def handle_list_farms(self):
        conn = self.connect_db()
        rows = conn.execute('select id, name from farms order by name').fetchall()
        conn.close()
        self.send_json([dict(row) for row in rows])

    def handle_get_farm(self, farm_id):
        conn = self.connect_db()
        row = conn.execute('select id, name from farms where id = ?', (farm_id,)).fetchone()
        conn.close()
        if not row:
            self.send_error(404, 'Farm not found')
            return
        self.send_json(dict(row))

    def handle_create_farm(self):
        data = self.read_json()
        name = data.get('name', '').strip()
        if not name:
            self.send_error(400, 'Farm name is required')
            return
        farm_id = str(uuid.uuid4())
        conn = self.connect_db()
        conn.execute('insert into farms (id, name) values (?, ?)', (farm_id, name))
        conn.commit()
        conn.close()
        self.send_json({'id': farm_id, 'name': name}, status=201)

    def handle_list_fields(self, query):
        params = parse_qs(query)
        farm_id = params.get('farmId', [None])[0]
        if not farm_id:
            self.send_error(400, 'farmId is required')
            return
        conn = self.connect_db()
        rows = conn.execute('select id, farm_id, name from fields where farm_id = ? order by name', (farm_id,)).fetchall()
        conn.close()
        self.send_json([dict(row) for row in rows])

    def handle_get_field(self, field_id):
        conn = self.connect_db()
        row = conn.execute('select id, farm_id, name from fields where id = ?', (field_id,)).fetchone()
        conn.close()
        if not row:
            self.send_error(404, 'Field not found')
            return
        self.send_json(dict(row))

    def handle_create_field(self):
        data = self.read_json()
        farm_id = data.get('farm_id', '').strip()
        name = data.get('name', '').strip()
        if not farm_id or not name:
            self.send_error(400, 'farm_id and name are required')
            return
        field_id = str(uuid.uuid4())
        conn = self.connect_db()
        conn.execute('insert into fields (id, farm_id, name) values (?, ?, ?)', (field_id, farm_id, name))
        conn.commit()
        conn.close()
        self.send_json({'id': field_id, 'farm_id': farm_id, 'name': name}, status=201)

    def handle_rename_field(self, field_id):
        data = self.read_json()
        name = data.get('name', '').strip()
        if not name:
            self.send_error(400, 'Field name is required')
            return
        conn = self.connect_db()
        cur = conn.execute('update fields set name = ? where id = ?', (name, field_id))
        conn.commit()
        if cur.rowcount == 0:
            conn.close()
            self.send_error(404, 'Field not found')
            return
        row = conn.execute('select id, farm_id, name from fields where id = ?', (field_id,)).fetchone()
        conn.close()
        self.send_json(dict(row))

    def handle_delete_field(self, field_id):
        conn = self.connect_db()
        row = conn.execute('select storage_path from images where field_id = ?', (field_id,)).fetchall()
        image_paths = [r['storage_path'] for r in row]
        conn.execute('delete from fields where id = ?', (field_id,))
        conn.commit()
        conn.close()
        for path in image_paths:
            file_path = ROOT_DIR / path.lstrip('/')
            if file_path.exists():
                try:
                    file_path.unlink()
                except OSError:
                    pass
        self.send_json({'success': True})

    def handle_list_images(self, query):
        params = parse_qs(query)
        field_id = params.get('fieldId', [None])[0]
        if not field_id:
            self.send_error(400, 'fieldId is required')
            return
        conn = self.connect_db()
        rows = conn.execute(
            'select id, field_id, name, storage_path, public_url, uploaded_at from images where field_id = ? order by uploaded_at desc',
            (field_id,)
        ).fetchall()
        conn.close()
        self.send_json([dict(row) for row in rows])

    def handle_upload_image(self):
        content_type = self.headers.get('Content-Type', '')
        if 'multipart/form-data' not in content_type:
            self.send_error(400, 'multipart/form-data required')
            return
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={
                'REQUEST_METHOD': 'POST',
                'CONTENT_TYPE': content_type,
            }
        )
        field_id = form.getvalue('field_id')
        file_item = form['file'] if 'file' in form else None
        if not field_id or not file_item or not getattr(file_item, 'filename', None):
            self.send_error(400, 'field_id and file are required')
            return
        filename = os.path.basename(file_item.filename)
        unique_name = f"{uuid.uuid4().hex}_{filename}"
        target_path = UPLOAD_DIR / unique_name
        with open(target_path, 'wb') as output_file:
            output_file.write(file_item.file.read())
        public_url = f'/uploads/{unique_name}'
        image_id = str(uuid.uuid4())
        uploaded_at = datetime.utcnow().isoformat() + 'Z'
        conn = self.connect_db()
        conn.execute(
            'insert into images (id, field_id, name, storage_path, public_url, uploaded_at) values (?, ?, ?, ?, ?, ?)',
            (image_id, field_id, filename, str(target_path.relative_to(ROOT_DIR)), public_url, uploaded_at)
        )
        conn.commit()
        conn.close()
        self.send_json({
            'id': image_id,
            'field_id': field_id,
            'name': filename,
            'storage_path': str(target_path.relative_to(ROOT_DIR)),
            'public_url': public_url,
            'uploaded_at': uploaded_at
        }, status=201)

    def read_json(self):
        length = int(self.headers.get('Content-Length', 0))
        if length == 0:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode('utf-8'))

    def send_json(self, payload, status=200):
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def connect_db(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        conn.execute('PRAGMA foreign_keys = ON')
        return conn


if __name__ == '__main__':
    init_db()
    os.chdir(str(ROOT_DIR))
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, BackendHandler)
    print(f'Serving on http://localhost:{PORT}')
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print('Stopping server')
        httpd.server_close()
