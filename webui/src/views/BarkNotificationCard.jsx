import React from 'react'

import { api } from '../api.js'
import { generateBarkEncryptionMaterial } from '../barkConfig.js'

export default function BarkNotificationCard({
  config, onPatch, renderEventOptions, MessageTemplateEditor, showToast, t,
}) {
  const encryption = config.encryption || {}
  const patchEncryption = patch => onPatch({
    encryption: { ...encryption, ...patch },
  })
  const test = async () => {
    try {
      await api.testBark(config)
      showToast(t('Test succeeded'))
    } catch (error) {
      showToast(error.message)
    }
  }
  const generate = () => {
    try {
      patchEncryption(generateBarkEncryptionMaterial())
      showToast(t('Bark encryption values generated locally'))
    } catch (error) {
      showToast(error.message)
    }
  }

  return <div className="card u-panel">
    <div className="u-card-head">
      <div><h2>Bark</h2><p>{t('Encrypted iOS push for incoming SMS.')}</p></div>
      <input type="checkbox" className="u-toggle" checked={!!config.enabled}
        onChange={event => onPatch({ enabled: event.target.checked })} />
    </div>

    <label>{t('Bark full push URL')}</label>
    <input type="password" autoComplete="new-password" value={config.push_url || ''}
      placeholder="https://api.day.app/…"
      onChange={event => onPatch({ push_url: event.target.value })} />
    <p className="u-note">{t('Copy the complete test URL from Bark, including its device key.')}</p>

    <label><input type="checkbox" className="u-toggle" checked={config.verify_tls !== false}
      onChange={event => onPatch({ verify_tls: event.target.checked })} />
      {t('Verify remote TLS certificate')}</label>

    <label><input type="checkbox" className="u-toggle" checked={encryption.enabled !== false}
      onChange={event => patchEncryption({ enabled: event.target.checked })} />
      {t('Encrypt Bark push content')}</label>
    {encryption.enabled !== false ? <>
      <p className="u-note">{t('Enter the identical AES-128-CBC key and IV in Bark Push Encryption. Values are generated locally in this browser.')}</p>
      <div className="u-form-grid">
        <div><label>{t('Encryption algorithm')}</label><input value="AES-128-CBC" disabled /></div>
        <div className="u-inline" style={{ alignItems: 'end' }}><button type="button" className="btn btn-ghost" onClick={generate}>{t('Generate key and IV')}</button></div>
      </div>
      <div className="u-form-grid">
        <div><label>{t('Encryption key (16 ASCII characters)')}</label>
          <input type="password" autoComplete="new-password" value={encryption.key || ''}
            onChange={event => patchEncryption({ key: event.target.value })} /></div>
        <div><label>{t('Encryption IV (16 ASCII characters)')}</label>
          <input type="password" autoComplete="new-password" value={encryption.iv || ''}
            onChange={event => patchEncryption({ iv: event.target.value })} /></div>
      </div>
    </> : <p className="u-error">{t('Plaintext Bark pushes expose SMS content to the Bark server and Apple Push Notification service.')}</p>}

    <div className="u-form-grid">
      <div><label>{t('Notification group')}</label><input value={config.group || ''}
        onChange={event => onPatch({ group: event.target.value })} /></div>
      <div><label>{t('Notification sound (optional)')}</label><input value={config.sound || ''}
        onChange={event => onPatch({ sound: event.target.value })} /></div>
    </div>
    <label>{t('Notification level')}</label>
    <select value={config.level || 'active'} onChange={event => onPatch({ level: event.target.value })}>
      <option value="active">active</option>
      <option value="timeSensitive">timeSensitive</option>
      <option value="critical">critical</option>
      <option value="passive">passive</option>
    </select>

    <MessageTemplateEditor channel="Bark" config={config}
      onChange={message_templates => onPatch({ message_templates })}
      onTest={async event => {
        try {
          await api.testBark({ ...config, _test_event: event })
          showToast(t('Test succeeded'))
        } catch (error) {
          showToast(error.message)
        }
      }} />
    {renderEventOptions(config)}
    <button type="button" className="btn btn-ghost" onClick={test}>{t('Test')}</button>
  </div>
}
