import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from control.app import store

class SmsImportIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        p = Path(self.temp.name)
        self.settings = patch.multiple(store, DATA_DIR=str(p), DB_PATH=str(p/'db'), PREVIOUS_DB_PATH=str(p/'old'))
        self.settings.start()
        self.addCleanup(self.settings.stop)
        store.init()

    def add(self, fingerprint, ts=1700000000, instance='3', body='hello'):
        return store.add_imported_message(fingerprint, instance, 'in', '#ClubSim', body, ts, 'cellular')

    def test_renumbered_sms_does_not_emit_record_for_bark(self):
        self.assertIsNotNone(self.add('path19'))
        self.assertIsNone(self.add('path39'))

    def test_existing_legacy_row_is_adopted_without_notification(self):
        with store._conn() as c:
            c.execute("insert into messages(instance,direction,peer,body,status,ts,transport) values('3','in','#ClubSim','hello','ok',1700000000,'cellular')")
        self.assertIsNone(self.add('new-path'))

    def test_identity_survives_history_deletion_and_restart(self):
        self.add('path19')
        with store._conn() as c: c.execute('delete from messages')
        store.init()
        self.assertIsNone(self.add('path39'))

    def test_different_timestamp_sim_and_body_remain_new(self):
        self.add('first')
        self.assertIsNotNone(self.add('second', ts=1700000001))
        self.assertIsNotNone(self.add('third', instance='4'))
        self.assertIsNotNone(self.add('fourth', body='different'))

    def test_missing_timestamp_does_not_merge_identical_messages(self):
        self.assertIsNotNone(self.add('first', ts=0))
        self.assertIsNotNone(self.add('second', ts=0))
