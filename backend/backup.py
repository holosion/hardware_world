"""Consistent CSV snapshots and transactional restore for the seven tables."""
import csv
import hashlib
import io
import json
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from db import connect

# Parent tables precede child tables, so foreign keys remain enabled on restore.
TABLES = {
    'employees': ('id', 'name', 'username', 'email', 'password_hash', 'role', 'active'),
    'categories': ('id', 'name'),
    'suppliers': ('id', 'name', 'phone', 'email'),
    'products': ('id', 'name', 'category_id', 'price', 'stock', 'reorder_level'),
    'sales': ('id', 'employee_id', 'customer_name', 'created_at'),
    'sale_items': ('id', 'sale_id', 'product_id', 'quantity', 'unit_price'),
    'purchases': ('id', 'supplier_id', 'product_id', 'employee_id', 'quantity', 'unit_cost', 'created_at'),
}
SNAPSHOT_NAME = r'backup-\d{8}-\d{6}-[a-f0-9]{8}'
MAX_BACKUP_BYTES = 64 * 1024 * 1024


def encode(value):
    if value is None:
        return '\\N'
    if isinstance(value, datetime):
        return value.isoformat(sep=' ')
    value = str(value)
    # Keep literal null markers and spreadsheet formula-like text reversible.
    return '\\' + value if value.startswith(('\\', '=', '+', '-', '@', '\t', '\r', '\n')) else value


def decode(value):
    if value == '\\N':
        return None
    return value[1:] if value.startswith('\\') else value


def create_backup(settings, root):
    root = Path(root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone(timedelta(hours=3)))
    name = 'backup-' + now.strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
    manifest = {'version': 1, 'created_at': now.isoformat(), 'time_zone': '+03:00', 'tables': {}}
    # Publish only a completed folder; failed writes never appear as backups.
    with tempfile.TemporaryDirectory(prefix='.pending-', dir=root) as temporary:
        staging = Path(temporary) / name
        staging.mkdir()
        with connect(settings) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION time_zone = '+03:00'")
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                cursor.execute('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY')
                for table, columns in TABLES.items():
                    cursor.execute(f'SELECT {", ".join(columns)} FROM {table} ORDER BY id')
                    rows = cursor.fetchall()
                    path = staging / (table + '.csv')
                    with path.open('w', encoding='utf-8', newline='') as handle:
                        writer = csv.writer(handle)
                        writer.writerow(columns)
                        writer.writerows([encode(row[column]) for column in columns] for row in rows)
                    manifest['tables'][table] = {'rows': len(rows), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
                connection.rollback()  # End the read-only snapshot.
        (staging / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        staging.rename(root / name)
    return root / name


def backup_folder(root, name):
    root = Path(root).resolve()
    if not re.fullmatch(SNAPSHOT_NAME, name):
        raise ValueError('Invalid backup name.')
    folder = (root / name).resolve()
    if folder.parent != root or not folder.is_dir():
        raise ValueError('Backup folder was not found.')
    return folder


def list_backups(root):
    root = Path(root)
    if not root.exists():
        return []
    return sorted((p.name for p in root.iterdir() if re.fullmatch(SNAPSHOT_NAME, p.name)
                   and p.is_dir() and not p.is_symlink() and (p / 'manifest.json').is_file()), reverse=True)


def load_backup(folder):
    """Validate all files before beginning any database changes."""
    folder = Path(folder).resolve()
    try:
        manifest_path = folder / 'manifest.json'
        if manifest_path.stat().st_size > 64 * 1024:
            raise ValueError('Backup manifest is too large.')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if (manifest.get('version') != 1 or manifest.get('time_zone') != '+03:00'
                or set(manifest.get('tables', {})) != set(TABLES)):
            raise ValueError('Unsupported or incomplete backup manifest.')
        contents, total_bytes = {}, 0
        for table, columns in TABLES.items():
            path = folder / (table + '.csv')
            if path.resolve().parent != folder:
                raise ValueError('Backup files must stay inside the backup folder.')
            total_bytes += path.stat().st_size
            if total_bytes > MAX_BACKUP_BYTES:
                raise ValueError('Backup exceeds the 64 MB restore limit.')
            raw = path.read_bytes()
            info = manifest['tables'][table]
            if hashlib.sha256(raw).hexdigest() != info['sha256']:
                raise ValueError(f'{table}.csv failed its checksum. Use an unchanged backup.')
            reader = csv.reader(io.StringIO(raw.decode('utf-8'), newline=''), strict=True)
            if next(reader, []) != list(columns):
                raise ValueError(f'{table}.csv has the wrong column headers.')
            rows = []
            for row in reader:
                if len(row) != len(columns):
                    raise ValueError(f'{table}.csv has an invalid row.')
                rows.append(tuple(decode(value) for value in row))
            if len(rows) != info['rows']:
                raise ValueError(f'{table}.csv has an incorrect row count.')
            contents[table] = rows
        return contents
    except (OSError, json.JSONDecodeError, UnicodeError, csv.Error, KeyError, TypeError, AttributeError) as error:
        raise ValueError('Backup is missing files or is not a valid CSV snapshot.') from error


def restore_backup(folder, settings):
    contents = load_backup(folder)
    with connect(settings) as connection:
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET SESSION time_zone = '+03:00'")
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
                connection.begin()
                for table in TABLES:
                    # Empty-table gap locks also protect against concurrent inserts.
                    cursor.execute(f'SELECT id FROM {table} FOR UPDATE')
                    if cursor.fetchone():
                        raise ValueError('Restore requires an empty database. Existing records were not changed.')
                for table, columns in TABLES.items():
                    if contents[table]:
                        placeholders = ', '.join(['%s'] * len(columns))
                        cursor.executemany(f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders})', contents[table])
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {table: len(rows) for table, rows in contents.items()}


def zip_backup(folder):
    # Validate before serving; never include unrelated files from the filesystem.
    load_backup(folder)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename in ['manifest.json'] + [table + '.csv' for table in TABLES]:
            archive.write(Path(folder) / filename, filename)
    buffer.seek(0)
    return buffer
