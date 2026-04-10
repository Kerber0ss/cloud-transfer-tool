import { useEffect, useState, useCallback } from 'react'
import api from '@/lib/api'
import { getToken } from '@/lib/auth'
import toast from 'react-hot-toast'

interface GoogleDriveAccount {
  connected: boolean
  email?: string | null
  name?: string | null
  expired?: boolean | null
}

export function useGoogleDrive() {
  const [account, setAccount] = useState<GoogleDriveAccount>({ connected: false })
  const [loading, setLoading] = useState(true)

  const checkStatus = useCallback(async () => {
    try {
      const response = await api.get('/api/auth/google/status')
      setAccount(response.data)
      if (response.data.expired) {
        toast.error('Google Drive session expired. Please reconnect.', { id: 'gdrive-expired' })
      }
    } catch {
      setAccount({ connected: false })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    checkStatus()

    const params = new URLSearchParams(window.location.search)
    if (params.get('google_connected') === 'true') {
      window.history.replaceState({}, '', window.location.pathname)
      checkStatus()
    }

    const handleFocus = () => checkStatus()
    window.addEventListener('focus', handleFocus)
    return () => window.removeEventListener('focus', handleFocus)
  }, [checkStatus])

  const connect = useCallback(() => {
    const token = getToken()
    window.location.href = `/api/auth/google?token=${token}`
  }, [])

  const disconnect = useCallback(async () => {
    try {
      await api.delete('/api/auth/google/disconnect')
      setAccount({ connected: false })
    } catch {
    }
  }, [])

  return { isConnected: account.connected, account, loading, connect, disconnect }
}
