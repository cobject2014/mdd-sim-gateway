"""Explicit IMSI-bound service policy. Raw identities remain in the private data directory."""
import os
import re
from . import device_state

PATH = os.path.join(device_state.ROOT, 'sim-policies.json')

def normalize(imsi):
    value = str(imsi or '').strip()
    return value if re.fullmatch(r'\d{14,15}', value) else ''

def policies():
    return device_state._read(PATH, {}).get('policies', {})

def protected(imsi):
    return (policies().get(normalize(imsi)) or {}).get('mode') == 'sms_only'

def view(imsi):
    imsi = normalize(imsi)
    return {'mode': 'sms_only' if protected(imsi) else 'normal',
            'imsi_masked': imsi[:5] + '*' * (len(imsi)-9) + imsi[-4:] if imsi else '',
            'bound': bool(imsi)}

def save(imsi, mode):
    imsi = normalize(imsi)
    if not imsi or mode not in {'normal', 'sms_only'}:
        raise ValueError('A live IMSI and valid mode are required')
    records = policies()
    if mode == 'normal':
        records.pop(imsi, None)
    else:
        records[imsi] = {'mode': mode}
    device_state._write(PATH, {'policies': records})
    os.chmod(PATH, 0o600)
    return view(imsi)
