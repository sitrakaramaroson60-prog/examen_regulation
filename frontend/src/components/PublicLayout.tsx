import { useState } from "react"
import { Link, NavLink, Outlet } from "react-router"
import { Building2, ChevronRight, Menu, ShieldCheck, X } from "lucide-react"
import { Button, ButtonLink, Text } from "./ui"
import { LiveBadge } from "./kit"

const links = [
  ["Accueil", "/"],
  ["Publications", "/publications"],
  ["Sondages", "/sondages"],
  ["Qualité des services", "/qualite"],
  ["Rapports", "/rapports"],
  ["Signaler un problème", "/signalement"],
  ["À propos", "/a-propos"],
]

export default function PublicLayout() {
  const [open, setOpen] = useState(false)
  return (
    <div className="site-shell">
      <header className="public-header">
        <div className="container header-inner">
          <Link to="/" className="brand" aria-label="Accueil">
            <span className="brand-mark">
              <ShieldCheck size={24} />
            </span>
            <span>
              <strong>QoS Madagascar</strong>
              <small>Plateforme de régulation</small>
            </span>
          </Link>
          <nav
            className={open ? "public-nav nav-open" : "public-nav"}
            aria-label="Navigation principale"
          >
            {links.map(([label, path]) => (
              <NavLink key={path} to={path} onClick={() => setOpen(false)}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="header-actions">
            <LiveBadge />
            <ButtonLink to="/connexion" variant="secondary">
              <Building2 size={17} /> Espace organismes
            </ButtonLink>
            <Button
              variant="ghost"
              className="menu-button"
              onClick={() => setOpen(!open)}
              aria-label="Menu"
            >
              {open ? <X size={21} /> : <Menu size={21} />}
            </Button>
          </div>
        </div>
      </header>
      <main>
        <Outlet />
      </main>
      <footer className="footer">
        <div className="container footer-grid">
          <div>
            <Link to="/" className="brand brand-light">
              <span className="brand-mark">
                <ShieldCheck size={24} />
              </span>
              <span>
                <strong>QoS Madagascar</strong>
                <small>Plateforme de régulation</small>
              </span>
            </Link>
            <Text>
              Un espace numérique au service de la transparence et de la qualité
              des télécommunications.
            </Text>
          </div>
          <div>
            <Text className="footer-title">Accès rapide</Text>
            <Link to="/publications">Publications</Link>
            <Link to="/sondages">Sondages publics</Link>
            <Link to="/rapports">Rapports validés</Link>
            <Link to="/signalement">Signaler un problème</Link>
            <Link to="/signalement/suivi">Suivre un signalement</Link>
          </div>
          <div>
            <Text className="footer-title">Informations</Text>
            <Link to="/a-propos">À propos</Link>
            <Link to="/confidentialite">Confidentialité</Link>
            <Link to="/accessibilite">Accessibilité</Link>
          </div>
          <div>
            <Text className="footer-title">Participation publique</Text>
            <Text>
              Aucun compte n’est requis pour répondre aux sondages ouverts.
            </Text>
            <Link to="/sondages" className="footer-cta">
              Voir les sondages <ChevronRight size={15} />
            </Link>
          </div>
        </div>
        <div className="container footer-bottom">
          <Text as="small">
            © 2025 — Interface de démonstration non officielle.
          </Text>
          <Text as="small">Données fictives à des fins de prototypage.</Text>
        </div>
      </footer>
    </div>
  )
}
