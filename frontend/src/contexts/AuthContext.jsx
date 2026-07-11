import React, { createContext, useContext, useState, useEffect } from 'react'
import { login as loginApi, register as registerApi, logout as logoutApi } from '../services/auth'

const AuthContext = createContext()

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const token = localStorage.getItem('access_token')
    if (token) {
      // TODO: Verify token and set user
    }
    setLoading(false)
  }, [])

  const login = async (email, password) => {
    try {
      const response = await loginApi({ email, password })
      localStorage.setItem('access_token', response.access)
      localStorage.setItem('refresh_token', response.refresh)
      setUser(response.user)
      return { success: true }
    } catch (error) {
      return { success: false, error: error.response?.data }
    }
  }

  const register = async (userData) => {
    try {
      const response = await registerApi(userData)
      return { success: true, data: response }
    } catch (error) {
      return { success: false, error: error.response?.data }
    }
  }

  const logout = () => {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    setUser(null)
    logoutApi()
  }

  const value = {
    user,
    loading,
    login,
    register,
    logout,
    isAuthenticated: !!user
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
