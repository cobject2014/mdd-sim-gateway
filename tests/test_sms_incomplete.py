import json
import unittest
from control.app.cellular_sms import Scanner
from tests.test_cellular_sms import Result

class IncompleteSmsTests(unittest.TestCase):
    def scan(self, state, text, raw='s ""'):
        path = '/org/freedesktop/ModemManager1/SMS/19'
        def runner(args, **kwargs):
            if '--messaging-list-sms' in args:
                return Result(json.dumps({'modem.messaging.sms': [path]}))
            if args[0] == 'busctl': return Result(raw)
            return Result(json.dumps({'sms': {'content': {'number': '#ClubSim', 'text': text},
                'properties': {'state': state, 'pdu-type': 'deliver'}}}))
        scanner = Scanner(runner=runner, clock=lambda: 1)
        scanner._topology = [('modem', 'card')]
        scanner._topology_expires = 100
        return scanner, [{'id': '3', 'iccid': 'card'}]

    def test_receiving_is_not_imported_or_cached(self):
        for text in ['--', 'partial']:
            scanner, lines = self.scan('receiving', text)
            self.assertEqual(scanner.discover(lines), [])
            self.assertFalse(scanner._details)

    def test_complete_sms_is_imported(self):
        scanner, lines = self.scan('received', 'complete')
        self.assertEqual(scanner.discover(lines)[0]['body'], 'complete')

    def test_empty_placeholder_is_not_imported(self):
        scanner, lines = self.scan('received', '--')
        self.assertEqual(scanner.discover(lines), [])

    def test_literal_dashes_are_preserved(self):
        scanner, lines = self.scan('received', '--', 's "--"')
        self.assertEqual(scanner.discover(lines)[0]['body'], '--')

    def test_next_poll_retries_incomplete_object(self):
        scanner, lines = self.scan('receiving', '--')
        self.assertEqual(scanner.discover(lines), [])
        complete, _ = self.scan('received', 'complete')
        scanner.runner = complete.runner
        self.assertEqual(scanner.discover(lines)[0]['body'], 'complete')
