import { useMemo, useState } from "react"
import { Link, useParams } from "react-router"
import { CheckCircle2, Copy } from "lucide-react"
import { Badge, Button, Card, Heading, Input, Select, Text } from "../components/ui"
import { Loading, Notice } from "../components/kit"
import { fmtDateTime } from "../lib/format"
import { api, describeError } from "../lib/api"
import { useFetch } from "../lib/useFetch"

type Region = { id: number; name: string; cities: { id: number; name: string }[] }
const CATEGORIES = ["Qualité des appels", "Coupures fréquentes", "Débit internet insuffisant", "Absence de couverture", "Facturation ou offre", "Service client", "Autre"]
const STATUS_LABEL: Record<string, string> = { NEW: "Reçue", IN_REVIEW: "En cours de traitement", AWAITING_INFO: "Informations demandées", RESOLVED: "Traitée", REJECTED: "Non retenue", CLOSED: "Clôturée" }

/** Signalement d'un problème de service par le public (sans compte). */
export function ReportProblemPage() {
  const regions = useFetch<Region[]>("/organizations/regions/", undefined, false)
  const [f, setF] = useState({ complaint_type: "PUBLIC_COMPLAINT", category: CATEGORIES[0], description: "", target_operator: "", region: "", city: "", contact_email: "" })
  const [website, setWebsite] = useState("") // champ piège anti-robot
  const [done, setDone] = useState<{ reference: string; tracking_token: string } | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const cities = useMemo(() => regions.data?.find((r) => String(r.id) === f.region)?.cities ?? [], [regions.data, f.region])

  const submit = async () => {
    setBusy(true); setError("")
    try {
      const r = await api<{ reference: string; tracking_token: string }>("/complaints/public/", {
        method: "POST", auth: false,
        body: { ...f, target_operator: f.target_operator || null, region: f.region ? Number(f.region) : null, city: f.city ? Number(f.city) : null, website },
      })
      setDone(r)
    } catch (e) { setError(describeError(e)) } finally { setBusy(false) }
  }

  if (done)
    return (
      <section className="page-section"><div className="container narrow">
        <Card className="placeholder-card">
          <CheckCircle2 size={36} />
          <Heading>Votre signalement a été transmis</Heading>
          <Text>Référence : <strong>{done.reference}</strong></Text>
          <Text>Code de suivi (affiché une seule fois, conservez-le) :</Text>
          <code style={{ padding: "8px 12px", background: "#eef2f7", borderRadius: 8, wordBreak: "break-all" }}>{done.tracking_token}</code>
          <Button variant="secondary" onClick={() => void navigator.clipboard.writeText(`${done.reference} ${done.tracking_token}`)}><Copy size={15} /> Copier la référence et le code</Button>
          <Link className="link-btn" to="/signalement/suivi">Suivre mon signalement</Link>
        </Card>
      </div></section>
    )

  return (
    <section className="page-section"><div className="container narrow">
      <div className="page-heading"><div>
        <Text as="small" className="eyebrow">PARTICIPATION PUBLIQUE</Text>
        <Heading as="h1">Signaler un problème de service</Heading>
        <Text>Aucun compte n’est nécessaire. Votre signalement est examiné par l’ARTEC ; il ne vaut pas, à lui seul, constat de manquement d’un opérateur.</Text>
      </div></div>
      {error && <Notice tone="red">{error}</Notice>}
      <Card className="kit-section">
        <div className="form-stack">
          <div className="form-row">
            <Select label="Nature" value={f.complaint_type} onChange={(e) => setF({ ...f, complaint_type: e.target.value })}><option value="PUBLIC_COMPLAINT">Réclamation</option><option value="REPORT">Signalement d'un problème</option></Select>
            <Select label="Type de problème" value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })}>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</Select>
            <Select label="Opérateur concerné" value={f.target_operator} onChange={(e) => setF({ ...f, target_operator: e.target.value })}><option value="">Je ne sais pas / plusieurs</option><option>YAS</option><option>AIRTEL</option><option>ORANGE</option></Select>
          </div>
          <div className="form-row">
            <Select label="Région" value={f.region} onChange={(e) => setF({ ...f, region: e.target.value, city: "" })}><option value="">Non précisée</option>{regions.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}</Select>
            <Select label="Ville" disabled={!f.region} value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })}><option value="">Non précisée</option>{cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>
          </div>
          <label className="field"><span className="field-label">Décrivez le problème (10 caractères minimum)</span><textarea className="input" rows={5} maxLength={4000} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} /></label>
          <Input label="Email de contact (facultatif)" type="email" value={f.contact_email} onChange={(e) => setF({ ...f, contact_email: e.target.value })} />
          <input type="text" tabIndex={-1} autoComplete="off" aria-hidden="true" value={website} onChange={(e) => setWebsite(e.target.value)} style={{ position: "absolute", left: "-9999px" }} />
          <Text as="small">N’indiquez ni numéro de carte, ni mot de passe. Les dépôts sont limités en nombre pour éviter les abus.</Text>
          <div><Button loading={busy} disabled={f.description.trim().length < 10} onClick={submit}>Envoyer mon signalement</Button></div>
        </div>
      </Card>
    </div></section>
  )
}

type Tracking = { reference: string; status: string; category: string; conclusion: string; messages: { author_kind: string; content: string; created_at: string }[] }

export function TrackComplaintPage() {
  const [ref, setRef] = useState("")
  const [token, setToken] = useState("")
  const [data, setData] = useState<Tracking | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState(false)
  const check = async () => {
    setBusy(true); setError("")
    try { setData(await api<Tracking>("/complaints/public/track/", { method: "POST", auth: false, body: { reference: ref.trim(), token: token.trim() } })) }
    catch (e) { setData(null); setError(describeError(e)) } finally { setBusy(false) }
  }
  return (
    <section className="page-section"><div className="container narrow">
      <div className="page-heading"><div><Text as="small" className="eyebrow">PARTICIPATION PUBLIQUE</Text><Heading as="h1">Suivre mon signalement</Heading><Text>Saisissez la référence et le code de suivi remis lors du dépôt.</Text></div></div>
      <Card className="kit-section">
        <div className="form-row"><Input label="Référence" placeholder="CMP-2026-00001" value={ref} onChange={(e) => setRef(e.target.value)} /><Input label="Code de suivi" value={token} onChange={(e) => setToken(e.target.value)} /></div>
        {error && <Notice tone="red">{error}</Notice>}
        <div><Button loading={busy} disabled={!ref || !token} onClick={check}>Consulter</Button></div>
      </Card>
      {busy && <Loading />}
      {data && (
        <Card className="kit-section">
          <Heading as="h3">{data.reference} — {data.category}</Heading>
          <Badge tone={data.status === "RESOLVED" ? "green" : data.status === "REJECTED" ? "red" : "blue"}>{STATUS_LABEL[data.status] ?? data.status}</Badge>
          {data.conclusion && <Notice tone="blue">{data.conclusion}</Notice>}
          {data.messages.map((m, i) => <div key={i} className="stack-sm"><strong>{m.author_kind === "ARTEC" ? "ARTEC" : "Vous"}</strong><span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span><span className="ind-meta">{fmtDateTime(m.created_at)}</span></div>)}
        </Card>
      )}
    </div></section>
  )
}

type Results = { title: string; total_responses: number; suppressed?: boolean; message?: string; by_region: { region: string; count: number }[]; questions: { id: number; text: string; type: string; answered: number; average?: number | null; yes?: number; no?: number; choices?: { id: number; label: string; count: number }[] }[] }

/** Résultats publics d'un sondage : agrégés, sans texte libre, au-delà d'un nombre minimal de réponses. */
export function PublicSurveyResults() {
  const { id } = useParams()
  const r = useFetch<Results>(`/surveys/${id}/results/`, undefined, false)
  if (r.loading) return <section className="page-section"><div className="container narrow"><Loading /></div></section>
  if (r.error || !r.data) return <section className="page-section"><div className="container narrow"><Card className="placeholder-card"><Heading>Résultats non publics</Heading><Text>Les résultats de ce sondage n’ont pas été rendus publics.</Text><Link className="link-btn" to="/sondages">Retour aux sondages</Link></Card></div></section>
  const d = r.data
  return (
    <section className="page-section"><div className="container narrow">
      <Link className="link-btn" to="/sondages">← Retour aux sondages</Link>
      <div className="page-heading"><div><Text as="small" className="eyebrow">RÉSULTATS PUBLICS</Text><Heading as="h1">{d.title}</Heading><Text>{d.total_responses} réponse(s) · résultats agrégés et anonymes, mis à jour en direct.</Text></div></div>
      {d.suppressed && <Notice>{d.message}</Notice>}
      {d.questions.map((q) => (
        <Card className="kit-section" key={q.id}>
          <Heading as="h3">{q.text}</Heading>
          {q.choices?.map((c) => { const max = Math.max(...q.choices!.map((x) => x.count), 1); return <div className="op-row" key={c.id} style={{ gridTemplateColumns: "minmax(120px,1fr) 2fr auto" }}><span>{c.label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${(c.count / max) * 100}%` }} /></div><span className="val">{c.count}</span></div> })}
          {q.average != null && <Text>Moyenne : <strong>{q.average.toLocaleString("fr-FR", { maximumFractionDigits: 2 })}</strong></Text>}
          {q.yes !== undefined && <Text>Oui : {q.yes} · Non : {q.no}</Text>}
        </Card>
      ))}
      {d.by_region.length > 0 && <Card className="kit-section"><Heading as="h3">Participation par région</Heading>{d.by_region.map((x) => <Text key={x.region}>{x.region} : {x.count}</Text>)}</Card>}
    </div></section>
  )
}
