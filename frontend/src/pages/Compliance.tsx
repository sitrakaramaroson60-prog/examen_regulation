import { useState } from "react"
import { Link } from "react-router"
import { Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, Stat, StatusPill, Table, Tabs } from "../components/kit"
import { fmtDate, fmtDateTime, fmtNum } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"

type Eval = { status: string; measured_value: number | null; gap: number | null; gap_pct: number | null; sample_count?: number; samples?: number; evaluated_at: string }
type Obligation = {
  id: number; operator: string; title: string; legal_basis: string; metric_name: string; unit: string; comparison: "GTE" | "LTE"; target_value: number
  measurement_method: string; technology: string; is_active: boolean; latest_evaluation: Eval | null
}
type Alert = { id: number; operator: string; obligation_title: string; severity: string; status: string; message: string; measured_value: number; nature: string; cases: number[]; created_at: string }
type Metric = { metric: string; label: string; unit: string; higher_is_better: boolean }
type Org = { id: number; code: string; organization_type: string; name: string }
type Check = { id: number; case: string; operator: string; action_description: string; due_date: string; status: string; outcome: string; notes: string }
type FileSummary = { operator: { code: string; name: string }; obligations_total: number; obligations_evaluated: number; obligations_compliant: number; obligations_with_gap: number; open_cases: number; awaiting_response: number; warnings: number; congratulations: number; pending_corrective_actions: number; open_alerts?: number }

export default function Compliance() {
  const [tab, setTab] = useState<"obligations" | "alerts" | "files" | "checks">("obligations")
  return (
    <div className="page-stack">
      <PageHeader title="Obligations et conformité" subtitle="Engagements des opérateurs, résultats mesurés, écarts détectés et suites données. Une alerte algorithmique n'est jamais une décision réglementaire." />
      <Tabs tabs={[["obligations", "Engagements"], ["alerts", "Alertes algorithmiques"], ["files", "Dossiers par opérateur"], ["checks", "Contrôles de suivi"]]} value={tab} onChange={setTab} />
      {tab === "obligations" && <Obligations />}
      {tab === "alerts" && <Alerts />}
      {tab === "files" && <OperatorFiles />}
      {tab === "checks" && <Checks />}
    </div>
  )
}

function Obligations() {
  const list = useFetch<Page<Obligation>>("/regulation/obligations/", { page_size: 200 })
  const metrics = useFetch<Metric[]>("/qos/measurements/metrics/")
  const orgs = useFetch<Org[]>("/organizations/")
  const [form, setForm] = useState({ operator: "", title: "", legal_basis: "", metric_name: "availability", comparison: "GTE", target_value: "", measurement_method: "", technology: "", evaluation_window_days: "30", min_samples: "10", valid_from: new Date().toISOString().slice(0, 10) })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const [busy, setBusy] = useState("")
  const metric = metrics.data?.find((m) => m.metric === form.metric_name)
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }))

  const run = async (label: string, fn: () => Promise<string | void>) => {
    setBusy(label); setMsg(null)
    try { const m = await fn(); if (m) setMsg({ t: "green", m }); list.reload() } catch (e) { setMsg({ t: "red", m: describeError(e) }) } finally { setBusy("") }
  }
  const create = () => run("create", async () => {
    await api("/regulation/obligations/", { method: "POST", body: { ...form, unit: metric?.unit, target_value: Number(form.target_value), evaluation_window_days: Number(form.evaluation_window_days), min_samples: Number(form.min_samples) } })
    setForm((f) => ({ ...f, title: "", legal_basis: "", target_value: "" }))
    return "Engagement enregistré."
  })
  const evaluate = (o: Obligation) => run(`e${o.id}`, async () => {
    const r = await api<{ evaluation: Eval; alert: Alert | null }>(`/regulation/obligations/${o.id}/evaluate/`, { method: "POST" })
    return r.alert ? "Écart détecté : une alerte algorithmique a été créée (onglet Alertes)." : `Évaluation : ${r.evaluation.status === "COMPLIANT" ? "conforme" : r.evaluation.status === "INSUFFICIENT_DATA" ? "données insuffisantes" : "écart"}.`
  })
  const all = () => run("all", async () => {
    const r = await api<{ evaluated: number; alerts: number }>("/regulation/obligations/evaluate-all/", { method: "POST" })
    return `${r.evaluated} engagement(s) évalué(s), ${r.alerts} nouvelle(s) alerte(s).`
  })
  const operators = orgs.data?.filter((o) => o.organization_type === "OPERATOR") ?? []

  return (
    <>
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Section title="Engagements en vigueur" subtitle="Seules les mesures techniques validées, selon la méthode de référence de chaque engagement, sont évaluées."
        actions={<Button variant="secondary" loading={busy === "all"} onClick={all}>Évaluer tous les engagements</Button>}>
        {list.loading && <Loading />}
        {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
        {list.data && list.data.results.length === 0 && <Empty>Aucun engagement enregistré. Ajoutez-les ci-dessous à partir des textes applicables (cahier des charges, décisions, conventions).</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Opérateur", "Engagement", "Cible", "Dernier résultat", "Statut", ""]}>
            {list.data.results.map((o) => (
              <tr key={o.id}>
                <td><strong>{o.operator}</strong></td>
                <td>{o.title}<div className="ind-meta">{o.legal_basis} · méthode « {o.measurement_method} »{o.technology ? ` · ${o.technology}` : ""}</div></td>
                <td>{o.comparison === "GTE" ? "≥" : "≤"} {fmtNum(o.target_value)} {o.unit}</td>
                <td>{o.latest_evaluation?.measured_value != null ? `${fmtNum(o.latest_evaluation.measured_value)} ${o.unit}` : "—"}<div className="ind-meta">{o.latest_evaluation ? fmtDateTime(o.latest_evaluation.evaluated_at) : "Jamais évalué"}</div></td>
                <td><StatusPill status={o.latest_evaluation?.status ?? "INSUFFICIENT_DATA"} /></td>
                <td><Button size="sm" variant="secondary" loading={busy === `e${o.id}`} onClick={() => evaluate(o)}>Évaluer</Button></td>
              </tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Ajouter un engagement" subtitle="Les valeurs cibles et leur base juridique sont celles de l'ARTEC : aucune valeur officielle n'est préremplie.">
        <div className="form-stack">
          <div className="form-row">
            <Select label="Opérateur" value={form.operator} onChange={(e) => set("operator", e.target.value)}><option value="">Sélectionner…</option>{operators.map((o) => <option key={o.code}>{o.code}</option>)}</Select>
            <Input label="Intitulé" value={form.title} onChange={(e) => set("title", e.target.value)} />
          </div>
          <Input label="Base juridique (texte, décision, convention)" value={form.legal_basis} onChange={(e) => set("legal_basis", e.target.value)} />
          <div className="form-row">
            <Select label="Indicateur" value={form.metric_name} onChange={(e) => { set("metric_name", e.target.value); set("comparison", metrics.data?.find((m) => m.metric === e.target.value)?.higher_is_better ? "GTE" : "LTE") }}>
              {metrics.data?.filter((m) => m.metric !== "satisfaction").map((m) => <option key={m.metric} value={m.metric}>{m.label}</option>)}
            </Select>
            <Select label="Condition" value={form.comparison} onChange={(e) => set("comparison", e.target.value)}><option value="GTE">Au moins (≥)</option><option value="LTE">Au plus (≤)</option></Select>
            <Input label={`Valeur cible (${metric?.unit ?? ""})`} type="number" step="any" value={form.target_value} onChange={(e) => set("target_value", e.target.value)} />
          </div>
          <div className="form-row">
            <Input label="Méthode de mesure de référence" value={form.measurement_method} onChange={(e) => set("measurement_method", e.target.value)} />
            <Input label="Technologie (facultatif)" value={form.technology} onChange={(e) => set("technology", e.target.value)} />
            <Input label="Fenêtre d'évaluation (jours)" type="number" value={form.evaluation_window_days} onChange={(e) => set("evaluation_window_days", e.target.value)} />
            <Input label="Mesures minimales" type="number" value={form.min_samples} onChange={(e) => set("min_samples", e.target.value)} />
            <Input label="En vigueur depuis" type="date" value={form.valid_from} onChange={(e) => set("valid_from", e.target.value)} />
          </div>
          <div><Button loading={busy === "create"} disabled={!form.operator || !form.title || !form.legal_basis || !form.target_value || !form.measurement_method} onClick={create}>Enregistrer l'engagement</Button></div>
        </div>
      </Section>
    </>
  )
}

function Alerts() {
  const [status, setStatus] = useState("NEW")
  const list = useFetch<Page<Alert>>("/regulation/alerts/", { status, page_size: 100 })
  const [msg, setMsg] = useState<string | null>(null)
  const act = async (a: Alert, action: "acknowledge" | "dismiss" | "escalate") => {
    let note = ""
    if (action === "dismiss") { const n = window.prompt("Motif du classement sans suite (obligatoire) :"); if (!n) return; note = n }
    try {
      await api(`/regulation/alerts/${a.id}/${action}/`, { method: "POST", body: { note } })
      setMsg(action === "escalate" ? "Dossier réglementaire ouvert à partir de l'alerte (menu Dossiers réglementaires)." : "Alerte mise à jour.")
      list.reload()
    } catch (e) { setMsg(describeError(e)) }
  }
  return (
    <Section title="Alertes algorithmiques" subtitle="Produites automatiquement lorsqu'un engagement n'est pas respecté. Elles n'ont aucune valeur de décision : un agent habilité les examine puis ouvre, ou non, un dossier."
      actions={<Select label="" aria-label="Statut" value={status} onChange={(e) => setStatus(e.target.value)}><option value="NEW">Nouvelles</option><option value="ACKNOWLEDGED">Prises en compte</option><option value="ESCALATED">Dossier ouvert</option><option value="DISMISSED">Sans suite</option></Select>}>
      {msg && <Notice tone="blue">{msg}</Notice>}
      {list.loading && <Loading />}
      {list.data && list.data.results.length === 0 && <Empty>Aucune alerte dans cet état.</Empty>}
      {list.data && list.data.results.length > 0 && (
        <Table head={["Gravité", "Opérateur", "Constat", "Date", ""]}>
          {list.data.results.map((a) => (
            <tr key={a.id}>
              <td><StatusPill status={a.severity} /></td><td><strong>{a.operator}</strong></td>
              <td>{a.message}<div className="ind-meta">{a.nature}</div></td><td>{fmtDate(a.created_at)}</td>
              <td style={{ whiteSpace: "nowrap" }}>
                {(a.status === "NEW" || a.status === "ACKNOWLEDGED") ? (
                  <>
                    {a.status === "NEW" && <Button size="sm" variant="secondary" onClick={() => act(a, "acknowledge")}>Prendre en compte</Button>}{" "}
                    <Button size="sm" onClick={() => act(a, "escalate")}>Ouvrir un dossier</Button>{" "}
                    <Button size="sm" variant="ghost" onClick={() => act(a, "dismiss")}>Sans suite</Button>
                  </>
                ) : a.cases.length > 0 ? <Link className="link-btn" to={`/regulation/dossiers/${a.cases[0]}`}>Voir le dossier</Link> : <StatusPill status={a.status} />}
              </td>
            </tr>
          ))}
        </Table>
      )}
    </Section>
  )
}

type OperatorFile = {
  operator: { code: string; name: string }
  summary: FileSummary
  obligations: (Obligation & { latest_evaluation: Eval | null })[]
  quality_last_30_days: { metric: string; label: string; average: number; unit: string; status: string | null }[]
  cases: { id: number; reference_number: string; title: string; status: string; deadline: string | null }[]
  decisions: { id: number; case: string; category: string; decided_at: string }[]
  corrective_actions: { id: number; case: string; description: string; due_date: string; status: string }[]
  planned_checks: { id: number; due_date: string; action: string }[]
  alerts?: { id: number; severity: string; status: string; message: string; created_at: string }[]
}

const DECISION_LABELS: Record<string, string> = { WARNING: "Avertissement", CONGRATULATIONS: "Félicitations", EXPLANATION_REQUEST: "Demande d'explication", RECOMMENDATION: "Recommandation", CORRECTION_REQUEST: "Demande de correction", NO_BREACH: "Aucun manquement établi", CLOSURE: "Clôture" }

function OperatorFiles() {
  const idx = useFetch<FileSummary[]>("/regulation/operator-files/")
  const [code, setCode] = useState("")
  return (
    <>
      <Section title="Vue comparée des opérateurs" subtitle="Cliquez sur un opérateur pour ouvrir son dossier de suivi.">
        {idx.loading && <Loading />}
        {idx.error && <ErrorMsg>{idx.error}</ErrorMsg>}
        {idx.data && (
          <Table head={["Opérateur", "Engagements conformes", "Écarts", "Alertes ouvertes", "Dossiers ouverts", "Avertissements", "Félicitations", ""]}>
            {idx.data.map((f) => (
              <tr key={f.operator.code}>
                <td><strong>{f.operator.code}</strong></td><td>{f.obligations_compliant} / {f.obligations_evaluated}</td><td>{f.obligations_with_gap}</td><td>{f.open_alerts ?? 0}</td>
                <td>{f.open_cases}</td><td>{f.warnings}</td><td>{f.congratulations}</td>
                <td><button className="link-btn" onClick={() => setCode(f.operator.code)}>Ouvrir le dossier</button></td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
      {code && <OperatorFileView code={code} regulator />}
    </>
  )
}

export function OperatorFileView({ code, regulator = false }: { code: string; regulator?: boolean }) {
  const f = useFetch<OperatorFile>(`/regulation/operator-files/${code}/`)
  const base = regulator ? "/regulation" : "/operateur"
  if (f.loading) return <Loading />
  if (f.error) return <ErrorMsg>{f.error}</ErrorMsg>
  const d = f.data
  if (!d) return null
  const s = d.summary
  return (
    <div className="page-stack">
      <div className="kpi-grid">
        <Stat label="Engagements conformes" value={`${s.obligations_compliant} / ${s.obligations_evaluated}`} hint={`${s.obligations_total} engagement(s) au total`} tone={s.obligations_with_gap ? "orange" : "green"} />
        <Stat label="Écarts détectés" value={s.obligations_with_gap} tone={s.obligations_with_gap ? "red" : undefined} />
        <Stat label="Dossiers en cours" value={s.open_cases} hint={`${s.awaiting_response} en attente de réponse`} />
        <Stat label="Actions correctives attendues" value={s.pending_corrective_actions} tone={s.pending_corrective_actions ? "orange" : undefined} />
        <Stat label="Avertissements" value={s.warnings} /><Stat label="Félicitations" value={s.congratulations} tone="green" />
      </div>
      <Section title={`${d.operator.name} — engagements et résultats mesurés`}>
        {d.obligations.length === 0 ? <Empty>Aucun engagement enregistré pour cet opérateur.</Empty> : (
          <Table head={["Engagement", "Cible", "Résultat mesuré", "Écart", "Statut"]}>
            {d.obligations.map((o) => (
              <tr key={o.id}><td>{o.title}<div className="ind-meta">{o.legal_basis}</div></td><td>{o.comparison === "GTE" ? "≥" : "≤"} {fmtNum(o.target_value)} {o.unit}</td>
                <td>{o.latest_evaluation?.measured_value != null ? `${fmtNum(o.latest_evaluation.measured_value)} ${o.unit}` : "—"}</td>
                <td>{o.latest_evaluation?.gap != null ? `${fmtNum(o.latest_evaluation.gap)} (${fmtNum(o.latest_evaluation.gap_pct, 1)} %)` : "—"}</td>
                <td><StatusPill status={o.latest_evaluation?.status ?? "INSUFFICIENT_DATA"} /></td></tr>
            ))}
          </Table>
        )}
      </Section>
      <div className="grid-2">
        <Section title="Qualité mesurée (30 derniers jours)" subtitle="Moyennes des mesures techniques validées.">
          {d.quality_last_30_days.length === 0 ? <Empty>Aucune mesure sur la période.</Empty> : (
            <Table head={["Indicateur", "Moyenne", "Niveau"]}>{d.quality_last_30_days.map((q) => <tr key={q.metric}><td>{q.label}</td><td>{fmtNum(q.average)} {q.unit}</td><td><StatusPill status={q.status} /></td></tr>)}</Table>
          )}
        </Section>
        <Section title="Actions correctives attendues" subtitle="Plans correctifs en cours et contrôles de suivi planifiés.">
          {d.corrective_actions.length === 0 ? <Empty>Aucune action corrective en cours.</Empty> : (
            <Table head={["Dossier", "Action", "Échéance", "Statut"]}>{d.corrective_actions.map((a) => <tr key={a.id}><td>{a.case}</td><td>{a.description}</td><td>{fmtDate(a.due_date)}</td><td><StatusPill status={a.status} /></td></tr>)}</Table>
          )}
          {d.planned_checks.map((c) => <span className="ind-meta" key={c.id}>Contrôle de suivi prévu le {fmtDate(c.due_date)} — {c.action}</span>)}
        </Section>
      </div>
      <div className="grid-2">
        <Section title="Dossiers réglementaires">
          {d.cases.length === 0 ? <Empty>Aucun dossier.</Empty> : (
            <Table head={["Référence", "Objet", "Statut"]}>{d.cases.map((c) => <tr key={c.id}><td><Link className="link-btn" to={`${base}/dossiers/${c.id}`}>{c.reference_number}</Link></td><td>{c.title}</td><td><StatusPill status={c.status} /></td></tr>)}</Table>
          )}
        </Section>
        <Section title="Décisions formelles en vigueur" subtitle="Avertissements, demandes de correction, félicitations officielles…">
          {d.decisions.length === 0 ? <Empty>Aucune décision.</Empty> : (
            <Table head={["Date", "Dossier", "Décision"]}>{d.decisions.map((x) => <tr key={x.id}><td>{fmtDate(x.decided_at)}</td><td>{x.case}</td><td><strong>{DECISION_LABELS[x.category] ?? x.category}</strong></td></tr>)}</Table>
          )}
        </Section>
      </div>
      {d.alerts && d.alerts.length > 0 && (
        <Section title="Alertes algorithmiques (internes à l'ARTEC)" subtitle="Indications automatiques, sans valeur de décision.">
          <Table head={["Gravité", "Constat", "Statut", "Date"]}>{d.alerts.map((a) => <tr key={a.id}><td><StatusPill status={a.severity} /></td><td>{a.message}</td><td><StatusPill status={a.status} /></td><td>{fmtDate(a.created_at)}</td></tr>)}</Table>
        </Section>
      )}
    </div>
  )
}

function Checks() {
  const list = useFetch<Page<Check>>("/regulation/checks/", { page_size: 100 })
  const { user } = useAuth()
  const complete = async (c: Check, outcome: string) => {
    const notes = window.prompt("Constat du contrôle (obligatoire) :")
    if (!notes) return
    try { await api(`/regulation/checks/${c.id}/complete/`, { method: "POST", body: { outcome, notes } }); list.reload() } catch (e) { window.alert(describeError(e)) }
  }
  return (
    <Section title="Contrôles de suivi" subtitle="Vérifications planifiées après une demande de correction. Planifiez-les depuis le détail d'un dossier.">
      {list.loading && <Loading />}
      {list.data && list.data.results.length === 0 && <Empty>Aucun contrôle planifié.</Empty>}
      {list.data && list.data.results.length > 0 && (
        <Table head={["Opérateur", "Dossier", "Action contrôlée", "Échéance", "Statut", ""]}>
          {list.data.results.map((c) => (
            <tr key={c.id}><td><strong>{c.operator}</strong></td><td>{c.case}</td><td>{c.action_description}</td><td>{fmtDate(c.due_date)}</td>
              <td><StatusPill status={c.status} /> {c.outcome && <StatusPill status={c.outcome} />}<div className="ind-meta">{c.notes}</div></td>
              <td style={{ whiteSpace: "nowrap" }}>{user?.role === "ARTEC_REGULATOR" && c.status === "PLANNED" && (
                <>
                  <Button size="sm" variant="secondary" onClick={() => complete(c, "COMPLIANT")}>Conforme</Button>{" "}
                  <Button size="sm" variant="secondary" onClick={() => complete(c, "PARTIAL")}>Partiel</Button>{" "}
                  <Button size="sm" variant="ghost" onClick={() => complete(c, "NON_COMPLIANT")}>Non conforme</Button>
                </>
              )}</td></tr>
          ))}
        </Table>
      )}
    </Section>
  )
}

/** Page « Ma conformité » de l'espace opérateur. */
export function MyCompliance() {
  return (
    <div className="page-stack">
      <PageHeader title="Ma conformité" subtitle="Vos engagements, les résultats mesurés par l'ARTEC, les écarts relevés et les actions correctives attendues." />
      <OperatorFileView code="me" />
    </div>
  )
}
