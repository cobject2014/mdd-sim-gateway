import assert from 'node:assert/strict'
import test from 'node:test'

import { lineCapabilityState } from '../src/deviceStatus.js'

test('a healthy line stays stopping while its desired state is off', () => {
  assert.equal(lineCapabilityState({ state: 'OK' }, false), 'stopping')
})
