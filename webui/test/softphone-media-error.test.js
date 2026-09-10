import assert from 'node:assert/strict'
import test from 'node:test'

import * as softphone from '../src/softphone.js'

test('microphoneErrorMessage classifies browser media failures for the UI', () => {
  assert.equal(typeof softphone.microphoneErrorMessage, 'function')

  const cases = [
    ['NotAllowedError', 'Microphone permission is blocked. Allow microphone access for this site in your browser settings, reload the page, and try again.'],
    ['SecurityError', 'Microphone permission is blocked. Allow microphone access for this site in your browser settings, reload the page, and try again.'],
    ['NotFoundError', 'No microphone was found. Connect or enable an audio input device, then try again.'],
    ['DevicesNotFoundError', 'No microphone was found. Connect or enable an audio input device, then try again.'],
    ['NotReadableError', 'The microphone is unavailable. Close other apps using it and check your system microphone permissions, then try again.'],
    ['TrackStartError', 'The microphone is unavailable. Close other apps using it and check your system microphone permissions, then try again.'],
    ['UnknownError', 'Could not start the microphone. Check your browser and system microphone settings, then try again.'],
  ]

  for (const [name, expected] of cases) {
    assert.equal(softphone.microphoneErrorMessage({ name }), expected, name)
  }
})

test('Softphone emits a mediafailed event when JsSIP cannot acquire the microphone', () => {
  const handlers = new Map()
  const events = []
  const session = {
    direction: 'outgoing',
    on: (type, handler) => handlers.set(type, handler),
  }
  const phone = new softphone.Softphone((type, data) => events.push({ type, data }))

  phone.handleSession({ session })

  assert.equal(typeof handlers.get('getusermediafailed'), 'function')
  handlers.get('getusermediafailed')({ name: 'NotAllowedError' })
  assert.deepEqual(events, [{
    type: 'mediafailed',
    data: {
      name: 'NotAllowedError',
      message: 'Microphone permission is blocked. Allow microphone access for this site in your browser settings, reload the page, and try again.',
    },
  }])
})
