export function lineCapabilityState(status, desired = true) {
  const state = String(status?.state || '').toUpperCase()
  if (state === 'OK') return desired ? 'on' : 'stopping'
  if (state === 'STOPPED') return desired ? 'degraded' : 'off'
  if (['ERROR', 'NO_CARD', 'PIN_PROBLEM'].includes(state)) return 'error'
  return desired ? 'starting' : 'off'
}
