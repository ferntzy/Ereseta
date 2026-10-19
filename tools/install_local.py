from contextlib import closing
"""Install/update EReseta without overwriting existing installed patient records."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3


def install(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    if source == destination:
        raise ValueError('Source and installation folder must differ.')
    if not (source / 'EReseta.exe').is_file():
        raise FileNotFoundError('Build dist/EReseta.exe before installing.')
    destination.mkdir(parents=True, exist_ok=True)
    # Fail before migrating data if Windows has locked the installed executable.
    staged = destination / 'EReseta.new.exe'
    shutil.copy2(source / 'EReseta.exe', staged)
    os.replace(staged, destination / 'EReseta.exe')
    for folder in ('assets', 'prescriptions'):
        (destination / folder).mkdir(exist_ok=True)
        if (source / folder).exists():
            for original in (source / folder).rglob('*'):
                target = destination / original.relative_to(source)
                if original.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                elif not target.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(original, target)
    icon = source.parent / 'assets' / 'ereseta.ico'
    if icon.exists():
        shutil.copy2(icon, destination / 'assets' / 'ereseta.ico')
    source_db, target_db = source / 'ereseta_local.db', destination / 'ereseta_local.db'
    migrated = False
    if source_db.exists() and not target_db.exists():
        with closing(sqlite3.connect(source_db.as_uri() + '?mode=ro', uri=True)) as old:
            with closing(sqlite3.connect(target_db)) as new:
                old.backup(new)
        def relocate(value):
            if not value:
                return value
            path = Path(value)
            if not path.is_absolute():
                path = source / path
            if not path.is_file():
                return value
            try:
                target = destination / path.resolve().relative_to(source)
            except ValueError:
                digest = hashlib.sha256(str(path).encode()).hexdigest()[:10]
                target = destination / 'assets' / ('imported_' + digest + '_' + path.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
            return str(target)
        def relocate_settings(value):
            if isinstance(value, dict):
                return {key: relocate(child) if key in ('path', 'rx_symbol_path') and isinstance(child, str)
                        else relocate_settings(child) for key, child in value.items()}
            if isinstance(value, list):
                return [relocate_settings(child) for child in value]
            return value
        with closing(sqlite3.connect(target_db)) as db, db:
            for table, column in [('physicians', 'signature_path'), ('prescriptions', 'pdf_path')]:
                for record_id, value in db.execute(f'SELECT id, {column} FROM {table}').fetchall():
                    db.execute(f'UPDATE {table} SET {column}=? WHERE id=?', (relocate(value), record_id))
            for key, value in db.execute('SELECT key, value FROM settings').fetchall():
                db.execute('UPDATE settings SET value=? WHERE key=?', (json.dumps(relocate_settings(json.loads(value))), key))
            assert db.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        migrated = True
    (destination / 'installation.json').write_text(json.dumps({'app': 'EReseta', 'data_directory': str(destination)}, indent=2))
    print('Installation ready:', destination)
    print('Existing records migrated.' if migrated else 'Installed records preserved; program updated.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source')
    parser.add_argument('destination')
    args = parser.parse_args()
    install(args.source, args.destination)
