import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bundle', ROOT / 'migration/backup_bundle.py')
bundle = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bundle)

class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.backup = self.root / 'backup'
        self.backup.mkdir()
        self.lab = self.root / 'lab'
        self.lab.mkdir()
        (self.lab / '.workspace-mail-lab').write_text('synthetic fixture')
        (self.backup / 'database.sql').write_text('-- synthetic SQL backup\n')
        self.tar('community-data.tar.gz', [('.private/machinekey', b'synthetic-key'), ('mail/body.html', b'Example')])
        self.tar('mail-data.tar.gz', [('example.test/Maildir/cur/1', b'Example message')])
        self.tar('configuration.tar.gz', [('notes.txt', b'Synthetic config archive')])
        self.manifest()

    def tar(self, name, files, malicious=None):
        with tarfile.open(self.backup / name, 'w:gz') as out:
            for path, data in files:
                member = tarfile.TarInfo(path)
                member.size = len(data)
                member.mode = 0o640
                out.addfile(member, io.BytesIO(data))
            if malicious is not None:
                out.addfile(malicious)

    def manifest(self):
        self.meta = {'schema':1,'capture_id':'synthetic-001','consistency_evidence':'Synthetic offline fixture',
                     'versions':bundle.BASELINE,'databases':['onlyoffice','onlyoffice_mailserver'],
                     'artifacts':{n:{'bytes':(self.backup/n).stat().st_size,'sha256':bundle.digest(self.backup/n)} for n in bundle.REQUIRED}}
        self.write_manifest()

    def write_manifest(self):
        (self.backup / 'manifest.json').write_text(json.dumps(self.meta))

    def test_success_preserves_content_and_receipt(self):
        target = self.lab / 'first'
        receipt = bundle.unpack(self.backup, target, preserve_owner=False)
        self.assertEqual((target/'community-data/mail/body.html').read_bytes(), b'Example')
        self.assertEqual(receipt['capture_id'], 'synthetic-001')
        self.assertEqual(receipt['manifest_sha256'], bundle.digest(self.backup/'manifest.json'))

    def test_archive_root_metadata_is_preserved(self):
        root=tarfile.TarInfo('.')
        root.type=tarfile.DIRTYPE
        root.mode=0o750
        self.tar('mail-data.tar.gz',[('message',b'Example')],root)
        self.manifest()
        target=self.lab/'root-mode'
        bundle.unpack(self.backup,target,False)
        self.assertEqual((target/'mail-data').stat().st_mode & 0o777,0o750)
        self.assertEqual((target/'mail-data/message').read_bytes(),b'Example')

    def test_corruption_fails_before_any_target_write(self):
        (self.backup/'database.sql').write_text('corrupt')
        with self.assertRaises(ValueError):
            bundle.unpack(self.backup,self.lab/'first',False)
        self.assertFalse((self.lab/'first').exists())

    def test_missing_mail_key_refused(self):
        self.tar('community-data.tar.gz',[('mail/body.html',b'Example')])
        self.manifest()
        with self.assertRaisesRegex(ValueError,'machine key'):
            bundle.verify(self.backup)

    def test_no_overwrites(self):
        target=self.lab/'first'
        target.mkdir()
        (target/'keep').write_text('untouched')
        with self.assertRaises(ValueError):
            bundle.unpack(self.backup,target,False)
        self.assertEqual((target/'keep').read_text(),'untouched')

    def test_parent_traversal_absolute_and_backslash_rejected(self):
        for name in ['../escape','/etc/example','safe/../../escape','safe\\escape']:
            with self.subTest(name=name):
                self.tar('mail-data.tar.gz',[(name,b'bad')])
                self.manifest()
                with self.assertRaises(ValueError):
                    bundle.verify(self.backup)

    def test_links_and_devices_rejected(self):
        for kind in [tarfile.SYMTYPE,tarfile.LNKTYPE,tarfile.CHRTYPE,tarfile.FIFOTYPE]:
            with self.subTest(kind=kind):
                item=tarfile.TarInfo('unsafe')
                item.type=kind
                item.linkname='/etc/example'
                self.tar('mail-data.tar.gz',[],item)
                self.manifest()
                with self.assertRaises(ValueError):
                    bundle.verify(self.backup)

    def test_duplicate_and_file_parent_conflict(self):
        for entries in [[('a',b'one'),('a',b'two')],[('a',b'one'),('a/b',b'two')]]:
            self.tar('mail-data.tar.gz',entries)
            self.manifest()
            with self.assertRaises(ValueError):
                bundle.verify(self.backup)

    def test_unsupported_version_refused(self):
        self.meta['versions']={'communityserver':'99.0','mysql':'8.4.0'}
        self.write_manifest()
        with self.assertRaises(ValueError):
            bundle.verify(self.backup)

    def test_missing_artifact_refused(self):
        del self.meta['artifacts']['mail-data.tar.gz']
        self.write_manifest()
        with self.assertRaises(ValueError):
            bundle.verify(self.backup)

    def test_unmarked_or_linked_destination_refused(self):
        with self.assertRaises(ValueError):
            bundle.unpack(self.backup,self.root/'unmarked',False)
        (self.root/'link').symlink_to(self.lab,target_is_directory=True)
        with self.assertRaises(ValueError):
            bundle.unpack(self.backup,self.root/'link'/'first',False)

    def test_readonly_verification_has_no_output_files(self):
        before=sorted(str(p) for p in self.root.rglob('*'))
        bundle.verify(self.backup)
        after=sorted(str(p) for p in self.root.rglob('*'))
        self.assertEqual(before,after)

if __name__=='__main__':
    unittest.main()
