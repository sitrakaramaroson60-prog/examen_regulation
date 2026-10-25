import { useEffect, useState } from "react"
import { realtime, topicsForPath, type LiveStatus } from "./realtime"

/** Renvoie un compteur qui change (au plus toutes les 300 ms) quand l'un des thèmes donnés évolue. À mettre dans les dépendances d'un effet de chargement. */
export function useLiveTick(topics: string[]): number {
  const [tick, setTick] = useState(0)
  const key = topics.join("|")
  useEffect(() => {
    if (!key) return
    const wanted = new Set(key.split("|"))
    let timer: number | undefined
    const off = realtime.subscribe((topic) => {
      if (topic !== "*" && !wanted.has(topic)) return
      window.clearTimeout(timer)
      timer = window.setTimeout(() => setTick((t) => t + 1), 300)
    })
    return () => {
      off()
      window.clearTimeout(timer)
    }
  }, [key])
  return tick
}

export const useLivePath = (path: string | null) => useLiveTick(topicsForPath(path))

export function useLiveStatus(): LiveStatus {
  const [status, setStatus] = useState<LiveStatus>("connecting")
  useEffect(() => realtime.subscribeStatus(setStatus), [])
  return status
}
