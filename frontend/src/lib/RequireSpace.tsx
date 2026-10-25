import type { ReactNode } from "react"
import { Navigate, useLocation } from "react-router"
import { SPACE_PATH, useAuth, type Space } from "./auth-context"

/**
 * Garde d'interface. Elle ne remplace PAS les contrôles serveur : elle évite seulement
 * d'afficher un espace qui renverrait 403 à chaque requête.
 */
export function RequireSpace({ spaces, children }: { spaces: Space[]; children: ReactNode }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="container" style={{ padding: 48 }}>Chargement…</div>
  if (!user) return <Navigate to="/connexion" state={{ from: location.pathname }} replace />
  if (!spaces.includes(user.space)) return <Navigate to={SPACE_PATH[user.space]} replace />
  return <>{children}</>
}
