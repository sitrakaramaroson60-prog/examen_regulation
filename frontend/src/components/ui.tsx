import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react"
import { Link, type LinkProps } from "react-router"
import { LoaderCircle } from "lucide-react"

export function Button({
  children,
  variant = "primary",
  size = "md",
  loading,
  className = "",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost" | "danger"
  size?: "sm" | "md"
  loading?: boolean
}) {
  return (
    <button
      className={`btn btn-${variant} btn-${size} ${className}`}
      {...props}
    >
      {loading ? <LoaderCircle size={16} className="spin" /> : children}
    </button>
  )
}

export function ButtonLink({
  children,
  variant = "primary",
  className = "",
  ...props
}: LinkProps & {
  children: ReactNode
  variant?: "primary" | "secondary" | "ghost"
}) {
  return (
    <Link className={`btn btn-${variant} btn-md ${className}`} {...props}>
      {children}
    </Link>
  )
}

export function Card({
  children,
  className = "",
}: {
  children: ReactNode
  className?: string
}) {
  return <div className={`card ${className}`}>{children}</div>
}

export function Heading({
  as: Tag = "h2",
  children,
  className = "",
}: {
  as?: "h1" | "h2" | "h3" | "h4"
  children: ReactNode
  className?: string
}) {
  return <Tag className={className}>{children}</Tag>
}

export function Text({
  as: Tag = "p",
  children,
  className = "",
}: {
  as?: "p" | "span" | "label" | "small"
  children: ReactNode
  className?: string
}) {
  return <Tag className={className}>{children}</Tag>
}

export function Input({
  label,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label?: string; error?: string }) {
  return (
    <label className="field">
      {label && <span className="field-label">{label}</span>}
      <input className={error ? "input input-error" : "input"} {...props} />
      {error && <small className="field-error">{error}</small>}
    </label>
  )
}

export function Checkbox({
  children,
  defaultChecked,
}: {
  children: ReactNode
  defaultChecked?: boolean
}) {
  return (
    <label className="check-row">
      <input type="checkbox" defaultChecked={defaultChecked} />
      <span>{children}</span>
    </label>
  )
}

export function Select({
  label,
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement> & {
  label?: string
  children: ReactNode
}) {
  return (
    <label className="field">
      {label && <span className="field-label">{label}</span>}
      <select className="input" {...props}>
        {children}
      </select>
    </label>
  )
}

export function Badge({
  children,
  tone = "blue",
}: {
  children: ReactNode
  tone?: "blue" | "green" | "orange" | "red" | "gray"
}) {
  return <span className={`badge badge-${tone}`}>{children}</span>
}

export function Avatar({ initials }: { initials: string }) {
  return <span className="avatar">{initials}</span>
}

export function DemoNotice({ compact = false }: { compact?: boolean }) {
  return (
    <div className={compact ? "demo-notice compact" : "demo-notice"}>
      <span className="demo-dot" />
      <Text as="span">
        <strong>Démonstration</strong> — données fictives, aucune donnée
        officielle.
      </Text>
    </div>
  )
}
