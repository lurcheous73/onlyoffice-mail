"""OO's key encoding must survive strict DER readers without changing numbers."""
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('dkim_keys',Path(__file__).parents[1]/'api/dkim_keys.py')
keys=importlib.util.module_from_spec(spec);spec.loader.exec_module(keys)


class OOKeys(unittest.TestCase):
    def fixture(self):
        # Same length/sign behaviour as OO CryptoUtil; no private key material.
        values=[b'\0',b'\x80\xff',b'\x01\0\x01',b'\x81',b'\x83',b'\x89',b'\x8b',b'\x8d',b'\x8f']
        body=b''.join(b'\x02\x81'+bytes([len(v)])+v for v in values)
        return b'\x30\x82'+len(body).to_bytes(2,'big')+body

    def test_nonminimal_lengths_and_unsigned_integers_become_der(self):
        data=keys.canonical_oo_pkcs1(self.fixture())
        expected=b'\x30\x25\x02\x01\0\x02\x03\0\x80\xff\x02\x03\x01\0\x01'+b''.join(b'\x02\x02\0'+bytes([v]) for v in (0x81,0x83,0x89,0x8b,0x8d,0x8f))
        self.assertEqual(data,expected)
        self.assertEqual(keys.canonical_oo_pkcs1(data),data)

    def test_truncation_extra_fields_and_indefinite_lengths_are_refused(self):
        original=self.fixture()
        for data in (original[:-1],original+b'x',b'\x30\x80'+original[4:]+b'\0\0',original.replace(b'\x02\x81\x01\x81',b'\x03\x81\x01\x81')):
            with self.assertRaises(ValueError):keys.canonical_oo_pkcs1(data)

    def test_wrong_version_and_oversize_are_refused(self):
        for data in (self.fixture().replace(b'\x02\x81\x01\0',b'\x02\x81\x01\x01'),b'x'*16385):
            with self.assertRaises(ValueError):keys.canonical_oo_pkcs1(data)


if __name__=='__main__':unittest.main()
