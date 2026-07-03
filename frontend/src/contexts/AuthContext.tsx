import { createContext, useContext, useState, useCallback, ReactNode } from 'react'
import { api, TokenResponse, storeTokens, clearTokens, hasStoredSession, getStoredRefreshToken } from '../api/client'

interface AuthState {
  isAuthenticated: boolean
  login: (username: string, password: string, rememberMe?: boolean) => Promise<void>
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
  const [isAuthenticated, setIsAuthenticated] = useState(() => hasStoredSession())

  const login = useCallback(async (username: string, password: string, rememberMe = false) => {
    const tokens: TokenResponse = await api.auth.login(username, password)
    storeTokens(tokens, rememberMe)
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
    const refreshToken = getStoredRefreshToken()
    if (refreshToken) {
      try {
        await api.auth.logout(refreshToken)
      } catch {
        // best-effort
      }
    }
    clearTokens()
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
