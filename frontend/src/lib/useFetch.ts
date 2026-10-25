import { useCallback, useEffect, useState } from "react"
import { api, describeError } from "./api"
import { useLivePath } from "./useLive"

type Query = Record<string, string | number | undefined>

/** Charge une ressource de l'API ; se recharge quand le chemin ou les paramètres changent. `reload()` force un nouvel appel. */
export function useFetch<T>(path: string | null, query?: Query, auth = true) {
  const key = JSON.stringify([path, query ?? {}, auth])
  const [state, setState] = useState<{ key: string; data?: T; error?: string }>({ key: "" })
  const [tick, setTick] = useState(0)
  const live = useLivePath(path) // rechargement automatique quand les données concernées changent

  useEffect(() => {
    const [p, q, a] = JSON.parse(key) as [string | null, Query, boolean]
    if (!p) return
    let alive = true
    api<T>(p, { query: q, auth: a })
      .then((data) => alive && setState({ key, data }))
      .catch((e) => alive && setState({ key, error: describeError(e) }))
    return () => {
      alive = false
    }
  }, [key, tick, live])

  const reload = useCallback(() => setTick((t) => t + 1), [])
  const current = state.key === key
  return {
    data: current ? state.data : undefined,
    error: current ? state.error : undefined,
    loading: path !== null && !current,
    reload,
  }
}
