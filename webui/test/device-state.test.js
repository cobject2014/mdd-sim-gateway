import test from 'node:test'
import assert from 'node:assert/strict'
import { deviceSummary, smsOnly, smsReceiveReady, mobileDataAddress, radioLabel } from '../src/deviceState.js'
const modem = { present: true, device_type: 'modem', sim: { present: true }, cellular: { registration: 'roaming', desired: false }, capabilities: { flight: { desired: false, actual: 'off' }, vowifi: { desired: false, actual: 'off' } } }
test('registered modem remains online with mobile data and VoWiFi off', () => {
  assert.equal(deviceSummary(modem).label, 'Cellular registered')
  assert.equal(smsReceiveReady(modem), true)
  assert.equal(mobileDataAddress(modem), 'Mobile data disabled')
})
test('disconnected and radio-off devices cannot inherit registration', () => {
  assert.equal(deviceSummary({...modem, present: false}).label, 'Device not connected')
  assert.equal(smsReceiveReady({...modem, present: false}), false)
  assert.equal(deviceSummary({...modem, capabilities: {flight: {actual:'on'}}}).label, 'Cellular radio off')
})
test('reader and dual registration are distinguished', () => {
  assert.equal(deviceSummary({...modem, capabilities:{vowifi:{actual:'on'}}}).label, 'Both networks registered')
  assert.equal(deviceSummary({present:true, device_type:'reader', capabilities:{vowifi:{actual:'off'}}}).label, 'VoWiFi not enabled')
})
test('SMS-only binds explicitly and unregistered SIM is not receive-ready', () => {
  assert.equal(smsOnly({sim_policy:{mode:'sms_only'}}), true)
  assert.equal(smsOnly(modem), false)
  assert.equal(smsReceiveReady({...modem, cellular:{registration:'searching'}}), false)
})

test('missing radio status is not advertised as radio on', () => {
  assert.equal(radioLabel({present:true, device_type:'modem'}), 'Waiting for radio status')
  assert.equal(smsReceiveReady({...modem, present:false, sms:{receive_ready:true}}), false)
})
