import { useState } from "react"
import { Link, useParams } from "react-router"
import { Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, Table } from "../components/kit"
import { fmtDate, fmtDateTime } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"

type Complaint = {
  id: number; reference: string; complaint_type: string; category: string; description: string; status: string; organization: string | null
  target_operator: string | null; related_case: number | null; related_decision: number | null; deadline: string | null; conclusion: string; created_at: string
}
type Msg = { id: number; author_kind: string; content: string; is_internal: boolean; created_at: string }
type CaseRow = { id: number; reference_number: string; title: string }
type DecisionRow = { id: number; category: string; decided_at: string }

const TYPES: Record<string, string> = { PUBLIC_COMPLAINT: "Réclamation du public", REPORT: "Signalement du public", OPERATOR_CONTESTATION: "Contestation d'un constat ou d'une décision", REVIEW_REQUEST: "Demande de réexamen" }
const STATUSES: Record<string, string> = { NEW: "Nouvelle", IN_REVIEW: "En traitement", AWAITING_INFO: "Informations demandées", RESOLVED: "Traitée", REJECTED: "Rejetée", CLOSED: "Clôturée" }

export function ComplaintsList({ base }: { base: string }) {
  const { user } = useAuth()
  const regulator = user?.role === "ARTEC_REGULATOR"
  const [status, setStatus] = useState("")
  const list = useFetch<Page<Complaint>>("/complaints/", { status, page_size: 100 })
  const cases = useFetch<Page<CaseRow>>(regulator ? null : "/regulation/cases/", { page_size: 100 })
  const [f, setF] = useState({ complaint_type: "OPERATOR_CONTESTATION", category: "", description: "", related_case: "", related_decision: "" })
  const decisions = useFetch<Page<DecisionRow>>(f.related_case ? "/regulation/decisions/" : null, { case: f.related_case })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const submit = async () => {
    try {
      const c = await api<Complaint>("/complaints/", { method: "POST", body: { ...f, related_case: f.related_case ? Number(f.related_case) : null, related_decision: f.related_decision ? Number(f.related_decision) : null } })
      setMsg({ t: "green", m: `Déposée sous la référence ${c.reference}. L'ARTEC en a été informée.` })
      setF({ ...f, category: "", description: "" }); list.reload()
    } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  return (
    <div className="page-stack">
      <PageHeader title={regulator ? "Réclamations, signalements et contestations" : "Réclamations et contestations"} subtitle={regulator ? "Réclamations du public, signalements et contestations des opérateurs. Les échanges internes ne sont jamais visibles du déposant." : "Contestez un constat ou une décision, demandez un réexamen et suivez les échanges avec l'ARTEC. Vos dépôts ne sont visibles que de vous et de l'ARTEC."} />
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      {!regulator && (
        <Section title="Déposer une contestation ou une demande de réexamen" subtitle="Elle doit viser un dossier ou une décision de l'ARTEC. Vos observations sur une demande d'explication se transmettent directement dans le dossier concerné.">
          <div className="form-stack">
            <div className="form-row">
              <Select label="Nature" value={f.complaint_type} onChange={(e) => setF({ ...f, complaint_type: e.target.value })}><option value="OPERATOR_CONTESTATION">{TYPES.OPERATOR_CONTESTATION}</option><option value="REVIEW_REQUEST">{TYPES.REVIEW_REQUEST}</option></Select>
              <Select label="Dossier concerné" value={f.related_case} onChange={(e) => setF({ ...f, related_case: e.target.value, related_decision: "" })}><option value="">Sélectionner…</option>{cases.data?.results.map((c) => <option key={c.id} value={c.id}>{c.reference_number} — {c.title}</option>)}</Select>
              <Select label="Décision contestée (facultatif)" value={f.related_decision} disabled={!f.related_case} onChange={(e) => setF({ ...f, related_decision: e.target.value })}><option value="">Aucune en particulier</option>{decisions.data?.results.map((d) => <option key={d.id} value={d.id}>Décision #{d.id} — {fmtDate(d.decided_at)}</option>)}</Select>
            </div>
            <Input label="Objet" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} />
            <label className="field"><span className="field-label">Exposé des motifs</span><textarea className="input" rows={4} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
            <div><Button disabled={!f.related_case || !f.category.trim() || f.description.trim().length < 10} onClick={submit}>Déposer</Button></div>
          </div>
        </Section>
      )}
      <Section title="Liste" actions={<Select label="" aria-label="Statut" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Tous les statuts</option>{Object.entries(STATUSES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>}>
        {list.loading && <Loading />}
        {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
        {list.data && list.data.results.length === 0 && <Empty>Aucun élément.</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Référence", "Nature", "Objet", "Organisme", "Statut", "Déposée le"]}>
            {list.data.results.map((c) => (
              <tr key={c.id}><td><Link className="link-btn" to={`${base}/reclamations/${c.id}`}>{c.reference}</Link></td><td>{TYPES[c.complaint_type]}</td><td>{c.category}</td><td>{c.organization ?? c.target_operator ?? "Public"}</td><td>{STATUSES[c.status]}</td><td>{fmtDate(c.created_at)}</td></tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  )
}

export function ComplaintDetail({ base }: { base: string }) {
  const { id } = useParams()
  const { user } = useAuth()
  const regulator = user?.role === "ARTEC_REGULATOR"
  const c = useFetch<Complaint>(`/complaints/${id}/`)
  const msgs = useFetch<Msg[]>(`/complaints/${id}/messages/`)
  const [text, setText] = useState("")
  const [internal, setInternal] = useState(false)
  const [conclusion, setConclusion] = useState("")
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); setMsg({ t: "green", m: ok }); c.reload(); msgs.reload() } catch (e) { setMsg({ t: "red", m: describeError(e) }) } }
  if (c.loading) return <Loading />
  if (c.error || !c.data) return <ErrorMsg>{c.error ?? "Introuvable."}</ErrorMsg>
  const d = c.data
  return (
    <div className="page-stack">
      <Link className="link-btn" to={`${base}/reclamations`}>← Retour</Link>
      <PageHeader title={`${d.reference} — ${d.category}`} subtitle={`${TYPES[d.complaint_type]} · déposée le ${fmtDate(d.created_at)} · statut : ${STATUSES[d.status]}`} />
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Section title="Exposé"><p style={{ whiteSpace: "pre-wrap" }}>{d.description}</p>{d.conclusion && <Notice tone="blue">Conclusion : {d.conclusion}</Notice>}</Section>
      <Section title="Échanges">
        {msgs.data?.length === 0 && <Empty>Aucun message.</Empty>}
        {msgs.data?.map((m) => <div key={m.id} className="stack-sm"><strong>{m.author_kind === "ARTEC" ? "ARTEC" : "Déposant"}{m.is_internal && " (interne)"}</strong><span style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{m.content}</span><span className="ind-meta">{fmtDateTime(m.created_at)}</span></div>)}
        {d.status !== "CLOSED" && (
          <div className="form-stack">
            <label className="field"><span className="field-label">Nouveau message</span><textarea className="input" rows={3} value={text} onChange={(e) => setText(e.target.value)} /></label>
            {regulator && <label style={{ display: "flex", gap: 6, fontSize: 13 }}><input type="checkbox" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> Note interne (invisible du déposant)</label>}
            <div><Button disabled={!text.trim()} onClick={() => run(async () => { await api(`/complaints/${id}/messages/`, { method: "POST", body: { content: text, is_internal: internal } }); setText("") }, "Message envoyé.")}>Envoyer</Button></div>
          </div>
        )}
      </Section>
      {regulator && d.status !== "CLOSED" && (
        <Section title="Traitement" subtitle="Une conclusion motivée est obligatoire pour traiter ou rejeter.">
          <div className="form-stack">
            <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
              <Button variant="secondary" onClick={() => run(() => api(`/complaints/${id}/process/`, { method: "POST", body: { status: "IN_REVIEW" } }), "Prise en charge.")}>Prendre en charge</Button>
              <Button variant="secondary" onClick={() => run(() => api(`/complaints/${id}/process/`, { method: "POST", body: { status: "AWAITING_INFO" } }), "Informations demandées.")}>Demander des informations</Button>
            </div>
            <label className="field"><span className="field-label">Conclusion</span><textarea className="input" rows={3} value={conclusion} onChange={(e) => setConclusion(e.target.value)} /></label>
            <div style={{ display: "flex", gap: 8 }}>
              <Button disabled={!conclusion.trim()} onClick={() => run(() => api(`/complaints/${id}/process/`, { method: "POST", body: { status: "RESOLVED", conclusion } }), "Réclamation traitée.")}>Marquer comme traitée</Button>
              <Button variant="ghost" disabled={!conclusion.trim()} onClick={() => run(() => api(`/complaints/${id}/process/`, { method: "POST", body: { status: "REJECTED", conclusion } }), "Réclamation rejetée.")}>Rejeter</Button>
              <Button variant="secondary" onClick={() => run(() => api(`/complaints/${id}/process/`, { method: "POST", body: { status: "CLOSED" } }), "Clôturée.")}>Clôturer</Button>
            </div>
          </div>
        </Section>
      )}
    </div>
  )
}
