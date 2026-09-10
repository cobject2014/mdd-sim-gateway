import React from 'react'
import { smsOnly } from '../deviceState.js'

// A VoWiFi draft is not a prerequisite for cellular SMS. Do not mount its editor
// (including its reader polling and missing-SMSC prompts) for an SMS-only SIM.
export default function SimModeContent({ device, t, children }) {
  if (!smsOnly(device)) return children
  const row = (label, value) => React.createElement('div', { className: 'u-detail', key: label },
    React.createElement('span', null, t(label)), React.createElement('b', null, value))
  return React.createElement('section', { className: 'u-panel' },
    React.createElement('h3', null, t('SMS only')),
    React.createElement('div', { className: 'u-details' },
      row('SIM', device.sim?.name || t('SIM detected')),
      row('Phone number', device.sim?.number || device.number || t('Number unavailable'))),
    React.createElement('p', { className: 'u-note' }, t('SMS sending and receiving use the cellular network. VoWiFi is not enabled in this mode; its draft configuration is not required. Select normal mode above to edit VoWiFi settings.')))
}
