"""Consistent CSV snapshots and transactional restore for all application tables."""
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
    'branches': ('id', 'name', 'location', 'contact_number'),
    'departments': ('id', 'branch_id', 'name', 'description', 'manager_id', 'status', 'created_at', 'updated_at'),
    'customers': ('id', 'name', 'phone'),
    'employees': ('id', 'name', 'username', 'email', 'password_hash', 'role', 'active'),
    'categories': ('id', 'name'),
    'suppliers': ('id', 'name', 'phone', 'email'),
    'products': ('id', 'name', 'category_id', 'price', 'stock', 'reorder_level'),
    'sales': ('id', 'employee_id', 'customer_name', 'created_at'),
    'sale_items': ('id', 'sale_id', 'product_id', 'quantity', 'unit_price'),
    'purchases': ('id', 'supplier_id', 'product_id', 'employee_id', 'quantity', 'unit_cost', 'created_at'),
}
# Explicit whitelist and dependency order; generated net_pay is intentionally omitted.
TABLES['employees'] += ('department_id', 'supervisor_id', 'nin', 'phone', 'date_hired', 'salary', 'job_type')
TABLES['suppliers'] += ('contact_person', 'address')
TABLES['products'] += ('description',)
TABLES['sales'] += ('customer_id', 'branch_id')
TABLES['purchases'] += ('order_id',)
TABLES.update({
    'company_finance': ('id', 'balance', 'updated_at'),
    'employee_department_memberships': ('id', 'employee_id', 'department_id', 'assigned_at', 'assigned_by', 'is_active'),
    'job_assignments': ('id', 'department_id', 'employee_id', 'title', 'description', 'priority', 'status',
                        'assigned_by', 'assigned_at', 'due_date', 'started_at', 'completed_at', 'updated_at'),
    'job_activity_history': ('id', 'job_id', 'actor_id', 'action', 'previous_status', 'new_status', 'comment', 'created_at'),
    'notifications': ('id', 'employee_id', 'job_id', 'message', 'is_read', 'created_at'),
    'cashiers': ('employee_id', 'pos_terminal_id'),
    'procurement_officers': ('employee_id', 'approval_limit'),
    'accountants': ('employee_id', 'certification_number'),
    'hr_staff': ('employee_id', 'hr_role'),
    'branch_managers': ('employee_id', 'branch_id', 'management_level'),
    'supply': ('supplier_id', 'product_id', 'cost_price', 'lead_time_days'),
    'purchase_orders': ('id', 'supplier_id', 'employee_id', 'order_date', 'status'),
    'purchase_order_items': ('order_id', 'product_id', 'quantity', 'unit_cost'),
    'payroll': ('id', 'employee_id', 'pay_month', 'gross_pay', 'deductions'),
    'ledger_entries': ('id', 'entry_date', 'source_type', 'sale_id', 'payroll_id', 'amount'),
})
# Deliveries reference orders, so restore them after orders.
TABLES['purchases'] = TABLES.pop('purchases')
SNAPSHOT_NAME = r'backup-\d{8}-\d{6}-[a-f0-9]{8}'
MAX_BACKUP_BYTES = 64 * 1024 * 1024
LEGACY_TABLES = {
    'employees': TABLES['employees'][:7], 'categories': TABLES['categories'],
    'suppliers': TABLES['suppliers'][:4], 'products': TABLES['products'][:6],
    'sales': TABLES['sales'][:4], 'sale_items': TABLES['sale_items'], 'purchases': TABLES['purchases'][:7],
}


def snapshot_tables(manifest):
    names = set(manifest.get('tables',{}))
    if names == set(TABLES): return TABLES
    if names == set(LEGACY_TABLES): return LEGACY_TABLES
    raise ValueError('Unsupported or incomplete backup manifest.')


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
                    cursor.execute(f'SELECT {", ".join(columns)} FROM {table} ORDER BY {", ".join(columns[:2])}')
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
        if manifest.get('version') != 1 or manifest.get('time_zone') != '+03:00':
            raise ValueError('Unsupported or incomplete backup manifest.')
        source_tables = snapshot_tables(manifest)
        contents, total_bytes = {}, 0
        for table, columns in source_tables.items():
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
        if source_tables is LEGACY_TABLES:
            additions = {'employees': (None,None,None,'',None,'0','Cashier'),
                         'suppliers': ('',''), 'products': ('',), 'sales': (None,None), 'purchases': (None,)}
            for table, suffix in additions.items():
                contents[table] = [row + suffix for row in contents[table]]
            for table in TABLES: contents.setdefault(table,[])
            contents['cashiers'] = [(row[0],'') for row in contents['employees']]
            from decimal import Decimal
            totals = {}
            for row in contents['sale_items']:
                totals[row[1]] = totals.get(row[1],Decimal(0)) + Decimal(row[3])*Decimal(row[4])
            contents['ledger_entries'] = [(str(i),row[3],'Sale',row[0],None,str(totals[row[0]]))
                                         for i,row in enumerate(contents['sales'],1) if row[0] in totals]
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
                cursor.execute('SET @restoring_snapshot=1')
                for table in TABLES:
                    # Empty-table gap locks also protect against concurrent inserts.
                    cursor.execute(f'SELECT {TABLES[table][0]} FROM {table} FOR UPDATE')
                    existing = cursor.fetchone()
                    if existing and table != 'company_finance':
                        raise ValueError('Restore requires an empty database. Existing records were not changed.')
                    if existing and table == 'company_finance':
                        cursor.execute('DELETE FROM company_finance WHERE id=1 AND balance=800000000.00')
                        if cursor.rowcount != 1:
                            raise ValueError('Restore requires an empty database. Existing records were not changed.')
                for table, columns in TABLES.items():
                    if contents[table]:
                        placeholders = ', '.join(['%s'] * len(columns))
                        rows = contents[table]
                        if table == 'employees':
                            # Self-referencing supervisors may have larger IDs.
                            index = columns.index('supervisor_id')
                            rows = [tuple(None if i == index else v for i,v in enumerate(row)) for row in rows]
                        cursor.executemany(f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({placeholders})', rows)
                        if table == 'employees':
                            for row in contents[table]:
                                cursor.execute('UPDATE employees SET supervisor_id=%s WHERE id=%s', (row[index],row[0]))
                cursor.execute('SET @restoring_snapshot=0')
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return {table: len(rows) for table, rows in contents.items()}


def zip_backup(folder):
    # Validate before serving; never include unrelated files from the filesystem.
    load_backup(folder)
    buffer = io.BytesIO()
    manifest = json.loads((Path(folder)/'manifest.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for filename in ['manifest.json'] + [table + '.csv' for table in snapshot_tables(manifest)]:
            archive.write(Path(folder) / filename, filename)
    buffer.seek(0)
    return buffer
