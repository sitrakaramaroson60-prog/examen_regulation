import { useCallback, useEffect, useState, type ReactNode } from "react"
import { Badge, Button, Card, Heading, Input, Select, Text } from "../components/ui"
import { StatusPill } from "../components/kit"
import { useAuth } from "../lib/auth-context"
import { api, describeError, type Page } from "../lib/api"
import { useLivePath } from "../lib/useLive"

/** Tableau paginé alimenté par l'API. Toutes les permissions sont appliquées côté serveur. */
type Column<T> = { header: string; render: (row: T) => ReactNode }
type RowAction<T> = {
  label: string
  show?: (row: T) => boolean
  /** Si défini, un motif est demandé et envoyé dans { comment } */
  askComment?: boolean
  run: (row: T, comment?: string) => Promise<unknown>
}

function DataPage<T extends { id: number }>({
  title, subtitle, endpoint, query, columns, actions = [], toolbar, refreshKey = 0,
}: {
  title: string
  subtitle: string
  endpoint: string
  query?: Record<string, string>
  columns: Column<T>[]
  actions?: RowAction<T>[]
  toolbar?: ReactNode
  refreshKey?: number
}) {
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState("")
  const [data, setData] = useState<Page<T> | null>(null)
  const [error, setError] = useState("")
  const [busy, setBusy] = useState<number | null>(null)
  const [reload, setReload] = useState(0)
  const live = useLivePath(endpoint)

  const load = useCallback(() => {
    api<Page<T>>(endpoint, { query: { ...query, page, search } })
      .then((d) => { setData(d); setError("") })
      .catch((e) => setError(describeError(e)))
  }, [endpoint, query, page, search])

  useEffect(() => {
    const t = window.setTimeout(load, 200)
    return () => window.clearTimeout(t)
  }, [load, reload, refreshKey, live])

  const exec = async (a: RowAction<T>, row: T) => {
    let comment: string | undefined
    if (a.askComment) {
      const c = window.prompt(`${a.label} — motif :`)
      if (c === null) return
      comment = c
    }
    setBusy(row.id)
    try {
      await a.run(row, comment)
      setReload((n) => n + 1)
    } catch (e) {
      window.alert(describeError(e))
    } finally {
      setBusy(null)
    }
  }

  return (
    <>
      <div className="dashboard-heading">
        <div>
          <Text as="small" className="eyebrow">ESPACE PROFESSIONNEL</Text>
          <Heading as="h1">{title}</Heading>
          <Text>{subtitle}</Text>
        </div>
      </div>
      {toolbar}
      <Card>
        <div className="search-box" style={{ marginBottom: 12 }}>
          <Input placeholder="Rechercher…" value={search} onChange={(e) => { setPage(1); setSearch(e.target.value) }} />
        </div>
        {error && <p className="field-error" role="alert">{error}</p>}
        {!data && !error && <Text>Chargement…</Text>}
        {data && data.results.length === 0 && <Text>Aucun élément à afficher.</Text>}
        {data && data.results.length > 0 && (
          <div style={{ overflowX: "auto" }}>
            <table className="data-table" style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  {columns.map((c) => <th key={c.header} style={{ textAlign: "left", padding: "8px 10px" }}>{c.header}</th>)}
                  {actions.length > 0 && <th />}
                </tr>
              </thead>
              <tbody>
                {data.results.map((row) => (
                  <tr key={row.id} style={{ borderTop: "1px solid var(--line, #e5e7eb)" }}>
                    {columns.map((c) => <td key={c.header} style={{ padding: "8px 10px" }}>{c.render(row)}</td>)}
                    {actions.length > 0 && (
                      <td style={{ padding: "8px 10px", whiteSpace: "nowrap" }}>
                        {actions.filter((a) => !a.show || a.show(row)).map((a) => (
                          <Button key={a.label} size="sm" variant="secondary" disabled={busy === row.id} onClick={() => exec(a, row)} style={{ marginRight: 6 }}>{a.label}</Button>
                        ))}
                      </td>
                    )}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && (data.next || data.previous) && (
          <div style={{ display: "flex", gap: 8, marginTop: 12, alignItems: "center" }}>
            <Button size="sm" variant="secondary" disabled={!data.previous} onClick={() => setPage(page - 1)}>Précédent</Button>
            <Text as="small">Page {page} · {data.count} résultat(s)</Text>
            <Button size="sm" variant="secondary" disabled={!data.next} onClick={() => setPage(page + 1)}>Suivant</Button>
          </div>
        )}
      </Card>
    </>
  )
}

const fmt = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("fr-FR") : "—")
const St = ({ s }: { s: string }) => <StatusPill status={s} />
const post = (url: string, body?: unknown) => api(url, { method: "POST", body: body ?? {} })

/* ===================== ARTEC Régulation ===================== */
type Submission = { id: number; reference: string; organization: string; dataset_name: string; data_type: string; version_number: number; status: string; report_status: string; quality_score: number; review_comment: string; submitted_at: string }

export function RegulationSubmissions() {
  const cols: Column<Submission>[] = [
    { header: "Référence", render: (r) => r.reference },
    { header: "Organisme", render: (r) => r.organization },
    { header: "Dataset", render: (r) => `${r.dataset_name} (v${r.version_number})` },
    { header: "Qualité", render: (r) => <><St s={r.report_status} /> {r.quality_score} %</> },
    { header: "Statut", render: (r) => <St s={r.status} /> },
    { header: "Soumis le", render: (r) => fmt(r.submitted_at) },
  ]
  const base = (r: Submission) => `/submissions/${r.id}`
  const actions: RowAction<Submission>[] = [
    { label: "Examiner", show: (r) => r.status === "SUBMITTED", run: (r) => post(`${base(r)}/start-review/`) },
    { label: "Accepter", show: (r) => r.status === "UNDER_REVIEW", askComment: true, run: (r, c) => post(`${base(r)}/accept/`, { comment: c }) },
    { label: "Demander correction", show: (r) => ["SUBMITTED", "UNDER_REVIEW"].includes(r.status), askComment: true, run: (r, c) => post(`${base(r)}/request-correction/`, { comment: c }) },
    { label: "Rejeter", show: (r) => ["SUBMITTED", "UNDER_REVIEW"].includes(r.status), askComment: true, run: (r, c) => post(`${base(r)}/reject/`, { comment: c }) },
  ]
  return <DataPage<Submission> title="Soumissions des opérateurs" subtitle="Examinez, acceptez ou renvoyez les datasets soumis. Tout rejet ou demande de correction doit être motivé." endpoint="/submissions/" columns={cols} actions={actions} />
}

type Audit = { id: number; actor_email: string; action: string; resource_type: string; resource_id: string; timestamp: string }
export function AuditPage() {
  return <DataPage<Audit> title="Historique des actions" subtitle="Journal d’audit en lecture seule." endpoint="/audit/" columns={[
    { header: "Date", render: (r) => fmt(r.timestamp) }, { header: "Utilisateur", render: (r) => r.actor_email || "—" },
    { header: "Action", render: (r) => r.action }, { header: "Ressource", render: (r) => `${r.resource_type} ${r.resource_id}` },
  ]} />
}

type Measurement = { id: number; operator: string; region: string; city: string | null; metric_name: string; metric_value: number; unit: string; measurement_method: string; source_type: string; measured_at: string }
export function QosPage() {
  return <DataPage<Measurement> title="Indicateurs QoS" subtitle="Mesures issues de datasets acceptés. Les méthodes de mesure différentes ne sont jamais fusionnées." endpoint="/qos/measurements/" columns={[
    { header: "Opérateur", render: (r) => r.operator }, { header: "Région", render: (r) => r.region }, { header: "Indicateur", render: (r) => r.metric_name },
    { header: "Valeur", render: (r) => `${r.metric_value} ${r.unit}` }, { header: "Méthode", render: (r) => r.measurement_method },
    { header: "Source", render: (r) => r.source_type }, { header: "Date", render: (r) => fmt(r.measured_at) },
  ]} />
}

/* ===================== Opérateur ===================== */
type Dataset = { id: number; name: string; data_type: string; source_type: string; created_at: string; latest_version: { id: number; version_number: number; report_status: string } | null }

export function OperatorDatasets() {
  const [name, setName] = useState("")
  const [dataType, setDataType] = useState("QOS_MEASUREMENT")
  const [sourceType, setSourceType] = useState("TECHNICAL")
  const [file, setFile] = useState<File | null>(null)
  const [msg, setMsg] = useState("")
  const [refresh, setRefresh] = useState(0)
  const importFile = async () => {
    if (!file || !name) return
    try {
      const existing = await api<Page<Dataset>>("/datasets/", { query: { search: name } })
      const found = existing.results.find((d) => d.name === name)
      const dsId = found ? found.id : (await api<Dataset>("/datasets/", { method: "POST", body: { name, data_type: dataType, source_type: sourceType } })).id
      const form = new FormData()
      form.append("file", file)
      const v = await api<{ version_number: number; report: { status: string; messages: string[] } }>(`/datasets/${dsId}/versions/`, { method: "POST", body: form })
      setMsg(`Version ${v.version_number} importée — rapport : ${v.report.status}. ${v.report.messages.join(" ")}`)
      setRefresh((n) => n + 1)
    } catch (e) { setMsg(describeError(e)) }
  }
  const submit = async (d: Dataset) => {
    if (!d.latest_version) return
    return post(`/datasets/versions/${d.latest_version.id}/submit/`)
  }
  return (
    <DataPage<Dataset>
      title="Datasets et importation" subtitle="Importez un fichier CSV, XLSX ou JSON : il est validé automatiquement avant toute soumission à l’ARTEC."
      endpoint="/datasets/" refreshKey={refresh}
      columns={[
        { header: "Nom", render: (r) => r.name }, { header: "Type", render: (r) => r.data_type }, { header: "Nature", render: (r) => (r.source_type === "TECHNICAL" ? "Mesures techniques" : r.source_type === "DECLARED" ? "Déclaré" : r.source_type) },
        { header: "Dernière version", render: (r) => (r.latest_version ? <>v{r.latest_version.version_number} <St s={r.latest_version.report_status} /></> : "—") },
        { header: "Créé le", render: (r) => fmt(r.created_at) },
      ]}
      actions={[{ label: "Soumettre à l’ARTEC", show: (r) => !!r.latest_version && r.latest_version.report_status !== "INVALID", run: submit }]}
      toolbar={
        <Card>
          <Heading as="h3">Importer une version</Heading>
          <div className="form-grid">
            <Input label="Nom du dataset" value={name} onChange={(e) => setName(e.target.value)} />
            <Select label="Type de données" value={dataType} onChange={(e) => setDataType(e.target.value)}>
              <option value="QOS_MEASUREMENT">Mesures QoS</option><option value="OTHER">Autre</option>
            </Select>
            <Select label="Nature des données" value={sourceType} onChange={(e) => setSourceType(e.target.value)}>
              <option value="TECHNICAL">Mesures techniques (sondes, drive tests, speed tests)</option>
              <option value="DECLARED">Indicateurs déclarés par l’opérateur</option>
            </Select>
          </div>
          <input type="file" accept=".csv,.xlsx,.json" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
          {msg && <Text as="small">{msg}</Text>}
          <Button disabled={!file || !name} onClick={importFile}>Importer et valider</Button>
        </Card>
      }
    />
  )
}

export function OperatorSubmissions() {
  return <DataPage<Submission> title="Soumissions à l’ARTEC" subtitle="Suivi de vos soumissions et des demandes de correction." endpoint="/submissions/" columns={[
    { header: "Référence", render: (r) => r.reference }, { header: "Dataset", render: (r) => `${r.dataset_name} (v${r.version_number})` },
    { header: "Statut", render: (r) => <St s={r.status} /> }, { header: "Commentaire ARTEC", render: (r) => r.review_comment || "—" }, { header: "Soumis le", render: (r) => fmt(r.submitted_at) },
  ]} />
}

/* ===================== Publications ===================== */
type Pub = { id: number; title: string; category: string; status: string; audience: string; published_at: string | null }
const PUB_CATEGORIES: Record<string, string> = { INFORMATION: "Information", PRESS_RELEASE: "Communiqué", REPORT: "Rapport", CONSULTATION: "Consultation", OTHER: "Autre" }

export function PublicationsAdmin() {
  const { user } = useAuth()
  const regulator = user?.role === "ARTEC_REGULATOR"
  const categories = regulator ? ["REPORT", "CONSULTATION"] : Object.keys(PUB_CATEGORIES)
  const [category, setCategory] = useState(regulator ? "REPORT" : "INFORMATION")
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [refresh, setRefresh] = useState(0)
  const [msg, setMsg] = useState("")
  const create = async () => {
    try { await api("/publications/", { method: "POST", body: { title, content, category } }); setTitle(""); setContent(""); setRefresh((n) => n + 1); setMsg("Brouillon créé.") }
    catch (e) { setMsg(describeError(e)) }
  }
  return (
    <DataPage<Pub>
      title={regulator ? "Rapports et consultations publics" : "Publications"}
      subtitle={regulator ? "Rapports, indicateurs agrégés et consultations publiés par l’ARTEC Régulation." : "Rédigez, publiez ou archivez vos contenus."}
      endpoint="/publications/" refreshKey={refresh}
      columns={[{ header: "Titre", render: (r) => r.title }, { header: "Catégorie", render: (r) => PUB_CATEGORIES[r.category] ?? r.category }, { header: "Statut", render: (r) => <St s={r.status} /> }, { header: "Publiée le", render: (r) => fmt(r.published_at) }]}
      actions={[
        { label: "Publier", show: (r) => r.status === "DRAFT" || r.status === "SCHEDULED", run: (r) => post(`/publications/${r.id}/publish/`) },
        { label: "Archiver", show: (r) => r.status === "PUBLISHED", run: (r) => post(`/publications/${r.id}/archive/`) },
      ]}
      toolbar={<Card><Heading as="h3">Nouvelle publication</Heading><Input label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Select label="Catégorie" value={category} onChange={(e) => setCategory(e.target.value)}>{categories.map((c) => <option key={c} value={c}>{PUB_CATEGORIES[c]}</option>)}</Select>
        <label className="field"><span className="field-label">Contenu</span><textarea className="input" rows={4} value={content} onChange={(e) => setContent(e.target.value)} /></label>
        {msg && <Text as="small">{msg}</Text>}<Button disabled={!title || !content} onClick={create}>Enregistrer le brouillon</Button></Card>}
    />
  )
}

type Cm = { id: number; publication_title: string; content: string; author_name: string; status: string; report_count: number; created_at: string }
export function CommentsAdmin() {
  return <DataPage<Cm> title="Modération des commentaires" subtitle="Seuls les commentaires approuvés sont visibles du public." endpoint="/comments/" query={{ status: "PENDING" }} columns={[
    { header: "Publication", render: (r) => r.publication_title }, { header: "Commentaire", render: (r) => r.content }, { header: "Auteur", render: (r) => r.author_name || "Anonyme" },
    { header: "Signalements", render: (r) => r.report_count }, { header: "Statut", render: (r) => <St s={r.status} /> },
  ]} actions={[
    { label: "Approuver", run: (r) => post(`/comments/${r.id}/approve/`) }, { label: "Rejeter", run: (r) => post(`/comments/${r.id}/reject/`) }, { label: "Masquer", run: (r) => post(`/comments/${r.id}/hide/`) },
  ]} />
}

/* ===================== Commun ===================== */
type Notif = { id: number; title: string; message: string; is_read: boolean; created_at: string }
export function NotificationsPage() {
  return <DataPage<Notif> title="Notifications" subtitle="Vos notifications personnelles." endpoint="/notifications/" columns={[
    { header: "", render: (r) => (r.is_read ? "" : <Badge>Nouveau</Badge>) }, { header: "Titre", render: (r) => r.title }, { header: "Message", render: (r) => r.message }, { header: "Date", render: (r) => fmt(r.created_at) },
  ]} actions={[{ label: "Marquer lue", show: (r) => !r.is_read, run: (r) => post(`/notifications/${r.id}/read/`) }]} />
}
