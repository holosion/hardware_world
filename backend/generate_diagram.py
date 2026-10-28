"""Generate the VS Code ER diagram from live MySQL schema metadata only.

Run: backend/.venv/Scripts/python.exe backend/generate_diagram.py
"""
import re

from db import ROOT, connect, connection_settings


def generate_diagram():
    settings = connection_settings()
    with connect(settings) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                'SELECT c.TABLE_NAME, c.COLUMN_NAME, c.DATA_TYPE, c.COLUMN_TYPE, '
                'c.COLUMN_KEY, c.IS_NULLABLE FROM information_schema.COLUMNS c '
                'JOIN information_schema.TABLES t ON t.TABLE_SCHEMA=c.TABLE_SCHEMA AND t.TABLE_NAME=c.TABLE_NAME '
                "WHERE c.TABLE_SCHEMA=%s AND t.TABLE_TYPE='BASE TABLE' "
                'ORDER BY c.TABLE_NAME, c.ORDINAL_POSITION', (settings['database'],))
            columns = cursor.fetchall()
            cursor.execute(
                'SELECT TABLE_NAME, COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME '
                'FROM information_schema.KEY_COLUMN_USAGE '
                'WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL '
                'ORDER BY TABLE_NAME, COLUMN_NAME', (settings['database'],))
            foreign_keys = cursor.fetchall()
            cursor.execute('SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) AS fields '
                           'FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND NON_UNIQUE=0 '
                           'GROUP BY TABLE_NAME,INDEX_NAME', (settings['database'],))
            unique_single = {(row['TABLE_NAME'],row['fields']) for row in cursor.fetchall() if ',' not in row['fields']}
        connection.rollback()
    if not columns:
        raise ValueError('No database tables found. Run init-db first.')
    tables = {}
    for column in columns:
        table, name = column['TABLE_NAME'], column['COLUMN_NAME']
        if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value) for value in (table, name)):
            raise ValueError('This diagram supports simple SQL table and column names only.')
        tables.setdefault(table, []).append(column)
    fk_columns = {(key['TABLE_NAME'], key['COLUMN_NAME']) for key in foreign_keys}
    diagram = ['erDiagram', '    direction LR']
    for table, attributes in tables.items():
        diagram.append(f'    {table} {{')
        for column in attributes:
            name = column['COLUMN_NAME']
            kind = column['DATA_TYPE']
            if kind in ('varchar', 'char', 'text'):
                kind = 'string'
            if column['COLUMN_TYPE'] == 'tinyint(1)':
                kind = 'boolean'
            keys = []
            if column['COLUMN_KEY'] == 'PRI':
                keys.append('PK')
            elif column['COLUMN_KEY'] == 'UNI':
                keys.append('UK')
            if (table, name) in fk_columns:
                keys.append('FK')
            key_text = ' ' + ', '.join(keys) if keys else ''
            optional = ' "optional"' if column['IS_NULLABLE'] == 'YES' else ''
            diagram.append(f'        {kind} {name}{key_text}{optional}')
        diagram.append('    }')
    for key in foreign_keys:
        child, field, parent = key['TABLE_NAME'], key['COLUMN_NAME'], key['REFERENCED_TABLE_NAME']
        column = next(c for c in tables[child] if c['COLUMN_NAME'] == field)
        parent_end = '|o' if column['IS_NULLABLE'] == 'YES' else '||'
        child_end = 'o|' if (child,field) in unique_single else 'o{'
        diagram.append(f'    {parent} {parent_end}--{child_end} {child} : {field}')
    text = (
        '# Hardware World - database diagram\n\n'
        f'Generated from the live MySQL schema **{settings["database"]}**: '
        f'**{len(tables)} tables** and **{len(foreign_keys)} foreign-key relationships**.\n\n'
        'In VS Code, this file is configured to open as a visual preview. '
        'If you see the source, press **Ctrl+Shift+V**. '
        'Use the diagram controls to zoom, or hold **Alt** and scroll; Alt-drag pans.\n\n'
        '```mermaid\n' + '\n'.join(diagram) + '\n```\n\n'
        '**PK** = primary key; **FK** = foreign key; **UK** = unique field. '
        '**optional** means the field allows NULL. '
        'The forked end of a relationship means many; the double line means exactly one.\n\n'
        '## How the tables connect\n\n'
        '| Parent field | Referencing field |\n| --- | --- |\n'
    )
    for key in foreign_keys:
        text += (f'| `{key["REFERENCED_TABLE_NAME"]}.{key["REFERENCED_COLUMN_NAME"]}` '
                 f'| `{key["TABLE_NAME"]}.{key["COLUMN_NAME"]}` |\n')
    text += (
        '\n## Explain it to your lecturer\n\n'
        '- Categories group products.\n'
        '- Employees record sales and receive purchases.\n'
        '- A sale contains sale items; each item points to a product.\n'
        '- Each purchase links a supplier, a product, and the employee who received it.\n'
        '- `products.stock` holds the current quantity; purchases increase it and sales reduce it.\n\n'
        '## Refresh after changing table structure\n\n'
        'In VS Code, run **Terminal -> Run Task -> Database: Refresh ER diagram**, or run:\n\n'
        '```powershell\nbackend/.venv/Scripts/python.exe backend/generate_diagram.py\n```\n\n'
        'This is a schema snapshot generated locally. It reads table metadata and does not change records. '
        'Use SQLTools to browse live rows.\n'
    )
    output = ROOT / 'DATABASE_DIAGRAM.md'
    output.write_text(text, encoding='utf-8')
    print(f'Generated {output.name}: {len(tables)} tables, {len(foreign_keys)} relationships, {len(columns)} columns.')
    return output


if __name__ == '__main__':
    generate_diagram()
