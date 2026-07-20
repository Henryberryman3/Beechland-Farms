from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import cgi
import json
import os
import sqlite3
import uuid
from urllib.parse import urlparse, parse_qs

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'beechland.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

os.makedirs(UPLOAD_DIR, exist_ok=True)

CREATE_FARMS = '''
CREATE TABLE IF NOT EXISTS farms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
);
'''

CREATE_FIELDS = '''
CREATE TABLE IF NOT EXISTS fields (
    id TEXT PRIMARY KEY,
    farm_id TEXT NOT NULL,
    name TEXT NOT NULL,
    FOREIGN KEY(farm_id) REFERENCES farms(id) ON DELETE CASCADE
);
'''

CREATE_IMAGES = '''
CREATE TABLE IF NOT EXISTS images (
    id TEXT PRIMARY KEY,
    field_id TEXT NOT NULL,
    filename TEXT NOT NULL,
    original_name TEXT NOT NULL,
    mime_type TEXT NOT NULL,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY(field_id) REFERENCES fields(id) ON DELETE CASCADE
);
'''

ALLOWED_IMAGE_MIME_TYPES = {
    'image/jpeg',
    'image/png',
    'image/gif',
    'image/webp',
    'image/svg+xml',
}


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.executescript(CREATE_FARMS + CREATE_FIELDS + CREATE_IMAGES)
    conn.commit()
    conn.close()


def json_response(handler, data, status=HTTPStatus.OK):
    response = json.dumps(data, ensure_ascii=False).encode('utf-8')
    handler.send_response(status)
    handler.send_header('Content-Type', 'application/json; charset=utf-8')
    handler.send_header('Content-Length', str(len(response)))
    handler.send_header('Access-Control-Allow-Origin', '*')
    handler.end_headers()
    handler.wfile.write(response)


def parse_body(handler):
    length = int(handler.headers.get('Content-Length', 0))
    body = handler.rfile.read(length)
    if not body:
        return {}
    return json.loads(body.decode('utf-8'))


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.execute('PRAGMA foreign_keys = ON;')
    conn.row_factory = sqlite3.Row
    return conn


def delete_image_files_by_field_ids(field_ids):
    if not field_ids:
        return
    conn = get_db_connection()
    rows = conn.execute(
        f"SELECT filename FROM images WHERE field_id IN ({','.join(['?'] * len(field_ids))})",
        field_ids
    ).fetchall()
    conn.execute(
        f"DELETE FROM images WHERE field_id IN ({','.join(['?'] * len(field_ids))})",
        field_ids
    )
    conn.commit()
    conn.close()
    for row in rows:
        file_path = os.path.join(UPLOAD_DIR, row['filename'])
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass


def delete_image_files_for_farm(farm_id):
    conn = get_db_connection()
    rows = conn.execute(
        'SELECT filename FROM images WHERE field_id IN (SELECT id FROM fields WHERE farm_id = ?)',
        (farm_id,)
    ).fetchall()
    conn.close()
    for row in rows:
        file_path = os.path.join(UPLOAD_DIR, row['filename'])
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except OSError:
            pass


class BeechlandHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api_get(parsed)
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api_post(parsed)
        return super().do_POST()

    def do_PUT(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api_put(parsed)
        return super().do_PUT()

    def do_DELETE(self):
        parsed = urlparse(self.path)
        if parsed.path.startswith('/api/'):
            return self.handle_api_delete(parsed)
        return super().do_DELETE()

    def handle_api_get(self, parsed):
        if parsed.path == '/api/farms':
            return self.api_get_farms()
        if parsed.path == '/api/fields':
            return self.api_get_fields(parsed.query)
        if parsed.path == '/api/images':
            return self.api_get_images(parsed.query)
        if parsed.path == '/api/farm':
            return self.api_get_farm(parsed.query)
        if parsed.path == '/api/field':
            return self.api_get_field(parsed.query)
        self.send_error(HTTPStatus.NOT_FOUND, 'API endpoint not found')

    def handle_api_post(self, parsed):
        if parsed.path == '/api/farms':
            return self.api_create_farm()
        if parsed.path == '/api/fields':
            return self.api_create_field()
        if parsed.path == '/api/images':
            return self.api_upload_image()
        self.send_error(HTTPStatus.NOT_FOUND, 'API endpoint not found')

    def handle_api_put(self, parsed):
        if parsed.path.startswith('/api/fields/'):
            return self.api_update_field(parsed.path.split('/')[-1])
        self.send_error(HTTPStatus.NOT_FOUND, 'API endpoint not found')

    def handle_api_delete(self, parsed):
        if parsed.path.startswith('/api/farms/'):
            return self.api_delete_farm(parsed.path.split('/')[-1])
        if parsed.path.startswith('/api/fields/'):
            return self.api_delete_field(parsed.path.split('/')[-1])
        if parsed.path == '/api/images':
            return self.api_delete_images(parsed.query)
        self.send_error(HTTPStatus.NOT_FOUND, 'API endpoint not found')

    def api_get_farms(self):
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute('SELECT id, name FROM farms ORDER BY name').fetchall()
        conn.close()
        data = [dict(row) for row in rows]
        return json_response(self, data)

    def api_get_fields(self, query_string):
        params = parse_qs(query_string)
        farm_id = params.get('farmId', [None])[0]
        if not farm_id:
            return json_response(self, {'error': 'Missing farmId'}, status=HTTPStatus.BAD_REQUEST)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT id, name FROM fields WHERE farm_id = ? ORDER BY name',
            (farm_id,)
        ).fetchall()
        conn.close()
        return json_response(self, [dict(row) for row in rows])

    def api_get_images(self, query_string):
        params = parse_qs(query_string)
        field_id = params.get('fieldId', [None])[0]
        if not field_id:
            return json_response(self, {'error': 'Missing fieldId'}, status=HTTPStatus.BAD_REQUEST)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            'SELECT id, filename, original_name, mime_type, uploaded_at FROM images WHERE field_id = ? ORDER BY uploaded_at DESC',
            (field_id,)
        ).fetchall()
        conn.close()
        return json_response(self, [dict(row) for row in rows])

    def api_get_farm(self, query_string):
        params = parse_qs(query_string)
        farm_id = params.get('farmId', [None])[0]
        if not farm_id:
            return json_response(self, {'error': 'Missing farmId'}, status=HTTPStatus.BAD_REQUEST)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT id, name FROM farms WHERE id = ?', (farm_id,)).fetchone()
        conn.close()
        if not row:
            return json_response(self, {'error': 'Farm not found'}, status=HTTPStatus.NOT_FOUND)
        return json_response(self, dict(row))

    def api_get_field(self, query_string):
        params = parse_qs(query_string)
        field_id = params.get('fieldId', [None])[0]
        if not field_id:
            return json_response(self, {'error': 'Missing fieldId'}, status=HTTPStatus.BAD_REQUEST)
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute('SELECT id, farm_id, name FROM fields WHERE id = ?', (field_id,)).fetchone()
        conn.close()
        if not row:
            return json_response(self, {'error': 'Field not found'}, status=HTTPStatus.NOT_FOUND)
        return json_response(self, dict(row))

    def api_create_farm(self):
        body = parse_body(self)
        name = body.get('name', '').strip()
        if not name:
            return json_response(self, {'error': 'Farm name is required'}, status=HTTPStatus.BAD_REQUEST)
        farm_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO farms (id, name) VALUES (?, ?)', (farm_id, name))
        conn.commit()
        conn.close()
        return json_response(self, {'id': farm_id, 'name': name}, status=HTTPStatus.CREATED)

    def api_create_field(self):
        body = parse_body(self)
        farm_id = body.get('farmId')
        name = body.get('name', '').strip()
        if not farm_id or not name:
            return json_response(self, {'error': 'farmId and field name are required'}, status=HTTPStatus.BAD_REQUEST)
        field_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH)
        conn.execute('INSERT INTO fields (id, farm_id, name) VALUES (?, ?, ?)', (field_id, farm_id, name))
        conn.commit()
        conn.close()
        return json_response(self, {'id': field_id, 'farmId': farm_id, 'name': name}, status=HTTPStatus.CREATED)

    def api_update_field(self, field_id):
        body = parse_body(self)
        name = body.get('name', '').strip()
        if not name:
            return json_response(self, {'error': 'Field name is required'}, status=HTTPStatus.BAD_REQUEST)
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        cur.execute('UPDATE fields SET name = ? WHERE id = ?', (name, field_id))
        if cur.rowcount == 0:
            conn.close()
            return json_response(self, {'error': 'Field not found'}, status=HTTPStatus.NOT_FOUND)
        conn.commit()
        conn.close()
        return json_response(self, {'id': field_id, 'name': name})

    def api_delete_field(self, field_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM fields WHERE id = ?', (field_id,))
        if cur.fetchone() is None:
            conn.close()
            return json_response(self, {'error': 'Field not found'}, status=HTTPStatus.NOT_FOUND)
        conn.close()
        delete_image_files_by_field_ids([field_id])
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM fields WHERE id = ?', (field_id,))
        conn.commit()
        conn.close()
        return json_response(self, {'success': True})

    def api_delete_images(self, query_string):
        params = parse_qs(query_string)
        field_id = params.get('fieldId', [None])[0]
        if not field_id:
            return json_response(self, {'error': 'Missing fieldId'}, status=HTTPStatus.BAD_REQUEST)
        delete_image_files_by_field_ids([field_id])
        return json_response(self, {'success': True})

    def api_delete_farm(self, farm_id):
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('SELECT id FROM farms WHERE id = ?', (farm_id,))
        if cur.fetchone() is None:
            conn.close()
            return json_response(self, {'error': 'Farm not found'}, status=HTTPStatus.NOT_FOUND)
        conn.close()
        delete_image_files_for_farm(farm_id)
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('DELETE FROM farms WHERE id = ?', (farm_id,))
        conn.commit()
        conn.close()
        return json_response(self, {'success': True})

    def api_upload_image(self):
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            return json_response(self, {'error': 'multipart/form-data required'}, status=HTTPStatus.BAD_REQUEST)

        boundary = content_type.split('boundary=')[-1].encode('utf-8')
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)

        def parse_multipart(data, boundary):
            parts = data.split(b'--' + boundary)
            for part in parts:
                if not part or part == b'--\r\n':
                    continue
                yield part.strip(b'\r\n')

        fields = {}
        for part in parse_multipart(body, boundary):
            if not part:
                continue
            header, _, value = part.partition(b'\r\n\r\n')
            disposition = None
            for line in header.split(b'\r\n'):
                if line.lower().startswith(b'content-disposition:'):
                    disposition = line.decode('utf-8')
            if not disposition:
                continue
            name_part = disposition.split('name="')[-1].split('"')[0]
            filename = None
            if 'filename="' in disposition:
                filename = disposition.split('filename="')[-1].split('"')[0]
            value = value.rstrip(b'\r\n')
            if filename:
                fields[name_part] = {'filename': filename, 'content': value}
            else:
                fields[name_part] = value.decode('utf-8')

        field_id = fields.get('fieldId')
        if not field_id:
            return json_response(self, {'error': 'fieldId is required'}, status=HTTPStatus.BAD_REQUEST)

        image_field = fields.get('image')
        if not image_field or not image_field.get('filename'):
            return json_response(self, {'error': 'image file is required'}, status=HTTPStatus.BAD_REQUEST)

        filename = image_field['filename']
        original_name = filename
        unique_name = f"{uuid.uuid4().hex}_{os.path.basename(filename)}"
        file_path = os.path.join(UPLOAD_DIR, unique_name)

        with open(file_path, 'wb') as f:
            f.write(image_field['content'])

        mime_type = 'application/octet-stream'
        if filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            mime_type = 'image/jpeg'
        elif filename.lower().endswith('.png'):
            mime_type = 'image/png'
        elif filename.lower().endswith('.gif'):
            mime_type = 'image/gif'
        elif filename.lower().endswith('.webp'):
            mime_type = 'image/webp'
        elif filename.lower().endswith('.svg'):
            mime_type = 'image/svg+xml'

        image_id = str(uuid.uuid4())
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            'INSERT INTO images (id, field_id, filename, original_name, mime_type, uploaded_at) VALUES (?, ?, ?, ?, ?, datetime("now"))',
            (image_id, field_id, unique_name, original_name, mime_type)
        )
        conn.commit()
        conn.close()

        return json_response(self, {
            'id': image_id,
            'fieldId': field_id,
            'filename': unique_name,
            'originalName': original_name,
            'mimeType': mime_type,
        }, status=HTTPStatus.CREATED)

    def translate_path(self, path):
        parsed = urlparse(path)
        if parsed.path.startswith('/api/'):
            return super().translate_path('/')
        return super().translate_path(path)


if __name__ == '__main__':
    init_db()
    host = '0.0.0.0'
    port = 8000
    print(f'Serving on http://{host}:{port}')
    server = ThreadingHTTPServer((host, port), BeechlandHandler)
    server.serve_forever()
