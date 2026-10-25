import { useState } from "react"
import { Link, useParams } from "react-router"
import { Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, StatusPill, Table } from "../components/kit"
import { fmtDate, fmtDateTime } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useAuth } from "../lib/auth-context"
import { useFetch } from "../lib/useFetch"

type Case = {
  id: number; reference_number: string; operator: string; case_type: string; status: string; title: string; description: string
  deadline: string | null; opened_at: string; closed_at: string | null; related_alert: number | null
}
type Ev = { id: number; kind: string; actor: string | null; message: string; internal: boolean; created_at: string }
type Evidence = { id: number; kind: string; description: string; visible_to_operator: boolean; created_at: string }
type Decision = { id: number; category: string; justification: string; decided_by: string; decided_at: string; is_current: boolean; supersedes: number | null; amendment_reason: string }
type Action = { id: number; description: string; due_date: string; status: string; operator_report: string; verification_comment: string }
type Resp = { id: number; responder: string; content: string; created_at: string }

const CASE_TYPES: Record<string, string> = { QOS_ANOMALY: "Anomalie de qualité de service", DATA_QUALITY: "Qualité des données transmises", COMPLAINT_FOLLOWUP: "Suite à réclamation", OBLIGATION_FOLLOWUP: "Suivi d'une obligation", RECOGNITION: "Reconnaissance (félicitations)", OTHER: "Autre" }
const DECISIONS: Record<string, string> = { EXPLANATION_REQUEST: "Demande d'explication", RECOMMENDATION: "Recommandation", CORRECTION_REQUEST: "Demande de correction", WARNING: "Avertissement", CONGRATULATIONS: "Félicitations officielles", NO_BREACH: "Absence de manquement établi", CLOSURE: "Clôture" }
const KIND: Record<string, string> = { OPENED: "Ouverture", EXPLANATION_REQUESTED: "Demande d'explication", OPERATOR_RESPONSE: "Réponse de l'opérateur", EVIDENCE_ADDED: "Élément de preuve", DECISION: "Décision", DECISION_AMENDED: "Décision modifiée", CORRECTIVE_ACTION: "Action corrective", NOTE: "Note interne", CLOSED: "Clôture", STATUS_CHANGE: "Changement de statut" }

export function CasesList({ regulator }: { regulator: boolean }) {
  const base = regulator ? "/regulation" : "/operateur"
  const orgs = useFetch<{ code: string; organization_type: string }[]>("/organizations/", undefined, true)
  const [status, setStatus] = useState("")
  const list = useFetch<Page<Case>>("/regulation/cases/", { status, page_size: 100 })
  const [f, setF] = useState({ operator: "", case_type: "QOS_ANOMALY", title: "", description: "", deadline: "" })
  const [msg, setMsg] = useState<string | null>(null)
  const create = async () => {
    try {
      await api("/regulation/cases/", { method: "POST", body: { ...f, deadline: f.deadline || null } })
      setF({ ...f, title: "", description: "" }); setMsg("Dossier ouvert."); list.reload()
    } catch (e) { setMsg(describeError(e)) }
  }
  return (
    <div className="page-stack">
      <PageHeader title="Dossiers réglementaires" subtitle={regulator ? "Demandes d'explication, décisions motivées, plans correctifs et félicitations officielles." : "Dossiers ouverts à votre sujet : consultez les demandes de l'ARTEC et transmettez vos réponses."} />
      {regulator && (
        <Section title="Ouvrir un dossier" subtitle="Un dossier peut aussi être ouvert à partir d'une alerte algorithmique (menu Obligations et conformité).">
          {msg && <Notice tone="blue">{msg}</Notice>}
          <div className="form-row">
            <Select label="Opérateur" value={f.operator} onChange={(e) => setF({ ...f, operator: e.target.value })}><option value="">Sélectionner…</option>{orgs.data?.filter((o) => o.organization_type === "OPERATOR").map((o) => <option key={o.code}>{o.code}</option>)}</Select>
            <Select label="Nature" value={f.case_type} onChange={(e) => setF({ ...f, case_type: e.target.value })}>{Object.entries(CASE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
            <Input label="Échéance (facultatif)" type="date" value={f.deadline} onChange={(e) => setF({ ...f, deadline: e.target.value })} />
          </div>
          <Input label="Objet" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />
          <label className="field"><span className="field-label">Description</span><textarea className="input" rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <div><Button disabled={!f.operator || !f.title || !f.description} onClick={create}>Ouvrir le dossier</Button></div>
        </Section>
      )}
      <Section title="Liste des dossiers" actions={<Select label="" aria-label="Statut" value={status} onChange={(e) => setStatus(e.target.value)}><option value="">Tous les statuts</option>{["OPEN", "UNDER_REVIEW", "AWAITING_OPERATOR_RESPONSE", "UNDER_CORRECTION", "DECIDED", "CLOSED"].map((s) => <option key={s} value={s}>{s}</option>)}</Select>}>
        {list.loading && <Loading />}
        {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
        {list.data && list.data.results.length === 0 && <Empty>Aucun dossier.</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Référence", "Opérateur", "Objet", "Nature", "Statut", "Échéance"]}>
            {list.data.results.map((c) => (
              <tr key={c.id}><td><Link className="link-btn" to={`${base}/dossiers/${c.id}`}>{c.reference_number}</Link></td><td><strong>{c.operator}</strong></td><td>{c.title}</td>
                <td>{CASE_TYPES[c.case_type]}</td><td><StatusPill status={c.status} /></td><td>{fmtDate(c.deadline)}</td></tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  )
}

export function CaseDetail() {
  const { id } = useParams()
  const { user } = useAuth()
  const regulator = user?.role === "ARTEC_REGULATOR"
  const base = regulator ? "/regulation" : "/operateur"
  const c = useFetch<Case>(`/regulation/cases/${id}/`)
  const timeline = useFetch<Ev[]>(`/regulation/cases/${id}/timeline/`)
  const evidence = useFetch<Evidence[]>(`/regulation/cases/${id}/evidence/`)
  const responses = useFetch<Resp[]>(`/regulation/cases/${id}/responses/`)
  const decisions = useFetch<Page<Decision>>("/regulation/decisions/", { case: id })
  const actions = useFetch<Action[]>(`/regulation/cases/${id}/corrective-actions/`)
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const [f, setF] = useState({ explanation: "", deadline: "", evKind: "DOCUMENT", evDesc: "", evVisible: true, dCat: "RECOMMENDATION", dText: "", dEvidence: [] as number[], aDesc: "", aDue: "", note: "", reply: "" })
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }))

  const reloadAll = () => { c.reload(); timeline.reload(); evidence.reload(); responses.reload(); decisions.reload(); actions.reload() }
  const run = async (fn: () => Promise<unknown>, ok: string) => {
    try { await fn(); setMsg({ t: "green", m: ok }); reloadAll() } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  const post = (path: string, body?: unknown) => api(`/regulation/${path}`, { method: "POST", body: body ?? {} })

  if (c.loading) return <Loading />
  if (c.error || !c.data) return <ErrorMsg>{c.error ?? "Dossier introuvable."}</ErrorMsg>
  const cs = c.data
  const closed = cs.status === "CLOSED"

  return (
    <div className="page-stack">
      <Link className="link-btn" to={`${base}/dossiers`}>← Retour aux dossiers</Link>
      <PageHeader title={`${cs.reference_number} — ${cs.title}`} subtitle={`${cs.operator} · ${CASE_TYPES[cs.case_type]} · ouvert le ${fmtDate(cs.opened_at)}${cs.deadline ? ` · échéance ${fmtDate(cs.deadline)}` : ""}`} actions={<StatusPill status={cs.status} />} />
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
      <Section title="Exposé"><p style={{ whiteSpace: "pre-wrap" }}>{cs.description}</p></Section>

      <div className="grid-2">
        <Section title="Décisions formelles" subtitle="Chaque décision est motivée, datée, signée par un agent habilité et rattachée à des preuves.">
          {decisions.data?.results.length === 0 && <Empty>Aucune décision rendue.</Empty>}
          {decisions.data?.results.map((d) => (
            <div key={d.id} className="stack-sm" style={{ opacity: d.is_current ? 1 : 0.55 }}>
              <div><strong>{DECISIONS[d.category]}</strong> {!d.is_current && <span className="ind-meta">(remplacée)</span>}</div>
              <p style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{d.justification}</p>
              <span className="ind-meta">{d.decided_by} · {fmtDateTime(d.decided_at)}{d.amendment_reason ? ` · modification : ${d.amendment_reason}` : ""}</span>
            </div>
          ))}
        </Section>
        <Section title="Éléments de preuve">
          {evidence.data?.length === 0 && <Empty>Aucun élément.</Empty>}
          {evidence.data?.map((e) => <div key={e.id} className="stack-sm"><strong>#{e.id} · {e.kind}</strong><span style={{ fontSize: 14 }}>{e.description}</span>{regulator && !e.visible_to_operator && <span className="ind-meta">Interne ARTEC</span>}</div>)}
        </Section>
      </div>

      <div className="grid-2">
        <Section title="Réponses de l'opérateur">
          {responses.data?.length === 0 && <Empty>Aucune réponse.</Empty>}
          {responses.data?.map((r) => <div key={r.id} className="stack-sm"><span style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{r.content}</span><span className="ind-meta">{r.responder} · {fmtDateTime(r.created_at)}</span></div>)}
          {!regulator && cs.status === "AWAITING_OPERATOR_RESPONSE" && (
            <div className="form-stack">
              <Notice>L'ARTEC attend votre réponse{cs.deadline ? ` avant le ${fmtDate(cs.deadline)}` : ""}.</Notice>
              <label className="field"><span className="field-label">Votre réponse</span><textarea className="input" rows={4} value={f.reply} onChange={(e) => set("reply", e.target.value)} /></label>
              <div><Button disabled={!f.reply.trim()} onClick={() => run(() => post(`cases/${id}/respond/`, { content: f.reply }), "Réponse transmise à l'ARTEC.")}>Transmettre ma réponse</Button></div>
            </div>
          )}
        </Section>
        <Section title="Actions correctives et contrôles de suivi">
          {actions.data?.length === 0 && <Empty>Aucune action corrective.</Empty>}
          {actions.data?.map((a) => (
            <div key={a.id} className="stack-sm">
              <div><strong>{a.description}</strong> <StatusPill status={a.status} /></div>
              <span className="ind-meta">Échéance {fmtDate(a.due_date)}{a.operator_report ? ` · rapport : ${a.operator_report}` : ""}{a.verification_comment ? ` · vérification : ${a.verification_comment}` : ""}</span>
              {!regulator && !closed && ["REQUESTED", "IN_PROGRESS"].includes(a.status) && (
                <div style={{ display: "flex", gap: 6 }}>
                  <Button size="sm" variant="secondary" onClick={() => run(() => post(`corrective-actions/${a.id}/update-progress/`, { status: "IN_PROGRESS" }), "Action marquée en cours.")}>En cours</Button>
                  <Button size="sm" onClick={() => { const r = window.prompt("Rapport de réalisation :"); if (r) run(() => post(`corrective-actions/${a.id}/update-progress/`, { status: "SUBMITTED", report: r }), "Transmis pour vérification.") }}>Transmettre pour vérification</Button>
                </div>
              )}
              {regulator && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                  <Button size="sm" variant="secondary" onClick={() => { const d = window.prompt("Date du contrôle de suivi (AAAA-MM-JJ) :"); if (d) run(() => post(`corrective-actions/${a.id}/schedule-check/`, { due_date: d }), "Contrôle de suivi planifié.") }}>Planifier un contrôle</Button>
                  {a.status === "SUBMITTED" && <>
                    <Button size="sm" onClick={() => { const m = window.prompt("Commentaire de vérification :") ?? ""; run(() => post(`corrective-actions/${a.id}/verify/`, { compliant: true, comment: m }), "Action vérifiée.") }}>Valider</Button>
                    <Button size="sm" variant="ghost" onClick={() => { const m = window.prompt("Motif de non-conformité :") ?? ""; run(() => post(`corrective-actions/${a.id}/verify/`, { compliant: false, comment: m }), "Action déclarée non réalisée.") }}>Non réalisée</Button>
                  </>}
                </div>
              )}
            </div>
          ))}
        </Section>
      </div>

      {regulator && !closed && (
        <Section title="Actions de l'ARTEC" subtitle="Réservé aux agents d'ARTEC Régulation et Prédiction. Aucune action n'est déclenchée automatiquement par un algorithme.">
          <div className="grid-2">
            <div className="form-stack">
              <strong>Demander une explication</strong>
              <label className="field"><span className="field-label">Objet de la demande</span><textarea className="input" rows={3} value={f.explanation} onChange={(e) => set("explanation", e.target.value)} /></label>
              <Input label="Délai de réponse" type="date" value={f.deadline} onChange={(e) => set("deadline", e.target.value)} />
              <div><Button disabled={!f.explanation.trim()} onClick={() => run(() => post(`cases/${id}/request-explanation/`, { message: f.explanation, deadline: f.deadline || undefined }), "Demande d'explication envoyée à l'opérateur.")}>Envoyer la demande</Button></div>
            </div>
            <div className="form-stack">
              <strong>Ajouter un élément de preuve</strong>
              <Select label="Nature" value={f.evKind} onChange={(e) => set("evKind", e.target.value)}>{["DOCUMENT", "MEASUREMENT", "DATASET", "PREDICTION", "OTHER"].map((k) => <option key={k}>{k}</option>)}</Select>
              <Input label="Description" value={f.evDesc} onChange={(e) => set("evDesc", e.target.value)} />
              <label style={{ display: "flex", gap: 6, fontSize: 13 }}><input type="checkbox" checked={f.evVisible} onChange={(e) => set("evVisible", e.target.checked)} /> Visible par l'opérateur</label>
              <div><Button variant="secondary" disabled={!f.evDesc.trim()} onClick={() => run(() => post(`cases/${id}/evidence/`, { kind: f.evKind, description: f.evDesc, visible_to_operator: f.evVisible }), "Preuve ajoutée.")}>Ajouter</Button></div>
            </div>
          </div>
          <div className="grid-2">
            <div className="form-stack">
              <strong>Rendre une décision</strong>
              <Select label="Nature de la décision" value={f.dCat} onChange={(e) => set("dCat", e.target.value)}>{Object.entries(DECISIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
              <label className="field"><span className="field-label">Motivation (20 caractères minimum)</span><textarea className="input" rows={4} value={f.dText} onChange={(e) => set("dText", e.target.value)} /></label>
              {evidence.data && evidence.data.length > 0 && (
                <div className="stack-sm"><span className="field-label">Preuves rattachées</span>
                  {evidence.data.map((e) => <label key={e.id} style={{ display: "flex", gap: 6, fontSize: 13 }}><input type="checkbox" checked={f.dEvidence.includes(e.id)} onChange={(x) => set("dEvidence", x.target.checked ? [...f.dEvidence, e.id] : f.dEvidence.filter((i) => i !== e.id))} /> #{e.id} {e.description.slice(0, 60)}</label>)}
                </div>
              )}
              <Notice tone="orange">Un avertissement exige une demande d'explication préalable et au moins une preuve.</Notice>
              <div><Button disabled={f.dText.trim().length < 20} onClick={() => run(() => post(`cases/${id}/decide/`, { category: f.dCat, justification: f.dText, evidence: f.dEvidence }), "Décision enregistrée et notifiée.")}>Enregistrer la décision</Button></div>
            </div>
            <div className="form-stack">
              <strong>Demander une action corrective</strong>
              <Input label="Description" value={f.aDesc} onChange={(e) => set("aDesc", e.target.value)} />
              <Input label="Échéance" type="date" value={f.aDue} onChange={(e) => set("aDue", e.target.value)} />
              <div><Button variant="secondary" disabled={!f.aDesc || !f.aDue} onClick={() => run(() => post(`cases/${id}/corrective-actions/`, { description: f.aDesc, due_date: f.aDue }), "Action corrective demandée.")}>Demander</Button></div>
              <strong style={{ marginTop: 8 }}>Note interne</strong>
              <Input label="Visible de l'ARTEC uniquement" value={f.note} onChange={(e) => set("note", e.target.value)} />
              <div><Button variant="ghost" disabled={!f.note.trim()} onClick={() => run(() => post(`cases/${id}/note/`, { message: f.note }), "Note ajoutée.")}>Ajouter la note</Button></div>
              <strong style={{ marginTop: 8 }}>Clôture</strong>
              <div><Button variant="secondary" onClick={() => { const m = window.prompt("Commentaire de clôture :") ?? ""; run(() => post(`cases/${id}/close/`, { comment: m }), "Dossier clôturé.") }}>Clôturer le dossier</Button></div>
            </div>
          </div>
        </Section>
      )}

      <Section title="Historique">
        <ul className="timeline">
          {timeline.data?.map((e) => <li key={e.id}><strong>{KIND[e.kind] ?? e.kind}</strong>{e.internal && " (interne)"} — {e.message}<small>{e.actor} · {fmtDateTime(e.created_at)}</small></li>)}
        </ul>
      </Section>
    </div>
  )
}
