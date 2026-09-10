export const smsOnly = device => device?.sim_policy?.mode === 'sms_only'
const cap = (device, key) => device?.capabilities?.[key] || device?.[key] || {}
export const radioOff = device => device?.cellular?.radio_enabled === false || cap(device, 'flight').actual === 'on'
export const radioLabel = device => device?.present === false ? 'Unavailable' : radioOff(device) ? 'Cellular radio off' : device?.cellular?.radio_enabled === true || cap(device, 'flight').actual === 'off' ? 'Cellular radio on' : 'Waiting for radio status'
export const cellularRegistered = device => device?.present !== false && device?.sim?.present !== false && device?.device_type !== 'reader' && !radioOff(device) && ['home', 'roaming', 'registered', '1', '5'].includes(String(device?.cellular?.registration || '').toLowerCase())
export const vowifiRegistered = device => device?.present !== false && cap(device, 'vowifi').actual === 'on'
export const smsReceiveReady = device => device?.present !== false && device?.sim?.present !== false && (device?.sms?.receive_ready ?? (cellularRegistered(device) || vowifiRegistered(device)))
export function deviceSummary(device) {
  if (device?.present === false) return {state:'off', label:'Device not connected'}
  if (device?.sim?.present === false) return {state:'off', label:'No SIM inserted'}
  const cellular = cellularRegistered(device), vowifi = vowifiRegistered(device)
  if (cellular || vowifi) return {state:'on', label:cellular && vowifi ? 'Both networks registered' : cellular ? 'Cellular registered' : 'VoWiFi registered'}
  if (device?.device_type !== 'reader') return {state:radioOff(device) ? 'off' : 'starting', label:radioOff(device) ? 'Cellular radio off' : 'Waiting for cellular registration'}
  return {state:cap(device,'vowifi').desired ? 'starting' : 'off', label:cap(device,'vowifi').desired ? 'Waiting for VoWiFi registration' : 'VoWiFi not enabled'}
}
export function mobileDataAddress(device) {
  if (!cap(device, 'cellular').desired && !device?.cellular?.data_active) return 'Mobile data disabled'
  return device?.cellular?.ip && device.cellular.ip !== '--' ? device.cellular.ip : 'Waiting'
}
