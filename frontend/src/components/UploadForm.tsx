import { useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import api from '@/lib/api'
import toast from 'react-hot-toast'

interface SelectedFolder {
  id: string
  name: string
}

interface UploadFormProps {
  onJobCreated: () => void
  isGDriveConnected: boolean
}

function detectProvider(url: string): { name: string; value: string } | null {
  if (url.includes('cloud.mail.ru')) return { name: 'Mail.ru Cloud', value: 'mail_ru' }
  return null
}

declare global {
  interface Window {
    gapi: any
    google: any
    _pickerCallback?: (data: any) => void
  }
}

export default function UploadForm({ onJobCreated, isGDriveConnected }: UploadFormProps) {
  const [url, setUrl] = useState('')
  const [filename, setFilename] = useState('')
  const [folder, setFolder] = useState<SelectedFolder | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [pickerLoading, setPickerLoading] = useState(false)

  const provider = detectProvider(url)

  const openPicker = useCallback(async () => {
    setPickerLoading(true)
    try {
      
      const { data } = await api.get('/api/auth/google/picker-token')
      const accessToken = data.access_token

      
      await new Promise<void>((resolve) => {
        if (window.gapi) { resolve(); return }
        const script = document.createElement('script')
        script.src = 'https://apis.google.com/js/api.js'
        script.onload = () => resolve()
        document.body.appendChild(script)
      })

      await new Promise<void>((resolve) => {
        window.gapi.load('picker', { callback: resolve })
      })

      window._pickerCallback = (data: any) => {
        if (data.action === 'picked' && data.docs?.[0]) {
          const doc = data.docs[0]
          setFolder({ id: doc.id, name: doc.name })
        }
        delete window._pickerCallback
      }

      const view = new window.google.picker.DocsView(window.google.picker.ViewId.FOLDERS)
        .setSelectFolderEnabled(true)
        .setIncludeFolders(true)

      const picker = new window.google.picker.PickerBuilder()
        .addView(view)
        .setOAuthToken(accessToken)
        .setDeveloperKey('')  
        .setCallback(window._pickerCallback)
        .build()

      picker.setVisible(true)
    } catch (err: any) {
      if (err?.response?.status === 400) {
        toast.error('Please connect Google Drive first')
      } else {
        toast.error('Failed to open folder picker')
      }
    } finally {
      setPickerLoading(false)
    }
  }, [])

  async function handleSubmit() {
    if (!url || !folder || !provider) return
    setSubmitting(true)
    try {
      await api.post('/api/upload', {
        source_url: url,
        provider: provider.value,
        gdrive_folder_id: folder.id,
        gdrive_folder_name: folder.name,
        filename: filename.trim() || null,
      })
      toast.success('Transfer started!')
      setUrl('')
      setFilename('')
      setFolder(null)
      onJobCreated()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail || 'Failed to start transfer')
    } finally {
      setSubmitting(false)
    }
  }

  const canSubmit = !!url && !!folder && !!provider && isGDriveConnected && !submitting

  return (
    <Card className="mb-6">
      <CardHeader>
        <CardTitle>New Transfer</CardTitle>
        <CardDescription>Paste a public cloud link to transfer directly to your Google Drive</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Source URL</label>
          <div className="flex gap-2 items-center">
            <Input
              placeholder="https://cloud.mail.ru/public/..."
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              className="flex-1"
            />
            {provider && (
              <Badge variant="secondary" className="whitespace-nowrap">
                {provider.name}
              </Badge>
            )}
          </div>
          {url && !provider && (
            <p className="text-xs text-destructive">Unsupported provider. Currently only Mail.ru Cloud is supported.</p>
          )}
        </div>

        {}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">
            Filename <span className="text-muted-foreground font-normal">(optional — leave blank to use original)</span>
          </label>
          <Input
            placeholder="custom-name.zip"
            value={filename}
            onChange={(e) => setFilename(e.target.value)}
          />
        </div>

        {}
        <div className="space-y-2">
          <label className="text-sm font-medium text-foreground">Destination Folder</label>
          <div className="flex gap-2">
            <div className="flex-1 flex items-center gap-2 px-3 py-2 rounded-md border border-input bg-background text-sm min-h-10">
              {folder ? (
                <>
                  <span>📁</span>
                  <span className="text-foreground truncate">{folder.name}</span>
                </>
              ) : (
                <span className="text-muted-foreground">No folder selected</span>
              )}
            </div>
            <Button
              type="button"
              variant="outline"
              onClick={openPicker}
              disabled={!isGDriveConnected || pickerLoading}
            >
              {pickerLoading ? 'Loading...' : 'Choose Folder'}
            </Button>
          </div>
          {!isGDriveConnected && (
            <p className="text-xs text-muted-foreground">Connect Google Drive to select a folder</p>
          )}
        </div>

        <Button
          className="w-full"
          onClick={handleSubmit}
          disabled={!canSubmit}
        >
          {submitting ? 'Starting...' : '🚀 Start Transfer'}
        </Button>
      </CardContent>
    </Card>
  )
}