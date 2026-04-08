interface Task {
  status: string
  bytes_transferred: number
}

interface StatsSummaryProps {
  tasks: Task[]
}

function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

export default function StatsSummary({ tasks }: StatsSummaryProps) {
  const total = tasks.length
  const success = tasks.filter(t => t.status === 'SUCCESS').length
  const running = tasks.filter(t => t.status === 'RUNNING').length
  const totalBytes = tasks.reduce((sum, t) => sum + (t.bytes_transferred || 0), 0)

  const stats = [
    { label: 'Total Transfers', value: total, color: 'text-foreground' },
    { label: 'Completed', value: success, color: 'text-green-400' },
    { label: 'In Progress', value: running, color: 'text-blue-400' },
    { label: 'Data Transferred', value: formatBytes(totalBytes), color: 'text-purple-400' },
  ]

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
      {stats.map((stat) => (
        <div key={stat.label} className="bg-card border border-border rounded-lg p-4">
          <div className={`text-2xl font-bold ${stat.color}`}>{stat.value}</div>
          <div className="text-xs text-muted-foreground mt-1">{stat.label}</div>
        </div>
      ))}
    </div>
  )
}