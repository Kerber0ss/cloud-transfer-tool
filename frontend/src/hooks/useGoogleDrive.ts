import { useEffect, useState, useCallback } from 'react'
import api from '@/lib/api'

interface GoogleDriveAccount {
  connected: boolean
  email?: string | null
  name?: string | null
}

export function useGoogleDrive() {
  const [account, setAccount] = useState<GoogleDriveAccount>({ connected: false })
  const [loading, setLoading] = useState(true)

  const checkStatus = useCallback(async () => {
    try {
      const response = await api.get('/api/auth/google/status')
      setAccount(response.data)
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
    const token = localStorage.getItem('token')
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
