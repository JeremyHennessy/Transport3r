"""Stage and switch immutable public-evidence files; never provision a server.

Requires an existing nationwide warehouse and a matching independent deep audit.
It re-runs deep warehouse validation, but does not certify original source bytes,
new source acquisition, private hosting, or post-restart HTTP/UI reconciliation.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import pathlib
import re
import shutil
import tempfile
import uuid

from audit_warehouse_integrity import audit, fingerprint
from nationwide_evidence import acceptance, connect
from integrity_report import load_report

SCHEMA = 'TRANSPORT3R_EVIDENCE_INSTALL_1'
POINTER = 'TRANSPORT3R_EVIDENCE_ACTIVATION_1'
ROOT = pathlib.Path(__file__).resolve().parents[1]
FILES = {'warehouse.duckdb', 'audit.json', 'manifest.json'}



def sync_directory(path):
    """Persist directory entries on POSIX; a file fsync alone is insufficient."""
    if os.name == 'posix':
        fd = os.open(path, os.O_RDONLY | getattr(os, 'O_DIRECTORY', 0))
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def durable_directory(path):
    """Persist newly created parent links before publishing children beneath them."""
    path = pathlib.Path(path)
    missing = []
    candidate = path
    while not candidate.exists():
        missing.append(candidate)
        candidate = candidate.parent
    path.mkdir(parents=True, exist_ok=True)
    for created in reversed(missing):
        sync_directory(created)
        sync_directory(created.parent)


def sha256(path):
    value = hashlib.sha256()
    with pathlib.Path(path).open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def storage(path):
    value = pathlib.Path(path).resolve()
    if value == ROOT or ROOT in value.parents or any(part.lower() in ('public', 'dist') for part in value.parts):
        raise ValueError('Evidence storage must be outside the repository and public static paths')
    return value


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{64}', value):
        raise ValueError('Exact SHA-256 release identifier required')
    return value


def read_json(path, maximum=2 * 1024 * 1024):
    path = pathlib.Path(path)
    if path.is_symlink() or not path.is_file() or path.stat().st_size > maximum:
        raise ValueError('Expected a bounded regular JSON file')
    with path.open('rb') as handle:
        raw = handle.read(maximum + 1)
    if len(raw) > maximum:
        raise ValueError('JSON size limit')
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('Duplicate manifest key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite manifest value')))


def write_new(path, value):
    data = (json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + '\n').encode()
    with pathlib.Path(path).open('xb') as handle:
        handle.write(data); handle.flush(); os.fsync(handle.fileno())


def validated_pair(warehouse, report_path):
    path = pathlib.Path(warehouse)
    if path.is_symlink() or not path.is_file() or pathlib.Path(str(path) + '.wal').exists():
        raise ValueError('Closed regular immutable warehouse required')
    stamp = fingerprint(path)
    digest = sha256(path)
    db = connect(path)
    try:
        receipt = acceptance(db)
        report = load_report(report_path, receipt, digest)
    finally:
        db.close()
    if stamp != fingerprint(path):
        raise ValueError('Warehouse changed during validation')
    return receipt, report, digest


def stage(root, warehouse, report_path):
    root = storage(root); durable_directory(root)
    receipt, report, digest = validated_pair(warehouse, report_path)
    target = root / 'releases' / digest
    durable_directory(target.parent)
    if target.exists():
        raise FileExistsError('Release already exists; inspect it, do not overwrite it')
    fresh = audit(warehouse, deep=True)
    if not fresh.get('release_ready') or fresh.get('status') != 'PASS' or fresh.get('warehouse_sha256') != digest:
        raise ValueError('Independent deep warehouse audit failed; no release staged')
    pending = pathlib.Path(tempfile.mkdtemp(prefix='.staging-', dir=target.parent))
    try:
        shutil.copyfile(warehouse, pending / 'warehouse.duckdb')
        shutil.copyfile(report_path, pending / 'audit.json')
        copied, copied_audit, copied_hash = validated_pair(pending / 'warehouse.duckdb', pending / 'audit.json')
        if copied_hash != digest or copied['cut_id'] != receipt['cut_id'] or copied_audit != report:
            raise ValueError('Source changed or copied release differs')
        manifest = {'schema': SCHEMA, 'release_id': digest, 'warehouse_sha256': digest,
                    'audit_sha256': sha256(pending / 'audit.json'), 'cut_id': copied['cut_id'],
                    'cut_available_at': copied['cut_available_at'], 'source_count': copied['sources'],
                    'staged_at': datetime.now(timezone.utc).isoformat(),
                    'validation_scope': 'INDEPENDENT_WAREHOUSE_DEEP_AUDIT_AND_FILE_COPY',
                    'original_source_bytes_revalidated': False, 'deployed': False,
                    'private_insurer_hosting': False}
        write_new(pending / 'manifest.json', manifest)
        for name in FILES:
            path = pending / name
            path.chmod(0o444)
            with path.open('rb') as handle:
                os.fsync(handle.fileno())
        # Persist file entries before rename, and persist the renamed entry before
        # returning success. File fsyncs do not make either directory durable.
        sync_directory(pending)
        os.rename(pending, target)
        sync_directory(target.parent)
        return manifest
    except Exception as error:
        if pending.exists():
            write_new(pending / 'failed.json', {'status': 'NOT_ACCEPTED', 'error': type(error).__name__,
                                               'promoted': False})
        raise


def inspect(root, release_id):
    root = storage(root); release_id = identifier(release_id)
    folder = root / 'releases' / release_id
    if folder.is_symlink() or not folder.is_dir() or {p.name for p in folder.iterdir()} != FILES:
        raise ValueError('Expected the exact staged release files')
    manifest = read_json(folder / 'manifest.json')
    receipt, report, digest = validated_pair(folder / 'warehouse.duckdb', folder / 'audit.json')
    if (manifest.get('schema') != SCHEMA or manifest.get('release_id') != release_id or digest != release_id or
        manifest.get('warehouse_sha256') != digest or manifest.get('audit_sha256') != sha256(folder / 'audit.json') or
        manifest.get('cut_id') != receipt['cut_id'] or manifest.get('cut_available_at') != receipt['cut_available_at'] or
        manifest.get('source_count') != receipt['sources']):
        raise ValueError('Release manifest or installed files do not reconcile')
    return manifest


def current(root):
    root = storage(root); path = root / 'current.json'
    if not path.exists():
        return None
    value = read_json(path)
    if not isinstance(value, dict) or value.get('schema') != POINTER:
        raise ValueError('Unknown activation pointer')
    identifier(value.get('release_id'))
    activation = value.get('activation_id')
    if not isinstance(activation, str) or not re.fullmatch('[0-9a-f]{32}', activation):
        raise ValueError('Invalid activation identity')
    if read_json(root / 'history' / (activation + '.json')) != value:
        raise ValueError('Current pointer does not match immutable activation history')
    return value


@contextmanager
def activation_lock(root):
    path = root / '.activation.lock'
    # A crash leaves the lock for operator inspection; never silently steal it.
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        os.write(fd, str(os.getpid()).encode()); os.fsync(fd)
        yield
    finally:
        os.close(fd); path.unlink()


def activate(root, release_id, expected_current, operator):
    root = storage(root)
    if not isinstance(operator, str) or not operator.strip() or len(operator) > 200 or any(ord(c) < 32 for c in operator):
        raise ValueError('Explicit operator attribution required')
    if expected_current is not None:
        identifier(expected_current)
    with activation_lock(root):
        inspect(root, release_id)
        prior = current(root)
        actual = prior['release_id'] if prior else None
        if actual != expected_current:
            raise ValueError('Current release changed; reread before activation')
        value = {'schema': POINTER, 'activation_id': uuid.uuid4().hex,
                 'release_id': release_id, 'previous_release_id': actual,
                 'previous_activation_id': prior['activation_id'] if prior else None,
                 'operator': operator, 'activated_at': datetime.now(timezone.utc).isoformat(),
                 'state': 'POINTER_CHANGED_RESTART_AND_HTTP_VERIFICATION_REQUIRED',
                 'deployed': False, 'private_insurer_hosting': False}
        history = root / 'history'; durable_directory(history)
        write_new(history / (value['activation_id'] + '.json'), value)
        # The pointer may reference only history whose directory entry is durable.
        sync_directory(history)
        temporary = root / ('.current-' + value['activation_id'] + '.json')
        write_new(temporary, value)
        os.replace(temporary, root / 'current.json')
        sync_directory(root)
        return value


def rollback(root, expected_current, operator):
    prior = current(root)
    if prior is None or prior.get('previous_release_id') is None:
        raise ValueError('No previous accepted release is recorded')
    if prior['release_id'] != expected_current:
        raise ValueError('Current release changed; reread before rollback')
    return activate(root, prior['previous_release_id'], expected_current, operator)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True)
    commands = parser.add_subparsers(dest='command', required=True)
    staged = commands.add_parser('stage'); staged.add_argument('--warehouse', required=True); staged.add_argument('--audit', required=True)
    viewed = commands.add_parser('inspect'); viewed.add_argument('--release', required=True)
    commands.add_parser('current')
    activated = commands.add_parser('activate'); activated.add_argument('--release', required=True)
    for command in (activated, commands.add_parser('rollback')):
        command.add_argument('--expected-current', required=True, help='Exact current release SHA, or NONE for first activation')
        command.add_argument('--operator', required=True)
    args = parser.parse_args()
    if args.command == 'stage': value = stage(args.root, args.warehouse, args.audit)
    elif args.command == 'inspect': value = inspect(args.root, args.release)
    elif args.command == 'current': value = current(args.root)
    elif args.command == 'activate': value = activate(args.root, args.release, None if args.expected_current == 'NONE' else args.expected_current, args.operator)
    else: value = rollback(args.root, args.expected_current, args.operator)
    print(json.dumps(value, indent=2))


if __name__ == '__main__':
    main()
