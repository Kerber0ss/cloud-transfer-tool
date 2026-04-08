import { useEffect, useState } from 'react'

interface TaskProgress {
  task_id: string
  status: string
  progress_pct: number
  bytes_transferred: number
  total_bytes: number | null
  error: string | null
  filename?: string
  provider?: string
  gdrive_folder_name?: string
  source_url?: string
  created_at?: string
}

export function useTaskProgress(taskId: string, isRunning: boolean) {
  const [progress, setProgress] = useState<TaskProgress | null>(null)

  useEffect(() => {
    if (!isRunning || !taskId) return

    const token = localStorage.getItem('cloud_transfer_token')
    if (!token) return

    const url = `/api/tasks/${taskId}/events?token=${encodeURIComponent(token)}`
    
    const eventSource = new EventSource(url)

    eventSource.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        setProgress(data)
      } catch {}
    }

    eventSource.onerror = () => {
      eventSource.close()
    }

    return () => eventSource.close()
  }, [taskId, isRunning])

  return progress
}