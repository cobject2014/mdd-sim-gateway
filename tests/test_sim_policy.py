import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from control.app import sim_policy
from host.mdd_orchestrator import Orchestrator

class SimPolicyTests(unittest.TestCase):
    def test_persist_mask_and_normal(self):
        with tempfile.TemporaryDirectory() as root, patch.object(sim_policy, 'PATH', str(Path(root)/'policies.json')):
            sim_policy.save('454001234563058', 'sms_only')
            self.assertTrue(sim_policy.protected('454001234563058'))
            self.assertFalse(sim_policy.protected('454009999999999'))
            self.assertEqual(sim_policy.view('454001234563058')['imsi_masked'], '45400******3058')
            sim_policy.save('454001234563058', 'normal')
            self.assertFalse(sim_policy.protected('454001234563058'))
    def test_live_identity_policy_does_not_transfer_to_replacement(self):
        wanted = dict(cellular_enabled=True, flight_mode=True, vowifi_enabled=True)
        policies = {'454001234563058': {'mode':'sms_only'}}
        self.assertEqual(Orchestrator.sim_policy_intent(wanted, '454001234563058', policies),
                         dict(cellular_enabled=False, flight_mode=False, vowifi_enabled=False))
        self.assertEqual(Orchestrator.sim_policy_intent(wanted, '454009999999999', policies), wanted)
        self.assertFalse(Orchestrator.sim_policy_intent(wanted, '', policies)['cellular_enabled'])

class HostPolicyTests(unittest.TestCase):
    def test_live_sim_enforced_before_data_activation(self):
        from unittest.mock import Mock
        host = Orchestrator.__new__(Orchestrator)
        host.root = Path('/unused')
        host._serial_mode = False
        host.dry_run = False
        host.radio_states = {}
        host.cellular_states = {}
        host.modemmanager_modem_for_tty = Mock(return_value='0')
        host.modem_snapshot = Mock(return_value={'available':True, 'radio_enabled':True,
                                                'sim_imsi':'454001234563058'})
        host.ensure_modem_data = Mock()
        host.disconnect_modem_data = Mock()
        wanted = {'m':dict(cellular_enabled=True, vowifi_enabled=True, flight_mode=True)}
        with patch('host.mdd_orchestrator.read_json', return_value={'policies': {'454001234563058': {'mode':'sms_only'}}}):
            host.apply_device_radios([{'id':'m','tty':'/dev/ttyUSB2'}], wanted, True)
        host.ensure_modem_data.assert_not_called()
        host.disconnect_modem_data.assert_called_once()
        self.assertEqual(wanted['m'], dict(cellular_enabled=False,vowifi_enabled=False,flight_mode=False))

class PolicyApiTests(unittest.IsolatedAsyncioTestCase):
    async def test_sms_send_not_blocked_by_policy(self):
        from control.app import main
        from unittest.mock import AsyncMock
        with patch.object(main.sim_policy, 'protected', return_value=True), patch.object(main, '_send_sms_cellular', new=AsyncMock(return_value={'ok':True})) as send:
            self.assertTrue((await main.send_sms_on_line('3', '12345', 'test', 'cellular'))['ok'])
            send.assert_awaited_once()

    async def test_save_refuses_missing_live_imsi(self):
        from control.app import main
        from fastapi import HTTPException
        with patch.object(main, '_live_device_imsi', return_value=''), patch.object(main.sim_policy, 'save') as save:
            with self.assertRaises(HTTPException):
                await main.api_device_sim_policy_save('m', {'mode':'sms_only'})
            save.assert_not_called()

class BackendDiscoveryTests(unittest.TestCase):
    def test_policy_needs_mm_even_when_default_radio_is_off(self):
        host = Orchestrator.__new__(Orchestrator)
        host.root = Path('/unused')
        host._degraded = {}
        plan = Orchestrator.capability_plan({'new': {'cellular_enabled':False, 'flight_mode':True, 'vowifi_enabled':False}})
        with patch('host.mdd_orchestrator.read_json', return_value={'policies':{'454001234563058': {'mode':'sms_only'}}}):
            self.assertTrue(host.cellular_backend_needed(plan, {'new'}, {}))
            self.assertFalse(host.cellular_backend_needed(plan, {'new'}, {'modem_backend':'serial'}))

    def test_missing_mm_drops_previous_sim_identity(self):
        from unittest.mock import Mock
        host = Orchestrator.__new__(Orchestrator)
        host.root = Path('/unused')
        host._serial_mode = False
        host.dry_run = False
        host.radio_states = {'m':True}
        host.cellular_states = {'m':{'sim_imsi':'454001234563058'}}
        host.modemmanager_modem_for_tty = Mock(return_value=None)
        wanted = {'m':dict(cellular_enabled=True,vowifi_enabled=True,flight_mode=False)}
        with patch('host.mdd_orchestrator.read_json', return_value={'policies':{'454001234563058':{'mode':'sms_only'}}}):
            host.apply_device_radios([{'id':'m','tty':'/dev/ttyUSB2'}], wanted, True)
        self.assertEqual(host.cellular_states['m'], {})
        self.assertFalse(wanted['m']['cellular_enabled'])

    def test_removed_policy_reads_safe_base_before_connect(self):
        from unittest.mock import Mock
        with tempfile.TemporaryDirectory() as root:
            host = Orchestrator.__new__(Orchestrator)
            host.root = Path(root)
            (host.root/'sim-policies.json').write_text('{}')
            host._serial_mode = False
            host.dry_run = False
            host.radio_states = {}
            host.cellular_states = {}
            host.modemmanager_modem_for_tty = Mock(return_value='0')
            host.modem_snapshot = Mock(return_value={'available':True,'radio_enabled':True,'sim_imsi':'454001234563058'})
            host.ensure_modem_data = Mock()
            host.disconnect_modem_data = Mock()
            stale = {'m':dict(cellular_enabled=True,vowifi_enabled=False,flight_mode=False)}
            safe = {'devices':{'m':dict(cellular_enabled=False,vowifi_enabled=False,flight_mode=False)}}
            with patch('host.mdd_orchestrator.read_json', side_effect=[{'policies':{}},safe]):
                host.apply_device_radios([{'id':'m','tty':'/dev/ttyUSB2'}], stale, True)
            host.ensure_modem_data.assert_not_called()

    def test_live_binding_rejects_sim_swap(self):
        from control.app import main
        device = {'devices':{'m':{'mm_object':'/org/freedesktop/ModemManager1/Modem/0'}}}
        replies = [{'modem':{'generic':{'sim':'/org/freedesktop/ModemManager1/SIM/0'}}},
                   {'sim':{'properties':{'imsi':'454009999999999'}}}]
        with patch.object(main.device_state,'status',return_value=device), patch.object(main.cellular_sms,'_run_json',side_effect=replies):
            self.assertFalse(main._verify_device_imsi('m','454001234563058'))
