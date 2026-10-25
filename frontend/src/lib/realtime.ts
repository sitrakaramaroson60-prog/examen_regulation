/**
 * Temps réel : WebSocket (poussée immédiate) + journal d'événements HTTP (rattrapage et repli).
 *
 * - Les événements ne contiennent aucune donnée : ils disent « le thème X a changé ». Les pages rechargent alors leurs
 *   données par l'API, qui applique les permissions habituelles.
 * - Si le WebSocket est indisponible (proxy, serveur WSGI, coupure), on interroge le journal toutes les 5 s.
 * - Même connecté, un contrôle de sécurité toutes les 30 s rattrape un événement manqué (ex. émis par un worker Celery
 *   sans Redis partagé). Après une coupure, les événements manqués sont rejoués grâce au curseur.
 */
import { API_BASE, api, onTokenChange, refreshAccess, tokens } from "./api"

export type LiveStatus = "connecting" | "live" | "polling"
type Listener = (topic: string) => void

const WS_URL = API_BASE.replace(/^http/, "ws").replace(/\/api\/v1\/?$/, "") + "/ws/realtime/"
const POLL_FAST = 5000
const POLL_SAFETY = 30000

type EventsResponse = { last_id: number; events: { id: number; topic: string }[]; reset: boolean }

class Realtime {
  private ws: WebSocket | null = null
  private listeners = new Set<Listener>()
  private statusListeners = new Set<(s: LiveStatus) => void>()
  private status: LiveStatus = "connecting"
  private lastId: number | null = null
  private pollTimer: number | undefined
  private retryTimer: number | undefined
  private retry = 0
  private started = false
  private unsubscribeToken: (() => void) | null = null

  start() {
    if (this.started) return
    this.started = true
    this.unsubscribeToken = onTokenChange(() => this.onTokenChange())
    document.addEventListener("visibilitychange", this.onVisible)
    window.addEventListener("online", this.onVisible)
    this.connect()
    this.schedulePoll()
  }

  stop() {
    this.started = false
    this.unsubscribeToken?.()
    document.removeEventListener("visibilitychange", this.onVisible)
    window.removeEventListener("online", this.onVisible)
    window.clearTimeout(this.pollTimer)
    window.clearTimeout(this.retryTimer)
    this.ws?.close()
    this.ws = null
  }

  subscribe(fn: Listener) {
    this.listeners.add(fn)
    return () => void this.listeners.delete(fn)
  }
  subscribeStatus(fn: (s: LiveStatus) => void) {
    this.statusListeners.add(fn)
    fn(this.status)
    return () => void this.statusListeners.delete(fn)
  }

  private setStatus(s: LiveStatus) {
    if (s === this.status) return
    this.status = s
    this.statusListeners.forEach((fn) => fn(s))
  }
  private emit(topic: string) {
    this.listeners.forEach((fn) => fn(topic))
  }

  private onVisible = () => {
    if (document.visibilityState === "hidden") return
    void this.poll()
    if (!this.ws || this.ws.readyState > WebSocket.OPEN) this.connect()
  }

  private onTokenChange() {
    if (!this.ws) return
    if (this.ws.readyState === WebSocket.OPEN && tokens.access) this.ws.send(JSON.stringify({ type: "auth", token: tokens.access }))
    else if (!tokens.access) this.ws.close() // déconnexion : on repart sur un canal public
  }

  private connect() {
    if (!this.started || (this.ws && this.ws.readyState <= WebSocket.OPEN)) return
    this.setStatus(this.status === "live" ? "live" : "connecting")
    let ws: WebSocket
    try {
      ws = new WebSocket(WS_URL)
    } catch {
      this.fallback()
      return
    }
    this.ws = ws
    ws.onopen = () => {
      this.retry = 0
      if (tokens.access) ws.send(JSON.stringify({ type: "auth", token: tokens.access }))
      void this.poll() // rejoue ce qui a pu se produire pendant la coupure
    }
    ws.onmessage = (msg) => {
      let data: { type?: string; topic?: string; id?: number }
      try {
        data = JSON.parse(msg.data)
      } catch {
        return
      }
      if (data.type === "ready") this.setStatus("live")
      else if (data.type === "event" && data.topic) {
        if (typeof data.id === "number" && (this.lastId === null || data.id > this.lastId)) this.lastId = data.id
        this.emit(data.topic)
      } else if (data.type === "auth_expired" || data.type === "auth_error") {
        void refreshAccess() // le jeton d'accès est court : on le renouvelle, ce qui ré-authentifie le canal
      }
    }
    ws.onclose = () => {
      if (this.ws === ws) this.ws = null
      this.fallback()
    }
    ws.onerror = () => ws.close()
  }

  private fallback() {
    this.setStatus("polling")
    if (!this.started) return
    window.clearTimeout(this.retryTimer)
    const delay = Math.min(30000, 1000 * 2 ** this.retry++)
    this.retryTimer = window.setTimeout(() => this.connect(), delay)
  }

  private schedulePoll() {
    window.clearTimeout(this.pollTimer)
    if (!this.started) return
    const wait = this.status === "live" ? POLL_SAFETY : POLL_FAST
    this.pollTimer = window.setTimeout(async () => {
      if (document.visibilityState !== "hidden") await this.poll()
      this.schedulePoll()
    }, wait)
  }

  private async poll() {
    try {
      const authed = !!tokens.access
      if (this.lastId === null) {
        const r = await api<EventsResponse>("/realtime/events/", { auth: authed })
        this.lastId = r.last_id
        return
      }
      const r = await api<EventsResponse>("/realtime/events/", { auth: authed, query: { after: this.lastId } })
      this.lastId = r.last_id
      if (r.reset) this.emit("*")
      else new Set(r.events.map((e) => e.topic)).forEach((t) => this.emit(t))
    } catch {
      /* réseau indisponible : on réessaiera au prochain cycle */
    }
  }
}

export const realtime = new Realtime()

/** Thèmes à surveiller pour un chemin d'API : un changement de ces thèmes recharge la ressource. */
export function topicsForPath(path: string | null): string[] {
  if (!path) return []
  const rules: [RegExp, string[]][] = [
    [/^\/qos\/(measurements|public)/, ["qos", "thresholds", "surveys"]],
    [/^\/qos\/thresholds/, ["thresholds"]],
    [/^\/predictions/, ["predictions", "datasets"]],
    [/^\/regulation\/(operator-files)/, ["cases", "obligations", "qos"]],
    [/^\/regulation\/(obligations|alerts)/, ["obligations"]],
    [/^\/regulation\/overview/, ["submissions", "cases", "obligations", "predictions"]],
    [/^\/regulation\//, ["cases"]],
    [/^\/datasets/, ["datasets", "submissions"]],
    [/^\/submissions/, ["submissions"]],
    [/^\/surveys/, ["surveys"]],
    [/^\/publications\/overview/, ["publications", "comments", "surveys"]],
    [/^\/publications/, ["publications"]],
    [/^\/comments/, ["comments"]],
    [/^\/complaints/, ["complaints"]],
    [/^\/scraping/, ["scraping"]],
    [/^\/notifications/, ["notifications"]],
    [/^\/audit/, ["audit"]],
    [/^\/auth\/users/, ["users"]],
  ]
  return rules.find(([re]) => re.test(path))?.[1] ?? []
}
