import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface Task {
  task_id: string
  status: string
  progress_pct: number
  bytes_transferred: number
  total_bytes: number | null
  error: string | null
  filename: string
  source_url: string
  provider: string
  gdrive_folder_name: string
  created_at: string
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

function StatusBadge({ status }: { status: string }) {
  const variants: Record<string, { variant: any; label: string }> = {
    PENDING:   { variant: 'secondary', label: '⏳ Pending' },
    RUNNING:   { variant: 'default',   label: '⚡ Running' },
    SUCCESS:   { variant: 'success',   label: '✓ Done' },
    FAILED:    { variant: 'destructive', label: '✗ Failed' },
    CANCELLED: { variant: 'warning',  label: '○ Cancelled' },
  }
  const cfg = variants[status] || { variant: 'secondary', label: status }
  return <Badge variant={cfg.variant}>{cfg.label}</Badge>
}

interface TaskListProps {
  tasks: Task[]
  onRefresh: () => void
}

export default function TaskList({ tasks, onRefresh }: TaskListProps) {
  async function cancelTask(taskId: string) {
    try {
      await api.post(`/api/tasks/${taskId}/cancel`)
      toast.success('Cancellation requested')
      setTimeout(onRefresh, 1000)
    } catch {
      toast.error('Failed to cancel task')
    }
  }

  if (tasks.length === 0) {
    return (
      <div className="text-center py-16 border border-border rounded-lg">
        <div className="text-4xl mb-3">📭</div>
        <p className="text-muted-foreground">No transfers yet. Start one above!</p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <div key={task.task_id} className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-start justify-between gap-3 mb-2">
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-medium text-foreground truncate max-w-xs">
                  {task.filename || 'Unknown file'}
                </span>
                <StatusBadge status={task.status} />
                {task.provider === 'mail_ru' && (
                  <Badge variant="outline" className="text-xs">Mail.ru</Badge>
                )}
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                → {task.gdrive_folder_name || 'Google Drive'}
                {task.created_at && (
                  <span className="ml-2">
                    {new Date(task.created_at).toLocaleString()}
                  </span>
                )}
              </div>
            </div>
            {(task.status === 'RUNNING' || task.status === 'PENDING') && (
              <Button
                variant="ghost"
                size="sm"
                className="text-xs text-destructive hover:text-destructive flex-shrink-0"
                onClick={() => cancelTask(task.task_id)}
              >
                Cancel
              </Button>
            )}
          </div>

          {}
          {task.status === 'RUNNING' && (
            <div className="mt-3">
              <div className="flex justify-between text-xs text-muted-foreground mb-1">
                <span>{task.progress_pct}%</span>
                <span>
                  {formatBytes(task.bytes_transferred)}
                  {task.total_bytes ? ` / ${formatBytes(task.total_bytes)}` : ''}
                </span>
              </div>
              <Progress value={task.progress_pct} className="h-2" />
            </div>
          )}

          {}
          {task.status === 'FAILED' && task.error && (
            <div className="mt-2 text-xs text-destructive bg-destructive/10 rounded px-3 py-2">
              {task.error}
            </div>
          )}

          {}
          {task.status === 'SUCCESS' && task.bytes_transferred > 0 && (
            <div className="mt-2 text-xs text-green-400">
              ✓ Transferred {formatBytes(task.bytes_transferred)}
            </div>
          )}
        </div>
      ))}
    </div>
  )
}