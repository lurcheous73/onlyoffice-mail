"""Offline archive integrity and mapping guards; no service is contacted."""
import datetime
from decimal import Decimal
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0,str(Path(__file__).parents[1]/'migration'))
spec=importlib.util.spec_from_file_location('records',Path(__file__).parents[1]/'migration'/'backend_records.py')
records=importlib.util.module_from_spec(spec);spec.loader.exec_module(records)


class BackendRecords(unittest.TestCase):
    def test_lossless_sql_scalars_including_binary_and_microseconds(self):
        row={'bytes':b'\x00\xffprivate\r\n','null':None,'number':12345678901234567890,'amount':Decimal('123456789.123456'),'time':datetime.datetime(2001,2,3,4,5,6,123456),'date':datetime.date(2001,2,3),'duration':datetime.timedelta(days=-1,microseconds=123),'unicode':'café 日本語','float':1.25,'zero_date':'0000-00-00 00:00:00'}
        self.assertEqual(records.decode(records.encode(row)),row)
        with self.assertRaises(ValueError):records.encode({'bad':math.nan})

    def test_unsafe_storage_and_unsupported_policies_are_rejected(self):
        with self.assertRaises(ValueError):records.validate_core('domain',{'domain':'example.invalid','backupmx':1})
        with self.assertRaises(ValueError):records.validate_core('domain',{'domain':'example.invalid','settings':'unknown legacy policy'})
        with self.assertRaises(ValueError):records.validate_core('alias',{'address':'@example.invalid','domain':'example.invalid','goto':'user@example.invalid'})
        row={'username':'user@example.invalid','domain':'example.invalid','local_part':'user','storagebasedirectory':'/var/vmail','storagenode':'vmail1','maildir':'../../escape','password':'$1$synthetic'}
        with self.assertRaises(ValueError):records.validate_core('mailbox',row)

    def archive(self,path):
        payload=records.encode({'id':1,'binary':b'\x00\xff','at':datetime.datetime(2026,1,2,3,4,5,123456)})
        with sqlite3.connect(path) as db:
            db.executescript('CREATE TABLE metadata(key TEXT,value TEXT);CREATE TABLE tables(name TEXT,row_count INTEGER,rows_sha256 TEXT);CREATE TABLE records(table_name TEXT,ordinal INTEGER,payload TEXT,sha256 TEXT);')
            db.executemany('INSERT INTO metadata VALUES (?,?)',[('format','1'),('complete','true')])
            db.execute('INSERT INTO records VALUES (?,?,?,?)',('legacy_history',0,payload,hashlib.sha256(payload.encode()).hexdigest()))
            count,digest=records.hash_rows(db,'legacy_history');db.execute('INSERT INTO tables VALUES (?,?,?)',('legacy_history',count,digest))

    def test_tampered_record_and_missing_row_are_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'archive.sqlite';self.archive(path)
            db=records.archive_open(path);db.close()
            with sqlite3.connect(path) as db:db.execute("UPDATE records SET payload='{}'")
            with self.assertRaises(ValueError):records.archive_open(path)
            with sqlite3.connect(path) as db:db.execute('DELETE FROM records')
            with self.assertRaises(ValueError):records.archive_open(path)

    def test_archive_ddl_is_data_and_identifiers_cannot_inject_sql(self):
        for value in ('mailbox; DROP DATABASE onlyoffice','`mailbox`','../mailbox'):
            with self.assertRaises(ValueError):records.identifier(value)
        self.assertEqual(records.identifier('enablelib-storage'),'`enablelib-storage`')
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp).resolve()/'archive.sqlite';self.archive(path)
            with sqlite3.connect(path) as db:
                db.execute('ALTER TABLE tables ADD COLUMN ddl TEXT');db.execute("UPDATE tables SET ddl='DROP DATABASE onlyoffice;'")
            db=records.archive_open(path)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM records').fetchone()[0],1);db.close()


if __name__=='__main__':unittest.main()
