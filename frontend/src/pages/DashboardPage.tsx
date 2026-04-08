import { useQuery } from '@tanstack/react-query'
import GoogleDriveConnect from '@/components/GoogleDriveConnect'
import UploadForm from '@/components/UploadForm'
import TaskList from '@/components/TaskList'
import StatsSummary from '@/components/StatsSummary'
import { logout } from '@/lib/auth'
import { Button } from '@/components/ui/button'
import { useGoogleDrive } from '@/hooks/useGoogleDrive'
import api from '@/lib/api'

async function fetchTasks() {
  const { data } = await api.get('/api/tasks/')
  return data
}

export default function DashboardPage() {
  const { isConnected } = useGoogleDrive()
  
  const { data: tasks = [], refetch } = useQuery({
    queryKey: ['tasks'],
    queryFn: fetchTasks,
    refetchInterval: 3000, 
  })

  
  const hasRunning = tasks.some((t: any) => t.status === 'RUNNING' || t.status === 'PENDING')

  return (
    <div className="min-h-screen bg-background flex">
      <aside className="w-64 min-h-screen bg-card border-r border-border flex flex-col flex-shrink-0">
        <div className="p-5 border-b border-border">
          <div className="text-xl font-bold text-foreground">☁️ Cloud Transfer</div>
          <div className="text-xs text-muted-foreground mt-1">File Transfer Dashboard</div>
        </div>

        <nav className="p-4 flex-1">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider mb-3">
            Navigation
          </div>
          <a href="/" className="flex items-center gap-2 px-3 py-2 rounded-md bg-accent text-accent-foreground text-sm font-medium mb-1">
            <span>📁</span> Dashboard
          </a>
        </nav>

        <div className="p-4 border-t border-border space-y-3">
          <div className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            Google Drive
          </div>
          <GoogleDriveConnect />
          <Button
            variant="ghost"
            size="sm"
            className="w-full text-xs text-muted-foreground"
            onClick={logout}
          >
            Sign Out
          </Button>
        </div>
      </aside>

      <main className="flex-1 p-6 overflow-auto">
        <div className="max-w-4xl">
          <h1 className="text-2xl font-bold text-foreground mb-1">Dashboard</h1>
          <p className="text-muted-foreground mb-6 text-sm">
            Transfer files from cloud services directly to your Google Drive
          </p>

          <StatsSummary tasks={tasks} />

          <UploadForm
            onJobCreated={() => refetch()}
            isGDriveConnected={isConnected}
          />

          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-lg font-semibold text-foreground">Transfer History</h2>
              <div className="flex items-center gap-3">
                {hasRunning && (
                  <span className="text-xs text-blue-400 animate-pulse">● Live updating</span>
                )}
              </div>
            </div>
            <TaskList tasks={tasks} onRefresh={() => refetch()} />
          </div>
        </div>
      </main>
    </div>
  )
}
