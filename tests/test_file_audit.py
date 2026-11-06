"""Meaningful preservation tests, using only temporary synthetic data."""
import importlib.util
import os
from pathlib import Path
import shutil
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('audit', Path(__file__).parents[1] / 'migration' / 'file_audit.py')
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


class FileAudit(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.source = self.base / 'source'
        self.source.mkdir()
        (self.source / 'cur').mkdir()
        (self.source / 'cur' / 'message:2,S').write_bytes(b'Subject: test\r\n\r\nmail\x00\xff')
        (self.source / 'empty').mkdir()
        (self.source / 'sieve').mkdir()
        (self.source / 'sieve' / 'active.sieve').write_text('keep;')
        (self.source / '.dovecot.sieve').symlink_to('sieve/active.sieve')
        self.copy = self.base / 'copy'
        shutil.copytree(self.source, self.copy, symlinks=True)

    def manifests(self):
        first, second = self.base / 'first.sqlite', self.base / 'second.sqlite'
        audit.capture(self.source, first)
        audit.capture(self.copy, second)
        return first, second

    def test_exact_copy_and_internal_sieve_link(self):
        first, second = self.manifests()
        self.assertTrue(audit.compare(first, second)['matches'])
        self.assertEqual(first.stat().st_mode & 0o777, 0o600)

    def test_mail_content_corruption_detected_even_same_length(self):
        target = self.copy / 'cur' / 'message:2,S'
        before = target.stat()
        target.write_bytes(b'x' * before.st_size)
        os.utime(target, ns=(before.st_atime_ns, before.st_mtime_ns))
        result = audit.compare(*self.manifests())
        self.assertFalse(result['matches'])
        self.assertIn('sha256', result['examples'][0]['fields'])

    def test_filename_flags_and_missing_empty_directory_detected(self):
        (self.copy / 'cur' / 'message:2,S').rename(self.copy / 'cur' / 'message:2,')
        (self.copy / 'empty').rmdir()
        result = audit.compare(*self.manifests())
        self.assertFalse(result['matches'])
        self.assertGreaterEqual(result['missing'], 2)
        self.assertEqual(result['added'], 1)

    def test_external_link_is_refused_and_manifest_stays_incomplete(self):
        (self.source / 'escape').symlink_to('../copy')
        output = self.base / 'incomplete.sqlite'
        with self.assertRaises(ValueError):
            audit.capture(self.source, output)
        self.assertTrue(output.exists())
        with self.assertRaises(ValueError):
            audit.readonly(output)

    def test_overwrite_and_manifest_inside_tree_refused(self):
        output = self.base / 'existing.sqlite'
        output.write_text('retain me')
        with self.assertRaises(FileExistsError):
            audit.capture(self.source, output)
        self.assertEqual(output.read_text(), 'retain me')
        with self.assertRaises(ValueError):
            audit.capture(self.source, self.source / 'manifest.sqlite')

    def test_linked_root_and_special_file_refused(self):
        linked = self.base / 'linked'
        linked.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            audit.capture(linked, self.base / 'linked.sqlite')
        os.mkfifo(self.source / 'pipe')
        with self.assertRaises(ValueError):
            audit.capture(self.source, self.base / 'special.sqlite')

    def test_timestamp_and_ownership_translation_are_explicit(self):
        first, second = self.manifests()
        with sqlite3.connect(second) as db:
            db.execute('UPDATE entries SET uid=uid+1')
        self.assertFalse(audit.compare(first, second)['matches'])
        self.assertTrue(audit.compare(first, second, ignore_ownership=True)['matches'])
        with sqlite3.connect(second) as db:
            db.execute('UPDATE entries SET mtime_ns=mtime_ns+1')
        self.assertFalse(audit.compare(first, second, ignore_ownership=True)['matches'])


if __name__ == '__main__':
    unittest.main()
