import axios from 'axios'

const TOKEN_KEY = 'cloud_transfer_token'

export async function login(username: string, password: string): Promise<void> {
  const response = await axios.post('/api/auth/login', { username, password })
  localStorage.setItem(TOKEN_KEY, response.data.access_token)
}

export function logout(): void {
  localStorage.removeItem(TOKEN_KEY)
  window.location.href = '/login'
}

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}

export function isAuthenticated(): boolean {
  const token = getToken()
  if (!token) return false
  try {
    const payload = JSON.parse(atob(token.split('.')[1]))
    return payload.exp * 1000 > Date.now()
  } catch {
    return false
  }
}
