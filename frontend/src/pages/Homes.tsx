import { Link } from "react-router"
import { useState } from "react"
import { ErrorMsg, Loading, Notice, PageHeader, Section, Stat } from "../components/kit"
import { Button, Input } from "../components/ui"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"
import Supervision from "./Supervision"

type RegOverview = {
  submissions_pending_review: number; submissions_total: number; predictions_completed: number; cases_open: number; cases_awaiting_operator: number
  alerts_open: number; alerts_critical: number; obligations_active: number; checks_planned: number
}

export function RegulationHome() {
  const o = useFetch<RegOverview>("/regulation/overview/")
  const d = o.data
  return (
    <div className="page-stack">
      <PageHeader title="Supervision de la qualité de service" subtitle="Indicateurs comparables entre opérateurs, fondés sur des mesures techniques validées." />
      {o.error && <ErrorMsg>{o.error}</ErrorMsg>}
      {o.loading && <Loading />}
      {d && (
        <div className="kpi-grid">
          <Stat label="Soumissions à examiner" value={d.submissions_pending_review} hint={<LinkText to="/regulation/soumissions">Ouvrir</LinkText>} tone={d.submissions_pending_review ? "orange" : undefined} />
          <Stat label="Alertes algorithmiques ouvertes" value={d.alerts_open} hint={`${d.alerts_critical} écart(s) important(s)`} tone={d.alerts_critical ? "red" : d.alerts_open ? "orange" : undefined} />
          <Stat label="Dossiers en cours" value={d.cases_open} hint={`${d.cases_awaiting_operator} en attente de réponse`} />
          <Stat label="Engagements suivis" value={d.obligations_active} hint={`${d.checks_planned} contrôle(s) planifié(s)`} />
          <Stat label="Prévisions réalisées" value={d.predictions_completed} />
        </div>
      )}
      {d && d.obligations_active === 0 && <Notice tone="blue">Aucun engagement n'est encore enregistré : renseignez-les dans « Obligations et conformité » pour activer le suivi des écarts. Configurez aussi les seuils QoS pour obtenir les niveaux bon / moyen / mauvais.</Notice>}
      <Supervision />
      <BarometerPublishing />
    </div>
  )
}

/** Publication des indicateurs agrégés au public : décision de l'ARTEC Régulation (tracée dans l'historique). */
function BarometerPublishing() {
  const cfg = useFetch<{ enabled: boolean; min_measurements: number }>("/qos/public/settings/")
  const [min, setMin] = useState("")
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const save = async (body: Record<string, unknown>, ok: string) => {
    try { await api("/qos/public/settings/", { method: "PUT", body }); setMsg({ t: "green", m: ok }); cfg.reload() } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  if (!cfg.data) return null
  return (
    <Section title="Publication des indicateurs au public" subtitle="Moyennes par opérateur des mesures techniques validées (jamais les déclarations), affichées sur la page publique « Qualité des services ».">
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Notice tone={cfg.data.enabled ? "green" : "orange"}>{cfg.data.enabled ? "Le baromètre est publié : le public voit les moyennes dès qu'une nouvelle mesure est acceptée." : "Le baromètre n'est pas publié."}</Notice>
      <div className="toolbar">
        <Input label="Nombre minimal de mesures pour publier une moyenne" type="number" min={5} value={min || String(cfg.data.min_measurements)} onChange={(e) => setMin(e.target.value)} />
        <Button variant="secondary" onClick={() => save({ min_measurements: Number(min || cfg.data!.min_measurements) }, "Seuil mis à jour.")}>Enregistrer le seuil</Button>
        <Button onClick={() => save({ enabled: !cfg.data!.enabled }, cfg.data!.enabled ? "Baromètre retiré du site public." : "Baromètre publié.")}>{cfg.data.enabled ? "Retirer du site public" : "Publier au public"}</Button>
      </div>
    </Section>
  )
}
const LinkText = ({ to, children }: { to: string; children: string }) => <Link to={to} className="link-btn">{children}</Link>

type FileSummary = { summary: { obligations_total: number; obligations_evaluated: number; obligations_compliant: number; obligations_with_gap: number; open_cases: number; awaiting_response: number; warnings: number; congratulations: number; pending_corrective_actions: number } }

export function OperatorHome() {
  const { user } = useAuth()
  const file = useFetch<FileSummary>("/regulation/operator-files/me/")
  const subs = useFetch<Page<{ id: number; status: string }>>("/submissions/", { page_size: 100 })
  const s = file.data?.summary
  const toFix = subs.data?.results.filter((x) => x.status === "CORRECTION_REQUIRED").length ?? 0
  return (
    <div className="page-stack">
      <PageHeader title={`Vue d'ensemble — ${user?.organization?.name ?? ""}`} subtitle="Votre qualité de service telle que mesurée, vos engagements et les suites données par l'ARTEC." />
      {s && s.awaiting_response > 0 && <Notice>L'ARTEC attend une réponse de votre part sur {s.awaiting_response} dossier(s). <Link className="link-btn" to="/operateur/dossiers">Consulter</Link></Notice>}
      {toFix > 0 && <Notice>{toFix} soumission(s) nécessitent une correction. <Link className="link-btn" to="/operateur/soumissions">Voir les soumissions</Link></Notice>}
      {s && (
        <div className="kpi-grid">
          <Stat label="Engagements conformes" value={`${s.obligations_compliant} / ${s.obligations_evaluated}`} tone={s.obligations_with_gap ? "orange" : "green"} hint={`${s.obligations_total} engagement(s)`} />
          <Stat label="Écarts détectés" value={s.obligations_with_gap} tone={s.obligations_with_gap ? "red" : undefined} />
          <Stat label="Actions correctives attendues" value={s.pending_corrective_actions} tone={s.pending_corrective_actions ? "orange" : undefined} />
          <Stat label="Dossiers en cours" value={s.open_cases} />
          <Stat label="Félicitations reçues" value={s.congratulations} tone="green" />
        </div>
      )}
      <Supervision own />
    </div>
  )
}

type PubOverview = { publications: Record<string, number>; comments_pending: number; comments_reported: number; surveys: Record<string, number>; surveys_pending_approval: number; responses_total: number }

export function PublisherHome() {
  const o = useFetch<PubOverview>("/publications/overview/")
  const d = o.data
  const n = (m: Record<string, number>, k: string) => m[k] ?? 0
  return (
    <div className="page-stack">
      <PageHeader title="Vue d'ensemble éditoriale" subtitle="Publications, sondages et modération des commentaires." />
      {o.error && <ErrorMsg>{o.error}</ErrorMsg>}
      {o.loading && <Loading />}
      {d && (
        <>
          {d.surveys_pending_approval > 0 && <Notice>{d.surveys_pending_approval} sondage(s) d'opérateurs attendent votre validation. <Link className="link-btn" to="/publications-admin/sondages">Examiner</Link></Notice>}
          <div className="kpi-grid">
            <Stat label="Publications publiées" value={n(d.publications, "PUBLISHED")} hint={`${n(d.publications, "DRAFT")} brouillon(s) · ${n(d.publications, "SCHEDULED")} planifiée(s)`} />
            <Stat label="Commentaires à modérer" value={d.comments_pending} tone={d.comments_pending ? "orange" : undefined} hint={`${d.comments_reported} signalé(s)`} />
            <Stat label="Sondages ouverts" value={n(d.surveys, "PUBLISHED")} hint={`${n(d.surveys, "DRAFT")} brouillon(s) · ${n(d.surveys, "CLOSED")} clos`} />
            <Stat label="Réponses collectées" value={d.responses_total} />
          </div>
        </>
      )}
    </div>
  )
}
