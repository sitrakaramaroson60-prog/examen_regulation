import { useState } from "react"
import { Link, useNavigate, useParams } from "react-router"
import { Plus, Trash2 } from "lucide-react"
import { Badge, Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, Stat, StatusPill, Table } from "../components/kit"
import { fmtDate, fmtNum } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"

type SurveyRow = { id: number; title: string; status: string; organization_code: string; target_operator: string | null; responses_count: number; ends_at: string | null; results_public: boolean; rejection_reason: string }
type QType = "SHORT_TEXT" | "LONG_TEXT" | "SINGLE_CHOICE" | "MULTIPLE_CHOICE" | "SATISFACTION" | "NUMBER" | "YES_NO"
type Q = { text: string; question_type: QType; is_required: boolean; choices: string; qos_metric: string; min_value: string; max_value: string }

const QTYPES: Record<QType, string> = { SATISFACTION: "Échelle de satisfaction (1 à 5)", SINGLE_CHOICE: "Choix unique", MULTIPLE_CHOICE: "Choix multiple", YES_NO: "Oui / non", NUMBER: "Nombre", SHORT_TEXT: "Texte court", LONG_TEXT: "Texte long" }
const blank = (): Q => ({ text: "", question_type: "SATISFACTION", is_required: false, choices: "", qos_metric: "", min_value: "", max_value: "" })

const TEMPLATE: Q[] = [
  { text: "Quelle est votre satisfaction globale concernant ce service ?", question_type: "SATISFACTION", is_required: true, choices: "", qos_metric: "satisfaction", min_value: "", max_value: "" },
  { text: "Quel service avez-vous principalement utilisé ?", question_type: "SINGLE_CHOICE", is_required: true, choices: "Appels vocaux\nInternet mobile\nSMS\nMobile money", qos_metric: "", min_value: "", max_value: "" },
  { text: "Comment jugez-vous la qualité des appels (clarté, absence de coupures) ?", question_type: "SATISFACTION", is_required: false, choices: "", qos_metric: "", min_value: "", max_value: "" },
  { text: "Comment jugez-vous la vitesse de la connexion internet ?", question_type: "SATISFACTION", is_required: false, choices: "", qos_metric: "", min_value: "", max_value: "" },
  { text: "Avez-vous subi une coupure d'appel ou de connexion au cours des 7 derniers jours ?", question_type: "YES_NO", is_required: false, choices: "", qos_metric: "", min_value: "", max_value: "" },
  { text: "Commentaire libre (facultatif)", question_type: "LONG_TEXT", is_required: false, choices: "", qos_metric: "", min_value: "", max_value: "" },
]

export function SurveyManager({ base }: { base: string }) {
  const list = useFetch<Page<SurveyRow>>("/surveys/", { page_size: 100 })
  const { user } = useAuth()
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const act = async (id: number, action: string, body?: unknown) => {
    try { await api(`/surveys/${id}/${action}/`, { method: "POST", body: body ?? {} }); setMsg({ t: "green", m: "Sondage mis à jour." }); list.reload() } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  return (
    <div className="page-stack">
      <PageHeader title="Sondages" subtitle="Recueillez la perception des usagers par opérateur et par région. Les réponses numériques liées à un indicateur alimentent les données de qualité de service."
        actions={<Link to={`${base}/sondages/nouveau`}><Button><Plus size={16} /> Nouveau sondage</Button></Link>} />
      {user?.role === "OPERATOR_USER" && <Notice tone="blue">Les sondages d'un opérateur sont relus par ARTEC Publications avant leur mise en ligne.</Notice>}
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Section title="Mes sondages">
        {list.loading && <Loading />}
        {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
        {list.data && list.data.results.length === 0 && <Empty>Aucun sondage. Créez-en un à partir du modèle « qualité de service ».</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Titre", "Organisme", "Opérateur évalué", "Statut", "Réponses", "Fin", ""]}>
            {list.data.results.map((s) => (
              <tr key={s.id}>
                <td>{s.title}{s.rejection_reason && <div className="ind-meta">Refusé : {s.rejection_reason}</div>}</td><td>{s.organization_code}</td><td>{s.target_operator ?? "Tous"}</td>
                <td><StatusPill status={s.status} /></td><td>{s.responses_count}</td><td>{fmtDate(s.ends_at)}</td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {s.status === "DRAFT" && s.organization_code === user?.organization?.code && <Button size="sm" onClick={() => act(s.id, "publish")}>Publier</Button>}{" "}
                  {s.status === "PENDING_APPROVAL" && (user?.role === "ARTEC_PUBLISHER" || user?.role === "ARTEC_REGULATOR") && <>
                    <Button size="sm" onClick={() => act(s.id, "approve")}>Valider</Button>{" "}
                    <Button size="sm" variant="ghost" onClick={() => { const r = window.prompt("Motif du refus :"); if (r) act(s.id, "reject", { reason: r }) }}>Refuser</Button></>}
                  {s.status === "PUBLISHED" && s.organization_code === user?.organization?.code && <Button size="sm" variant="secondary" onClick={() => act(s.id, "close")}>Clore</Button>}{" "}
                  {s.organization_code === user?.organization?.code && s.status !== "DRAFT" && <Link className="link-btn" to={`${base}/sondages/${s.id}`}>Résultats</Link>}
                </td>
              </tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  )
}

export function SurveyBuilder({ base }: { base: string }) {
  const nav = useNavigate()
  const { user } = useAuth()
  const orgs = useFetch<{ code: string; organization_type: string }[]>("/organizations/")
  const metrics = useFetch<{ metric: string; label: string }[]>("/qos/measurements/metrics/")
  const [f, setF] = useState({ title: "", description: "", target_operator: user?.role === "OPERATOR_USER" ? user.organization?.code ?? "" : "", ends_at: "", estimated_minutes: "4", results_public: false, duplicate_policy: "ONE_PER_DAY" })
  const [qs, setQs] = useState<Q[]>([blank()])
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const setQ = (i: number, patch: Partial<Q>) => setQs((cur) => cur.map((q, j) => (j === i ? { ...q, ...patch } : q)))
  const isChoice = (t: QType) => t === "SINGLE_CHOICE" || t === "MULTIPLE_CHOICE"

  const save = async () => {
    setBusy(true); setError("")
    try {
      const body = {
        title: f.title, description: f.description, target_operator: f.target_operator || null, estimated_minutes: Number(f.estimated_minutes),
        results_public: f.results_public, duplicate_policy: f.duplicate_policy, ends_at: f.ends_at ? new Date(f.ends_at + "T23:59:59").toISOString() : null,
        questions: qs.map((q, i) => ({
          text: q.text, question_type: q.question_type, is_required: q.is_required, order: i, qos_metric: q.qos_metric,
          min_value: q.min_value === "" ? null : Number(q.min_value), max_value: q.max_value === "" ? null : Number(q.max_value),
          choices: isChoice(q.question_type) ? q.choices.split("\n").map((c) => c.trim()).filter(Boolean).map((label, k) => ({ label, order: k })) : [],
        })),
      }
      await api("/surveys/", { method: "POST", body })
      nav(`${base}/sondages`)
    } catch (e) { setError(describeError(e)) } finally { setBusy(false) }
  }
  const operators = orgs.data?.filter((o) => o.organization_type === "OPERATOR") ?? []

  return (
    <div className="page-stack">
      <Link className="link-btn" to={`${base}/sondages`}>← Retour aux sondages</Link>
      <PageHeader title="Nouveau sondage" subtitle="Le sondage est enregistré en brouillon ; vous le publierez depuis la liste." actions={<Button variant="secondary" onClick={() => { setQs(TEMPLATE); if (!f.title) setF({ ...f, title: "Évaluation de la qualité de service" }) }}>Utiliser le modèle « qualité de service »</Button>} />
      {error && <ErrorMsg>{error}</ErrorMsg>}
      <Section title="Informations générales">
        <div className="form-stack">
          <Input label="Titre" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <label className="field"><span className="field-label">Description</span><textarea className="input" rows={2} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <div className="form-row">
            <Select label="Opérateur évalué" value={f.target_operator} disabled={user?.role === "OPERATOR_USER"} onChange={(e) => setF({ ...f, target_operator: e.target.value })}>
              <option value="">Tous / non précisé (le répondant choisit)</option>{operators.map((o) => <option key={o.code}>{o.code}</option>)}
            </Select>
            <Input label="Date de fin (facultatif)" type="date" value={f.ends_at} onChange={(e) => setF({ ...f, ends_at: e.target.value })} />
            <Input label="Durée estimée (min)" type="number" value={f.estimated_minutes} onChange={(e) => setF({ ...f, estimated_minutes: e.target.value })} />
            <Select label="Limitation des réponses répétées" value={f.duplicate_policy} onChange={(e) => setF({ ...f, duplicate_policy: e.target.value })}>
              <option value="ONE_PER_DAY">Une réponse par jour et par navigateur</option><option value="ONE_TOTAL">Une seule réponse par navigateur</option><option value="NONE">Aucune (limitation de débit seulement)</option>
            </Select>
          </div>
          <label style={{ display: "flex", gap: 8, fontSize: 13 }}><input type="checkbox" checked={f.results_public} onChange={(e) => setF({ ...f, results_public: e.target.checked })} /> Rendre les résultats agrégés publics (jamais de texte libre, seuil minimal de réponses)</label>
          <Notice tone="blue">La région, la ville et le contexte (résidence ou lieu d'utilisation) sont demandés automatiquement à chaque répondant. Aucune adresse, GPS ni identité n'est collecté.</Notice>
        </div>
      </Section>

      <Section title="Questions" actions={<Button variant="secondary" onClick={() => setQs([...qs, blank()])}><Plus size={14} /> Ajouter une question</Button>}>
        <div className="form-stack">
          {qs.map((q, i) => (
            <div className="q-editor" key={i}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}><Badge>Question {i + 1}</Badge>{qs.length > 1 && <Button size="sm" variant="ghost" aria-label="Supprimer" onClick={() => setQs(qs.filter((_, j) => j !== i))}><Trash2 size={14} /></Button>}</div>
              <Input label="Intitulé" value={q.text} onChange={(e) => setQ(i, { text: e.target.value })} />
              <div className="form-row">
                <Select label="Type de réponse" value={q.question_type} onChange={(e) => setQ(i, { question_type: e.target.value as QType, qos_metric: "" })}>{Object.entries(QTYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
                {(q.question_type === "SATISFACTION" || q.question_type === "NUMBER") && (
                  <Select label="Alimente l'indicateur QoS" value={q.qos_metric} onChange={(e) => setQ(i, { qos_metric: e.target.value })}>
                    <option value="">Aucun (analyse du sondage seulement)</option>
                    {metrics.data?.filter((m) => (q.question_type === "SATISFACTION" ? m.metric === "satisfaction" : true)).map((m) => <option key={m.metric} value={m.metric}>{m.label}</option>)}
                  </Select>
                )}
                {q.question_type === "NUMBER" && <><Input label="Minimum" type="number" value={q.min_value} onChange={(e) => setQ(i, { min_value: e.target.value })} /><Input label="Maximum" type="number" value={q.max_value} onChange={(e) => setQ(i, { max_value: e.target.value })} /></>}
              </div>
              {isChoice(q.question_type) && <label className="field"><span className="field-label">Choix (un par ligne, deux minimum)</span><textarea className="input" rows={3} value={q.choices} onChange={(e) => setQ(i, { choices: e.target.value })} /></label>}
              <label style={{ display: "flex", gap: 8, fontSize: 13 }}><input type="checkbox" checked={q.is_required} onChange={(e) => setQ(i, { is_required: e.target.checked })} /> Réponse obligatoire</label>
            </div>
          ))}
        </div>
      </Section>
      <div><Button loading={busy} disabled={!f.title.trim() || qs.some((q) => !q.text.trim())} onClick={save}>Enregistrer le brouillon</Button></div>
    </div>
  )
}

type Results = {
  title: string; total_responses: number; suppressed?: boolean; message?: string
  by_region: { region: string; count: number }[]
  questions: { id: number; text: string; type: string; answered: number; average?: number | null; yes?: number; no?: number; choices?: { id: number; label: string; count: number }[]; texts?: string[] }[]
}

export function SurveyResults({ base }: { base: string }) {
  const { id } = useParams()
  const r = useFetch<Results>(`/surveys/${id}/results/`)
  if (r.loading) return <Loading />
  if (r.error || !r.data) return <ErrorMsg>{r.error ?? "Résultats indisponibles."}</ErrorMsg>
  const d = r.data
  return (
    <div className="page-stack">
      <Link className="link-btn" to={`${base}/sondages`}>← Retour aux sondages</Link>
      <PageHeader title={d.title} subtitle="Résultats agrégés et anonymes." />
      <div className="kpi-grid"><Stat label="Réponses" value={d.total_responses} /><Stat label="Régions représentées" value={d.by_region.length} /></div>
      {d.suppressed && <Notice>{d.message}</Notice>}
      <Section title="Répartition par région">
        {d.by_region.length === 0 ? <Empty>Aucune donnée.</Empty> : <Table head={["Région", "Réponses"]}>{d.by_region.map((x) => <tr key={x.region}><td>{x.region}</td><td>{x.count}</td></tr>)}</Table>}
      </Section>
      {d.questions.map((q) => (
        <Section key={q.id} title={q.text} subtitle={`${q.answered} réponse(s)`}>
          {q.choices && q.choices.map((c) => { const max = Math.max(...q.choices!.map((x) => x.count), 1); return <div className="op-row" key={c.id} style={{ gridTemplateColumns: "minmax(120px,1fr) 2fr auto" }}><span>{c.label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${(c.count / max) * 100}%` }} /></div><span className="val">{c.count}</span></div> })}
          {q.average !== undefined && q.average !== null && <strong>Moyenne : {fmtNum(q.average)}</strong>}
          {q.yes !== undefined && <span>Oui : {q.yes} · Non : {q.no}</span>}
          {q.texts && q.texts.length > 0 && <ul>{q.texts.slice(0, 30).map((t, i) => <li key={i} style={{ fontSize: 14 }}>{t}</li>)}</ul>}
        </Section>
      ))}
    </div>
  )
}
