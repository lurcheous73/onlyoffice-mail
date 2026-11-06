#!/usr/bin/env python3
"""Hash stable OFFLINE copies; compare paths, bytes, links and metadata.

Does not copy, restore, delete, contact a host or execute SQL on a mail database.
Only a new, explicitly named private SQLite manifest is written by capture.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat
import sys

COLUMNS = ('path', 'kind', 'size', 'sha256', 'link', 'mode', 'uid', 'gid', 'mtime_ns')


def unlinked(path):
    path = Path(os.path.abspath(path))
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('Linked root/manifest path is not permitted')
    return path


def stamp(s):
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_mode, s.st_uid, s.st_gid


def file_hash(path, expected):
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'rb') as handle:
        if stamp(os.fstat(handle.fileno())) != stamp(expected):
            raise ValueError('Tree changed during capture')
        digest = hashlib.sha256()
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(block)
        if stamp(os.fstat(handle.fileno())) != stamp(expected):
            raise ValueError('File changed during capture')
    if stamp(path.lstat()) != stamp(expected):
        raise ValueError('File replaced during capture')
    return digest.hexdigest()


def capture(root, output):
    root, output = unlinked(root), unlinked(output)
    if not root.is_dir():
        raise ValueError('Offline tree must be a directory')
    if output == root or root in output.parents:
        raise ValueError('Manifest must be outside the captured tree')
    if not output.parent.is_dir():
        raise ValueError('Manifest parent must already exist')
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    os.close(descriptor)
    db = sqlite3.connect(output)
    try:
        db.execute('PRAGMA trusted_schema=OFF')
        db.execute('CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
        db.execute('CREATE TABLE entries (path TEXT PRIMARY KEY, kind TEXT NOT NULL, size INTEGER NOT NULL, sha256 TEXT, link TEXT, mode INTEGER, uid INTEGER, gid INTEGER, mtime_ns INTEGER)')
        db.execute("INSERT INTO meta VALUES ('schema','1')")
        db.execute("INSERT INTO meta VALUES ('complete','false')")
        db.commit()
        totals = {'files': 0, 'directories': 0, 'symlinks': 0, 'bytes': 0}

        def visit(path):
            before = path.lstat()
            name = path.relative_to(root).as_posix()
            kind, size, digest, link = None, 0, None, None
            if stat.S_ISREG(before.st_mode):
                kind, size, digest = 'file', before.st_size, file_hash(path, before)
                totals['files'] += 1
                totals['bytes'] += size
            elif stat.S_ISDIR(before.st_mode):
                kind = 'directory'
                totals['directories'] += 1
            elif stat.S_ISLNK(before.st_mode):
                kind, link = 'symlink', os.readlink(path)
                target = Path(link)
                # Absolute links bind to a different root on restore; refuse.
                if target.is_absolute() or '\x00' in link:
                    raise ValueError('Absolute or invalid symlink requires review')
                resolved = (path.parent / target).resolve()
                if resolved != root and root not in resolved.parents:
                    raise ValueError('Symlink escapes captured tree')
                totals['symlinks'] += 1
            else:
                raise ValueError('Special filesystem entry requires review')
            db.execute('INSERT INTO entries VALUES (?,?,?,?,?,?,?,?,?)',
                       (name, kind, size, digest, link, stat.S_IMODE(before.st_mode),
                        before.st_uid, before.st_gid, before.st_mtime_ns))
            if kind == 'directory':
                with os.scandir(path) as children:
                    names = sorted(child.name for child in children)
                for child in names:
                    visit(path / child)
            if stamp(path.lstat()) != stamp(before):
                raise ValueError('Tree changed during capture')

        visit(root)
        digest = hashlib.sha256()
        for row in db.execute('SELECT * FROM entries ORDER BY path'):
            digest.update((json.dumps(row, ensure_ascii=True, separators=(',', ':')) + '\n').encode())
        summary = dict(totals, tree_sha256=digest.hexdigest())
        db.execute("INSERT INTO meta VALUES ('summary',?)", (json.dumps(summary),))
        db.execute("UPDATE meta SET value='true' WHERE key='complete'")
        db.commit()
        return summary
    except BaseException:
        db.rollback()
        # Keep the incomplete output for diagnosis; never remove or overwrite it.
        raise
    finally:
        db.close()


def readonly(path):
    path = unlinked(path).resolve(strict=True)
    db = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)
    db.execute('PRAGMA trusted_schema=OFF')
    db.execute('PRAGMA query_only=ON')
    meta = dict(db.execute('SELECT key,value FROM meta'))
    if meta.get('schema') != '1' or meta.get('complete') != 'true':
        db.close()
        raise ValueError('Manifest is incomplete or unsupported')
    return db


def compare(before, after, ignore_ownership=False):
    left, right = readonly(before), readonly(after)
    try:
        result = {'missing': 0, 'added': 0, 'changed': 0, 'examples': [],
                  'ownership_comparison': not ignore_ownership}

        def record(kind, path, fields=None):
            result[kind] += 1
            if len(result['examples']) < 10:
                result['examples'].append({'difference': kind, 'path': path, 'fields': fields or []})

        for row in left.execute('SELECT * FROM entries ORDER BY path'):
            found = right.execute('SELECT * FROM entries WHERE path=?', (row[0],)).fetchone()
            if found is None:
                record('missing', row[0])
            else:
                fields = [name for i, name in enumerate(COLUMNS) if row[i] != found[i]
                          and not (ignore_ownership and name in ('uid', 'gid'))]
                if fields:
                    record('changed', row[0], fields)
        for (name,) in right.execute('SELECT path FROM entries ORDER BY path'):
            if left.execute('SELECT 1 FROM entries WHERE path=?', (name,)).fetchone() is None:
                record('added', name)
        result['matches'] = not any(result[k] for k in ('missing', 'added', 'changed'))
        return result
    finally:
        left.close()
        right.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    cap = sub.add_parser('capture')
    cap.add_argument('offline_tree', type=Path)
    cap.add_argument('new_manifest', type=Path)
    diff = sub.add_parser('compare')
    diff.add_argument('before', type=Path)
    diff.add_argument('after', type=Path)
    diff.add_argument('--ignore-ownership', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'capture':
            print(json.dumps(capture(args.offline_tree, args.new_manifest)))
        else:
            result = compare(args.before, args.after, args.ignore_ownership)
            print(json.dumps(result))
            return 0 if result['matches'] else 1
    except (ValueError, OSError, RuntimeError, sqlite3.Error) as exc:
        parser.exit(2, type(exc).__name__ + ': ' + str(exc) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
