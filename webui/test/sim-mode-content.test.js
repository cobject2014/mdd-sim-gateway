import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import SimModeContent from '../src/views/SimModeContent.js'
const render = mode => renderToStaticMarkup(React.createElement(SimModeContent, {
  device: { sim_policy: {mode}, sim: {name:'Test SIM',number:'12345'} }, t: value => value,
}, React.createElement('div', null, 'VoWiFi draft: missing SMSC')))
test('SMS mode omits the stopped VoWiFi draft and keeps SIM identity', () => {
  const html = render('sms_only')
  assert.doesNotMatch(html, /missing SMSC/)
  assert.match(html, /Test SIM/)
  assert.match(html, /12345/)
  assert.match(html, /SMS sending and receiving/)
})
test('normal mode retains the existing VoWiFi editor', () => {
  assert.match(render('normal'), /VoWiFi draft: missing SMSC/)
})
