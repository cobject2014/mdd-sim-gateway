import test from 'node:test'
import assert from 'node:assert/strict'
import { selectableLines, linePresent } from '../src/simSelection.js'
const lines = [{id:'1'}, {id:'3'}]
const devices = [{instance_id:'1',present:true},{instance_id:'3',present:false}]
test('SMS history keeps unplugged and all-offline lines selectable', () => {
  assert.deepEqual(selectableLines(lines, [], devices, true), lines)
  assert.deepEqual(selectableLines(lines, [], [], true), lines)
  assert.equal(linePresent(lines[1], [], devices), false)
})
test('live-only selectors still exclude unplugged lines and accept modem or reader', () => {
  assert.deepEqual(selectableLines(lines, [], devices, false), [lines[0]])
  assert.equal(linePresent(lines[1], [{matched:'3',present:true}], []), true)
})
