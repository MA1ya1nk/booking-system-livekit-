import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { apiRequest } from '../lib/api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(localStorage.getItem('token') || '')
  const [user, setUser] = useState(null)
  const [loadingUser, setLoadingUser] = useState(true)

  useEffect(() => {
    const loadUser = async () => {
      if (!token) {
        setUser(null)
        setLoadingUser(false)
        return
      }
      try {
        const me = await apiRequest('/auth/me', { token })
        setUser(me)
      } catch {
        setToken('')
        localStorage.removeItem('token')
        setUser(null)
      } finally {
        setLoadingUser(false)
      }
    }
    loadUser()
  }, [token])

  const value = useMemo(
    () => ({
      token,
      user,
      loadingUser,
      isAuthenticated: Boolean(token && user),
      isAdmin: user?.role === 'admin',
      setAuthToken: (value) => {
        setToken(value)
        if (value) {
          localStorage.setItem('token', value)
        } else {
          localStorage.removeItem('token')
        }
      },
      logout: () => {
        setToken('')
        localStorage.removeItem('token')
        setUser(null)
      },
    }),
    [token, user, loadingUser],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used inside AuthProvider')
  }
  return context
}
