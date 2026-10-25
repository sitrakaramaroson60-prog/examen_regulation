/**
 * Client HTTP du backend Django REST Framework.
 * - Jeton d'accès conservé en mémoire ; jeton de renouvellement en sessionStorage (effacé à la fermeture de l'onglet).
 * - Renouvellement automatique sur 401, une seule tentative.
 * - Le rôle affiché vient TOUJOURS de GET /auth/me/ : le backend reste seul juge des permissions.
 */
const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000/api/v1"

const REFRESH_KEY = "qos.refresh"
let accessToken: string | null = null

export type ApiErrorBody = { error?: { code: string; message: string; details?: unknown } }

export class ApiError extends Error {
  status: number
  code: string
  details: unknown
  constructor(status: number, body: ApiErrorBody | null) {
    super(body?.error?.message ?? `Erreur ${status}`)
    this.status = status
    this.code = body?.error?.code ?? "error"
    this.details = body?.error?.details ?? null
  }
}

const tokenListeners = new Set<() => void>()
/** Permet à d'autres modules (temps réel) de réagir à une connexion, un renouvellement ou une déconnexion. */
export const onTokenChange = (fn: () => void) => {
  tokenListeners.add(fn)
  return () => void tokenListeners.delete(fn)
}

export const API_BASE = API_URL

export const tokens = {
  set(access: string, refresh?: string) {
    accessToken = access
    if (refresh) sessionStorage.setItem(REFRESH_KEY, refresh)
    tokenListeners.forEach((fn) => fn())
  },
  clear() {
    accessToken = null
    sessionStorage.removeItem(REFRESH_KEY)
    tokenListeners.forEach((fn) => fn())
  },
  get refresh() {
    return sessionStorage.getItem(REFRESH_KEY)
  },
  get access() {
    return accessToken
  },
}

export async function refreshAccess(): Promise<boolean> {
  const refresh = tokens.refresh
  if (!refresh) return false
  const res = await fetch(`${API_URL}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
  })
  if (!res.ok) {
    tokens.clear()
    return false
  }
  const data = await res.json()
  tokens.set(data.access, data.refresh)
  return true
}

type Options = { method?: string; body?: unknown; auth?: boolean; query?: Record<string, string | number | undefined> }

export async function api<T = unknown>(path: string, opts: Options = {}): Promise<T> {
  const { method = "GET", body, auth = true, query } = opts
  const qs = query
    ? "?" + new URLSearchParams(Object.entries(query).filter(([, v]) => v !== undefined && v !== "").map(([k, v]) => [k, String(v)])).toString()
    : ""
  const doFetch = () => {
    const headers: Record<string, string> = {}
    if (auth && accessToken) headers.Authorization = `Bearer ${accessToken}`
    if (body !== undefined && !(body instanceof FormData)) headers["Content-Type"] = "application/json"
    return fetch(`${API_URL}${path}${qs}`, {
      method,
      headers,
      body: body === undefined ? undefined : body instanceof FormData ? body : JSON.stringify(body),
    })
  }
  let res = await doFetch()
  if (res.status === 401 && auth && (await refreshAccess())) res = await doFetch()
  if (res.status === 204) return undefined as T
  const text = await res.text()
  const data = text ? JSON.parse(text) : null
  if (!res.ok) throw new ApiError(res.status, data)
  return data as T
}

/** Pagination DRF */
export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

/** Convertit une erreur de validation DRF en message lisible. */
export function describeError(err: unknown): string {
  if (err instanceof ApiError) {
    const d = err.details as Record<string, unknown> | null
    if (d && typeof d === "object") {
      const parts = Object.entries(d).map(([k, v]) => `${k} : ${typeof v === "object" ? JSON.stringify(v) : String(v)}`)
      if (parts.length) return parts.join(" · ")
    }
    return err.message
  }
  return "Le serveur est injoignable. Vérifiez votre connexion."
}

/** Télécharge un fichier protégé (CSV, etc.) avec le jeton d'accès, puis déclenche l'enregistrement dans le navigateur. */
export async function downloadFile(path: string, filename: string) {
  const headers: Record<string, string> = {}
  if (tokens.access) headers.Authorization = `Bearer ${tokens.access}`
  let res = await fetch(`${API_URL}${path}`, { headers })
  if (res.status === 401 && (await refreshAccess())) {
    headers.Authorization = `Bearer ${tokens.access}`
    res = await fetch(`${API_URL}${path}`, { headers })
  }
  if (!res.ok) throw new ApiError(res.status, null)
  const url = URL.createObjectURL(await res.blob())
  const a = document.createElement("a")
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
