import { useEffect, useRef, useState } from "react"
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router"
import { useAuth } from "../lib/auth-context"
import { api } from "../lib/api"
import { LiveBadge } from "./kit"
import { useLiveTick } from "../lib/useLive"
import {
  Bell,
  BookOpen,
  ChevronDown,
  CircleHelp,
  ClipboardCheck,
  Database,
  FileBarChart,
  FileText,
  Gauge,
  Folder,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  MessageSquareWarning,
  PanelLeftClose,
  ScanSearch,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Upload,
  UserRound,
  Users,
  X,
} from "lucide-react"
import { Avatar, Badge, Button, Text } from "./ui"

type Mode = "regulation" | "operator" | "publications" | "admin"

const config = {
  regulation: {
    label: "ARTEC — Régulation et Prédiction",
    initials: "AR",
    user: "ARTEC",
    nav: [
      ["Supervision QoS", "/regulation", Gauge],
      ["Prédictions", "/regulation/predictions", Sparkles],
      ["Obligations et conformité", "/regulation/conformite", ClipboardCheck],
      ["Dossiers réglementaires", "/regulation/dossiers", Folder],
      ["Soumissions", "/regulation/soumissions", Database],
      ["Sondages réglementaires", "/regulation/sondages", Users],
      ["Rapports publics", "/regulation/rapports", BookOpen],
      ["Commentaires", "/regulation/commentaires", MessageSquareWarning],
      ["Mesures QoS", "/regulation/indicateurs", FileBarChart],
      ["Seuils QoS", "/regulation/seuils", SlidersHorizontal],
      ["Réclamations", "/regulation/reclamations", MessageSquareWarning],
      ["Comptes et accès", "/regulation/comptes", UserRound],
      ["Historique", "/regulation/historique", History],
    ],
  },
  operator: {
    label: "Espace opérateur",
    initials: "OP",
    user: "Opérateur",
    nav: [
      ["Vue d’ensemble", "/operateur", LayoutDashboard],
      ["Ma conformité", "/operateur/conformite", ClipboardCheck],
      ["Mes mesures", "/operateur/mesures", FileBarChart],
      ["Datasets et importation", "/operateur/datasets", Upload],
      ["Soumissions à l’ARTEC", "/operateur/soumissions", Database],
      ["Sondages", "/operateur/sondages", Users],
      ["Publications", "/operateur/publications", FileText],
      ["Collectes web", "/operateur/scraping", ScanSearch],
      ["Dossiers réglementaires", "/operateur/dossiers", Folder],
      ["Réclamations et contestations", "/operateur/reclamations", MessageSquareWarning],
    ],
  },
  admin: {
    label: "Administration système",
    initials: "AD",
    user: "Administrateur",
    nav: [
      ["Comptes et accès", "/administration", UserRound],
      ["Historique", "/administration/historique", History],
    ],
  },
  publications: {
    label: "ARTEC — Publications",
    initials: "AP",
    user: "ARTEC",
    nav: [
      ["Vue d’ensemble", "/publications-admin", LayoutDashboard],
      ["Publications", "/publications-admin/contenus", BookOpen],
      ["Sondages", "/publications-admin/sondages", Users],
      ["Commentaires", "/publications-admin/commentaires", MessageSquareWarning],
      ["Historique", "/publications-admin/historique", History],
    ],
  },
}

const BASE_PATH: Record<Mode, string> = { regulation: "/regulation", operator: "/operateur", publications: "/publications-admin", admin: "/administration" }

export default function AppLayout({ mode }: { mode: Mode }) {
  const [mobileOpen, setMobileOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(false)
  const location = useLocation()
  const navigate = useNavigate()
  const { user, logout } = useAuth()
  const [unread, setUnread] = useState(0)
  const [toasts, setToasts] = useState<{ id: number; title: string; message: string }[]>([])
  const previous = useRef<number | null>(null)
  const liveNotifications = useLiveTick(["notifications"])
  useEffect(() => {
    let alive = true
    api<{ count: number }>("/notifications/unread-count/")
      .then(async (d) => {
        if (!alive) return
        setUnread(d.count)
        // une nouvelle notification est arrivée pendant la session : on l'affiche brièvement
        if (previous.current !== null && d.count > previous.current) {
          const latest = await api<{ results: { id: number; title: string; message: string }[] }>("/notifications/", { query: { is_read: "false", page_size: 1 } })
          const n = latest.results[0]
          if (alive && n) {
            setToasts((t) => [...t, n])
            window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== n.id)), 7000)
          }
        }
        previous.current = d.count
      })
      .catch(() => undefined)
    return () => {
      alive = false
    }
  }, [liveNotifications])
  const base = config[mode]
  const fullName = user ? `${user.first_name} ${user.last_name}`.trim() || user.email : base.user
  const current = {
    ...base,
    user: user?.organization ? `${user.organization.name}` : fullName,
    initials: (fullName.match(/\b\w/g) ?? ["?"]).slice(0, 2).join("").toUpperCase(),
  }
  const doLogout = async () => {
    await logout()
    navigate("/connexion", { replace: true })
  }
  const basePath = BASE_PATH[mode]
  const activeLabel =
    current.nav.find(([, path]) => (path === basePath ? location.pathname === path : location.pathname.startsWith(path as string)))?.[0] ??
    (location.pathname.endsWith("/notifications") ? "Notifications" : location.pathname.endsWith("/compte") ? "Mon compte" : "Vue d’ensemble")

  return (
    <div className={`app-shell ${collapsed ? "sidebar-collapsed" : ""}`}>
      <aside className={mobileOpen ? "sidebar sidebar-open" : "sidebar"}>
        <div className="sidebar-head">
          <Link to="/" className="app-brand">
            <span className="brand-mark">
              <ShieldCheck size={23} />
            </span>
            <span className="brand-copy">
              <strong>QoS Madagascar</strong>
              <small>{current.label}</small>
            </span>
          </Link>
          <Button
            variant="ghost"
            className="mobile-close"
            onClick={() => setMobileOpen(false)}
          >
            <X size={20} />
          </Button>
        </div>
        <div className="org-chip">
          <Avatar initials={current.initials} />
          <span>
            <strong>{current.user}</strong>
            <small>Espace sécurisé</small>
          </span>
          <ChevronDown size={15} />
        </div>
        <nav className="side-nav">
          <Text as="small" className="nav-section">
            NAVIGATION
          </Text>
          {current.nav.map(([label, path, Icon]) => (
            <NavLink
              key={path as string}
              to={path as string}
              end={path === basePath}
              onClick={() => setMobileOpen(false)}
            >
              <Icon size={19} />
              <span>{label as string}</span>
            </NavLink>
          ))}
          <Text as="small" className="nav-section nav-section-bottom">
            COMPTE
          </Text>
          <NavLink to={`${basePath}/notifications`}>
            <Bell size={19} />
            <span>Notifications</span>
            {unread > 0 && <Badge tone="blue">{unread}</Badge>}
          </NavLink>
          <NavLink to={`${basePath}/compte`}>
            <UserRound size={19} />
            <span>Mon compte</span>
          </NavLink>
        </nav>
        <div className="sidebar-foot">
          <Link to="/a-propos">
            <CircleHelp size={19} />
            <span>À propos de la plateforme</span>
          </Link>
          <button type="button" className="nav-logout" onClick={doLogout}>
            <LogOut size={19} />
            <span>Déconnexion</span>
          </button>
          <Button
            variant="ghost"
            className="collapse-button"
            onClick={() => setCollapsed(!collapsed)}
          >
            <PanelLeftClose size={18} />
            <span>Réduire le menu</span>
          </Button>
        </div>
      </aside>
      {mobileOpen && (
        <div
          className="sidebar-backdrop"
          onClick={() => setMobileOpen(false)}
        />
      )}
      <div className="app-main">
        <header className="topbar">
          <div className="topbar-title">
            <Button
              variant="ghost"
              className="mobile-menu"
              onClick={() => setMobileOpen(true)}
            >
              <Menu size={21} />
            </Button>
            <div>
              <Text as="small">{current.label}</Text>
              <strong>{activeLabel as string}</strong>
            </div>
          </div>
          <div className="topbar-actions">
            <LiveBadge />
            <Button
              variant="ghost"
              className="icon-button"
              aria-label="Notifications"
              onClick={() => navigate(`${basePath}/notifications`)}
            >
              <Bell size={20} />
              {unread > 0 && <span className="notification-dot" title={`${unread} non lue(s)`} />}
            </Button>
            <div className="profile">
              <Avatar initials={current.initials} />
              <span>
                <strong>{current.user}</strong>
                <small>{user?.email}</small>
              </span>
              <ChevronDown size={16} />
            </div>
          </div>
        </header>
        <main className="dashboard-main">
          <Outlet />
        </main>
      </div>
      <div className="toast-stack" aria-live="polite">
        {toasts.map((t) => (
          <div className="toast" key={t.id}><strong>{t.title}</strong>{t.message}</div>
        ))}
      </div>
    </div>
  )
}
