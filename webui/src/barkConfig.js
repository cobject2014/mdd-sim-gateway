const ALPHABET = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'

function randomText(length, cryptoProvider) {
  const bytes = cryptoProvider.getRandomValues(new Uint8Array(length))
  return Array.from(bytes, value => ALPHABET[value % ALPHABET.length]).join('')
}

export function generateBarkEncryptionMaterial(cryptoProvider = globalThis.crypto) {
  if (!cryptoProvider?.getRandomValues) throw new Error('Secure random generation is unavailable')
  return { key: randomText(16, cryptoProvider), iv: randomText(16, cryptoProvider) }
}
