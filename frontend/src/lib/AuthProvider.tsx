import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react"
import { api, tokens } from "./api"
import { AuthContext, type CurrentUser } from "./auth-context"

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let alive = true
    ;(async () => {
      if (tokens.refresh) {
        try {
          // Le premier appel déclenche un renouvellement automatique du jeton d'accès.
          const me = await api<CurrentUser>("/auth/me/")
          if (alive) setUser(me)
        } catch {
          tokens.clear()
        }
      }
      if (alive) setLoading(false)
    })()
    return () => {
      alive = false
    }
  }, [])

  const login = useCallback(async (email: string, password: string) => {
    const data = await api<{ access: string; refresh: string; user: CurrentUser }>("/auth/login/", {
      method: "POST",
      auth: false,
      body: { email, password },
    })
    tokens.set(data.access, data.refresh)
    setUser(data.user)
    return data.user
  }, [])

  const logout = useCallback(async () => {
    try {
      if (tokens.refresh) await api("/auth/logout/", { method: "POST", body: { refresh: tokens.refresh } })
    } catch {
      /* le jeton est de toute façon effacé localement */
    }
    tokens.clear()
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, login, logout }), [user, loading, login, logout])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}
