import assert from 'node:assert/strict'
import test from 'node:test'

import { generateBarkEncryptionMaterial } from '../src/barkConfig.js'

test('generates two independent 16-character ASCII values', () => {
  let seed = 0
  const cryptoProvider = { getRandomValues(bytes) {
    for (let i = 0; i < bytes.length; i += 1) bytes[i] = seed++
    return bytes
  } }
  const generated = generateBarkEncryptionMaterial(cryptoProvider)
  assert.equal(generated.key.length, 16)
  assert.equal(generated.iv.length, 16)
  assert.notEqual(generated.key, generated.iv)
  assert.match(generated.key + generated.iv, /^[A-Za-z0-9]+$/)
})

test('refuses to generate secrets without a secure random provider', () => {
  assert.throws(() => generateBarkEncryptionMaterial({}), /Secure random/)
})
