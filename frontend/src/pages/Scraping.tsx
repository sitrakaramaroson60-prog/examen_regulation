import { useState } from "react"
import { Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, StatusPill, Table } from "../components/kit"
import { fmtDateTime } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useFetch } from "../lib/useFetch"

type Status = { configured: boolean; allowed_domains: string[]; message: string }
type Source = { id: number; name: string; base_url: string }
type Job = { id: number; name: string; url: string; frequency: string; status: string; last_run_at: string | null; last_result: string; items_collected: number; error_count: number }
type Rec = { id: number; job: number; source_url: string; http_status: number | null; content_type: string; data: { title?: string; text_excerpt?: string; description?: string }; fetched_at: string; validation_status: string }
const FREQ: Record<string, string> = { MANUAL: "Manuelle", HOURLY: "Toutes les heures", DAILY: "Chaque jour", WEEKLY: "Chaque semaine" }

/** Collectes web de l'organisme : sources, tâches, exécutions et validation des données collectées. */
export default function Scraping() {
  const status = useFetch<Status>("/scraping/status/")
  const sources = useFetch<Page<Source>>("/scraping/sources/", { page_size: 100 })
  const jobs = useFetch<Page<Job>>("/scraping/jobs/", { page_size: 100 })
  const [recStatus, setRecStatus] = useState("PENDING")
  const records = useFetch<Page<Rec>>("/scraping/records/", { validation_status: recStatus, page_size: 50 })
  const [src, setSrc] = useState({ name: "", base_url: "" })
  const [job, setJob] = useState({ name: "", source: "", url: "", frequency: "MANUAL" })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const run = async (fn: () => Promise<unknown>, ok: string) => { try { await fn(); setMsg({ t: "green", m: ok }) } catch (e) { setMsg({ t: "red", m: describeError(e) }) } }

  return (
    <div className="page-stack">
      <PageHeader title="Collectes web" subtitle="Chaque organisme collecte les données dont il a besoin. Les collectes respectent les conditions des sites (robots.txt) et restent limitées aux domaines autorisés ; rien n'est utilisé avant votre validation." />
      {status.data && !status.data.configured && <Notice>{status.data.message} Demandez à l'administrateur d'autoriser les domaines nécessaires (variable <code>SCRAPING_ALLOWED_DOMAINS</code>).</Notice>}
      {status.data?.configured && <Notice tone="blue">Domaines autorisés : {status.data.allowed_domains.join(", ")}</Notice>}
      {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}

      <div className="grid-2">
        <Section title="Sources">
          {sources.data?.results.length === 0 && <Empty>Aucune source.</Empty>}
          {sources.data && sources.data.results.length > 0 && <Table head={["Source", "Adresse"]}>{sources.data.results.map((s) => <tr key={s.id}><td><strong>{s.name}</strong></td><td>{s.base_url}</td></tr>)}</Table>}
          <div className="form-stack">
            <Input label="Nom" value={src.name} onChange={(e) => setSrc({ ...src, name: e.target.value })} />
            <Input label="Adresse du site" placeholder="https://…" value={src.base_url} onChange={(e) => setSrc({ ...src, base_url: e.target.value })} />
            <div><Button variant="secondary" disabled={!src.name || !src.base_url} onClick={() => run(async () => { await api("/scraping/sources/", { method: "POST", body: src }); setSrc({ name: "", base_url: "" }); sources.reload() }, "Source ajoutée.")}>Ajouter la source</Button></div>
          </div>
        </Section>
        <Section title="Nouvelle tâche de collecte">
          <div className="form-stack">
            <Input label="Nom de la tâche" value={job.name} onChange={(e) => setJob({ ...job, name: e.target.value })} />
            <Select label="Source" value={job.source} onChange={(e) => setJob({ ...job, source: e.target.value })}><option value="">Sélectionner…</option>{sources.data?.results.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</Select>
            <Input label="Page à collecter (domaine autorisé)" placeholder="https://…" value={job.url} onChange={(e) => setJob({ ...job, url: e.target.value })} />
            <Select label="Fréquence" value={job.frequency} onChange={(e) => setJob({ ...job, frequency: e.target.value })}>{Object.entries(FREQ).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</Select>
            <div><Button disabled={!job.name || !job.source || !job.url} onClick={() => run(async () => { await api("/scraping/jobs/", { method: "POST", body: { ...job, source: Number(job.source) } }); setJob({ ...job, name: "", url: "" }); jobs.reload() }, "Tâche créée.")}>Créer la tâche</Button></div>
          </div>
        </Section>
      </div>

      <Section title="Tâches">
        {jobs.loading && <Loading />}
        {jobs.error && <ErrorMsg>{jobs.error}</ErrorMsg>}
        {jobs.data?.results.length === 0 && <Empty>Aucune tâche de collecte.</Empty>}
        {jobs.data && jobs.data.results.length > 0 && (
          <Table head={["Tâche", "Page", "Fréquence", "Dernier résultat", "Collectés / erreurs", ""]}>
            {jobs.data.results.map((j) => (
              <tr key={j.id}><td><strong>{j.name}</strong></td><td>{j.url}</td><td>{FREQ[j.frequency]}</td><td>{j.last_result || "—"}<div className="ind-meta">{fmtDateTime(j.last_run_at)}</div></td><td>{j.items_collected} / {j.error_count}</td>
                <td><Button size="sm" variant="secondary" onClick={() => run(() => api(`/scraping/jobs/${j.id}/run/`, { method: "POST" }), "Collecte lancée : le résultat apparaît dès qu'elle est terminée.")}>Lancer</Button></td></tr>
            ))}
          </Table>
        )}
      </Section>

      <Section title="Données collectées" subtitle="Rien n'est utilisé dans les analyses avant votre validation."
        actions={<Select label="" aria-label="Validation" value={recStatus} onChange={(e) => setRecStatus(e.target.value)}><option value="PENDING">À valider</option><option value="VALIDATED">Validées</option><option value="REJECTED">Rejetées</option></Select>}>
        {records.data?.results.length === 0 && <Empty>Aucune donnée dans cet état.</Empty>}
        {records.data && records.data.results.length > 0 && (
          <Table head={["Collectée le", "Provenance", "Contenu", "Statut", ""]}>
            {records.data.results.map((r) => (
              <tr key={r.id}><td>{fmtDateTime(r.fetched_at)}</td><td>{r.source_url}<div className="ind-meta">HTTP {r.http_status} · {r.content_type}</div></td>
                <td><strong>{r.data.title}</strong><div className="ind-meta">{(r.data.description || r.data.text_excerpt || "").slice(0, 160)}</div></td><td><StatusPill status={r.validation_status} /></td>
                <td style={{ whiteSpace: "nowrap" }}>{r.validation_status === "PENDING" && <>
                  <Button size="sm" onClick={() => run(async () => { await api(`/scraping/records/${r.id}/validate/`, { method: "POST" }); records.reload() }, "Donnée validée.")}>Valider</Button>{" "}
                  <Button size="sm" variant="ghost" onClick={() => run(async () => { await api(`/scraping/records/${r.id}/reject/`, { method: "POST" }); records.reload() }, "Donnée rejetée.")}>Rejeter</Button></>}</td></tr>
            ))}
          </Table>
        )}
      </Section>
    </div>
  )
}
