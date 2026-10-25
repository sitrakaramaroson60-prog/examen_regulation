import type { ReactNode } from "react"
import { Badge, Card, Heading, Text } from "./ui"
import { STATUS, type Tone } from "../lib/format"
import { useLiveStatus } from "../lib/useLive"


export function StatusPill({ status }: { status?: string | null }) {
  if (!status) return <Badge tone="gray">Seuil non configuré</Badge>
  const [label, tone] = STATUS[status] ?? [status, "gray" as Tone]
  return <Badge tone={tone}>{label}</Badge>
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="dashboard-heading">
      <div>
        <Heading as="h1">{title}</Heading>
        {subtitle && <Text>{subtitle}</Text>}
      </div>
      {actions && <div className="dashboard-actions">{actions}</div>}
    </div>
  )
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: ReactNode; tone?: Tone }) {
  return (
    <Card className={`stat-card kit-stat ${tone ? `tone-${tone}` : ""}`}>
      <small>{label}</small>
      <strong className="stat-value">{value}</strong>
      {hint && <span className="kit-hint">{hint}</span>}
    </Card>
  )
}

export function Section({ title, subtitle, actions, children }: { title: string; subtitle?: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <Card className="kit-section">
      <header>
        <div>
          <Heading as="h3">{title}</Heading>
          {subtitle && <Text>{subtitle}</Text>}
        </div>
        {actions && <div className="kit-actions">{actions}</div>}
      </header>
      {children}
    </Card>
  )
}

export function Notice({ tone = "orange", children }: { tone?: "orange" | "blue" | "red" | "green"; children: ReactNode }) {
  return <div className={`kit-notice notice-${tone}`}>{children}</div>
}

export const Loading = ({ text = "Chargement…" }: { text?: string }) => <p className="kit-empty">{text}</p>
export const Empty = ({ children }: { children: ReactNode }) => <p className="kit-empty">{children}</p>
export const ErrorMsg = ({ children }: { children: ReactNode }) => <Notice tone="red">{children}</Notice>

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: [T, string][]; value: T; onChange: (t: T) => void }) {
  return (
    <div className="kit-tabs" role="tablist">
      {tabs.map(([key, label]) => (
        <button key={key} role="tab" aria-selected={value === key} className={value === key ? "active" : ""} onClick={() => onChange(key)}>{label}</button>
      ))}
    </div>
  )
}

export function Table({ head, children }: { head: string[]; children: ReactNode }) {
  return (
    <div className="kit-table-wrap">
      <table className="kit-table">
        <thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  )
}

export function LiveBadge({ light = false }: { light?: boolean }) {
  const status = useLiveStatus()
  const label = status === "live" ? "En direct" : status === "connecting" ? "Connexion…" : "Actualisation périodique"
  return (
    <span className={`live-badge live-${status} ${light ? "live-light" : ""}`} title={status === "live" ? "Les pages se mettent à jour dès qu'une donnée change." : "Les données sont rafraîchies toutes les quelques secondes."}>
      <i /> {label}
    </span>
  )
}
