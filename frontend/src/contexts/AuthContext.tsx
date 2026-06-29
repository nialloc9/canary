import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { api, TokenResponse } from '../api/client'

interface AuthState {
  isAuthenticated: boolean
  login: (username: string, password: string) => Promise<void>
  register: (payload: {
    account_name: string
    account_domain: string
    email: string
    username: string
    password: string
  }) => Promise<void>
  logout: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [isAuthenticated, setIsAuthenticated] = useState(() =>
    !!localStorage.getItem('access_token')
  )

  const login = useCallback(async (username: string, password: string) => {
    const tokens: TokenResponse = await api.auth.login(username, password)
    localStorage.setItem('access_token', tokens.access_token)
    localStorage.setItem('refresh_token', tokens.refresh_token)
    setIsAuthenticated(true)
  }, [])

  const register = useCallback(
    async (payload: {
      account_name: string
      account_domain: string
      email: string
      username: string
      password: string
    }) => {
      await api.auth.register(payload)
      await login(payload.username, payload.password)
    },
    [login]
  )

  const logout = useCallback(async () => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      try {
        await api.auth.logout(refreshToken)
      } catch {
        // best-effort
      }
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setIsAuthenticated(false)
  }, [])

  return (
    <AuthContext.Provider value={{ isAuthenticated, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
