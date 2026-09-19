import hashlib
import json
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
        return store.ingest_message(instance, 'in', '#ClubSim', body, sent_ts=ts, transport='cellular', legacy_fingerprint=fingerprint)

    def test_renumbered_sms_does_not_emit_record_for_bark(self):
        self.assertIsNotNone(self.add('path19'))
        self.assertIsNone(self.add('path39'))

    def test_existing_legacy_row_is_adopted_without_notification(self):
        with store._conn() as c:
            c.execute("insert into messages(instance,direction,peer,body,status,ts,transport) values('3','in','#ClubSim','hello','ok',1700000000,'cellular')")
        store.init()  # rollback-created rows are adopted on restart
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

    def test_deleted_fork_message_stays_deleted_after_object_renumber_and_migration(self):
        raw = json.dumps(['3', '#ClubSim', 'hello', 1700000000, 'cellular'],
                         ensure_ascii=False, separators=(',', ':'))
        marker = 'cellular-in-v2:' + hashlib.sha256(raw.encode()).hexdigest()
        # An older build may write to its table again after a rollback.
        with store._conn() as c:
            c.execute('CREATE TABLE message_imports (fingerprint TEXT PRIMARY KEY, instance TEXT NOT NULL, imported_ts INTEGER NOT NULL)')
            c.execute('INSERT INTO message_imports VALUES (?, ?, ?)', (marker, '3', 1700000001))
        store.init()
        self.assertIsNone(self.add('new-path'))
        store.init()
        self.assertIsNone(self.add('another-new-path'))
        self.assertEqual(store.list_threads('3'), [])

    def test_own_send_is_not_claimed_in_a_new_daemon_generation(self):
        mid = store.begin_local_modem_sms('3', '6700', 'BAL', daemon_epoch='old')
        store.bind_local_modem_sms(mid, '/modem/0', '/sms/7')
        self.assertTrue(store.owns_local_modem_sms('3', '/modem/0', '/sms/7', '6700', 'BAL', daemon_epoch='old'))
        self.assertFalse(store.owns_local_modem_sms('3', '/modem/0', '/sms/7', '6700', 'BAL', daemon_epoch='new'))

    def test_external_undated_sends_have_object_identity(self):
        def receive(identity):
            return store.ingest_message('3', 'out', '6700', 'BAL', transport='cellular', identity=identity)
        self.assertIsNotNone(receive('old:/sms/7'))
        self.assertIsNone(receive('old:/sms/7'))
        self.assertIsNotNone(receive('old:/sms/8'))
        self.assertIsNotNone(receive('new:/sms/7'))

    def test_definite_create_failure_cannot_claim_an_external_message(self):
        mid = store.begin_local_modem_sms('3', '6700', 'BAL', daemon_epoch='epoch')
        store.abandon_local_modem_sms(mid)
        self.assertFalse(store.owns_local_modem_sms('3', '/modem/0', '/sms/7', '6700', 'BAL', daemon_epoch='epoch'))
