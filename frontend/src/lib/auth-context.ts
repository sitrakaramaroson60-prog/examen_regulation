import { createContext, useContext } from "react"

export type Space = "operator" | "publications" | "regulation" | "admin"

export type CurrentUser = {
  id: number
  email: string
  first_name: string
  last_name: string
  role: "OPERATOR_USER" | "ARTEC_PUBLISHER" | "ARTEC_REGULATOR" | "SYSTEM_ADMIN"
  space: Space
  organization: { id: number; code: string; name: string } | null
}

export type AuthState = {
  user: CurrentUser | null
  loading: boolean
  login: (email: string, password: string) => Promise<CurrentUser>
  logout: () => Promise<void>
}

export const AuthContext = createContext<AuthState | null>(null)

export const SPACE_PATH: Record<Space, string> = {
  operator: "/operateur",
  publications: "/publications-admin",
  regulation: "/regulation",
  admin: "/administration",
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error("useAuth doit être utilisé dans <AuthProvider>")
  return ctx
}
