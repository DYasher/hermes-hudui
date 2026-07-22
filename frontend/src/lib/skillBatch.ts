export type SkillBatchAction = 'enable' | 'disable' | 'export' | 'delete' | 'move'

export type PendingBatchConfirmation = {
  action: SkillBatchAction
  selectionKey: string
}

export type BatchConfirmation = {
  confirmed: boolean
  next: PendingBatchConfirmation | null
}

export type SkillBatchProgress = {
  completed: number
  total: number
}

export type SkillBatchFailure<T> = {
  item: T
  message: string
}

export type SkillBatchResult<T> = SkillBatchProgress & {
  succeeded: T[]
  failed: Array<SkillBatchFailure<T>>
}

export function resolveBatchConfirmation(
  current: PendingBatchConfirmation | null,
  requested: SkillBatchAction,
  selectionKey: string,
): BatchConfirmation {
  if (current?.action === requested && current.selectionKey === selectionKey) {
    return { confirmed: true, next: null }
  }
  return {
    confirmed: false,
    next: { action: requested, selectionKey },
  }
}

export async function runSkillBatch<T>(
  items: T[],
  operation: (item: T) => Promise<void>,
  onProgress?: (progress: SkillBatchProgress) => void,
): Promise<SkillBatchResult<T>> {
  const result: SkillBatchResult<T> = {
    completed: 0,
    total: items.length,
    succeeded: [],
    failed: [],
  }
  onProgress?.({ completed: 0, total: items.length })

  for (const item of items) {
    try {
      await operation(item)
      result.succeeded.push(item)
    } catch (error) {
      result.failed.push({
        item,
        message: error instanceof Error ? error.message : String(error),
      })
    }
    result.completed += 1
    onProgress?.({ completed: result.completed, total: result.total })
  }

  return result
}
