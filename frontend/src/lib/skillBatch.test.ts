import assert from 'node:assert/strict'
import test from 'node:test'

import { resolveBatchConfirmation, runSkillBatch } from './skillBatch.ts'

test('batch confirmation requires the same action twice', () => {
  const armed = resolveBatchConfirmation(null, 'enable', 'alpha')
  assert.deepEqual(armed, {
    confirmed: false,
    next: { action: 'enable', selectionKey: 'alpha' },
  })

  const confirmed = resolveBatchConfirmation(armed.next, 'enable', 'alpha')
  assert.deepEqual(confirmed, { confirmed: true, next: null })
})

test('switching batch actions replaces the pending confirmation', () => {
  const result = resolveBatchConfirmation(
    { action: 'delete', selectionKey: 'alpha' },
    'export',
    'alpha',
  )
  assert.deepEqual(result, {
    confirmed: false,
    next: { action: 'export', selectionKey: 'alpha' },
  })
})

test('changing the selected skills invalidates pending confirmation', () => {
  const result = resolveBatchConfirmation(
    { action: 'delete', selectionKey: 'alpha' },
    'delete',
    'alpha\nbeta',
  )
  assert.deepEqual(result, {
    confirmed: false,
    next: { action: 'delete', selectionKey: 'alpha\nbeta' },
  })
})

test('batch runner continues after failures and reports progress', async () => {
  const progress: Array<[number, number]> = []
  const result = await runSkillBatch(
    ['alpha', 'beta', 'gamma'],
    async item => {
      if (item === 'beta') throw new Error('cannot update beta')
    },
    state => progress.push([state.completed, state.total]),
  )

  assert.deepEqual(progress, [[0, 3], [1, 3], [2, 3], [3, 3]])
  assert.deepEqual(result.succeeded, ['alpha', 'gamma'])
  assert.deepEqual(result.failed, [{ item: 'beta', message: 'cannot update beta' }])
  assert.equal(result.completed, 3)
  assert.equal(result.total, 3)
})
