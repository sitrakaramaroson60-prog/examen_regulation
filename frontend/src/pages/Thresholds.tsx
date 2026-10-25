import { useState } from "react"
import { Button, Input, Select } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, Table } from "../components/kit"
import { fmtDate } from "../lib/format"
import { api, describeError, type Page } from "../lib/api"
import { useFetch } from "../lib/useFetch"

type Th = { id: number; metric_name: string; technology: string; service_type: string; unit: string; good_threshold: number; poor_threshold: number; higher_is_better: boolean; valid_from: string; valid_until: string | null; origin: string }
type Metric = { metric: string; label: string; unit: string; units: string[]; higher_is_better: boolean }

export default function Thresholds({ readOnly = false }: { readOnly?: boolean }) {
  const list = useFetch<Page<Th>>("/qos/thresholds/", { page_size: 200 })
  const metrics = useFetch<Metric[]>("/qos/measurements/metrics/")
  const [f, setF] = useState({ metric_name: "download_speed", technology: "", service_type: "", good_threshold: "", poor_threshold: "", valid_from: new Date().toISOString().slice(0, 10), origin: "" })
  const [msg, setMsg] = useState<{ t: "red" | "green"; m: string } | null>(null)
  const m = metrics.data?.find((x) => x.metric === f.metric_name)
  const label = (k: string) => metrics.data?.find((x) => x.metric === k)?.label ?? k
  const save = async () => {
    try {
      await api("/qos/thresholds/", { method: "POST", body: { ...f, unit: m?.unit, higher_is_better: m?.higher_is_better, good_threshold: Number(f.good_threshold), poor_threshold: Number(f.poor_threshold) } })
      setMsg({ t: "green", m: "Seuil enregistré." }); setF({ ...f, good_threshold: "", poor_threshold: "", origin: "" }); list.reload()
    } catch (e) { setMsg({ t: "red", m: describeError(e) }) }
  }
  return (
    <div className="page-stack">
      <PageHeader title="Seuils de qualité de service" subtitle="Valeurs de référence qui déterminent les niveaux bon / moyen / mauvais. Chaque seuil documente son origine ; aucune valeur officielle n'est préremplie." />
      {list.loading && <Loading />}
      {list.error && <ErrorMsg>{list.error}</ErrorMsg>}
      <Section title="Seuils en vigueur">
        {list.data && list.data.results.length === 0 && <Empty>Aucun seuil configuré : les statuts de qualité ne peuvent pas être calculés et les prévisions ne peuvent pas être étiquetées.</Empty>}
        {list.data && list.data.results.length > 0 && (
          <Table head={["Indicateur", "Périmètre", "Bon si", "Mauvais si", "Validité", "Origine"]}>
            {list.data.results.map((t) => (
              <tr key={t.id}><td><strong>{label(t.metric_name)}</strong></td><td>{t.technology || "Toutes technologies"}{t.service_type ? ` · ${t.service_type}` : ""}</td>
                <td>{t.higher_is_better ? "≥" : "≤"} {t.good_threshold} {t.unit}</td><td>{t.higher_is_better ? "<" : ">"} {t.poor_threshold} {t.unit}</td>
                <td>{fmtDate(t.valid_from)} → {t.valid_until ? fmtDate(t.valid_until) : "sans limite"}</td><td>{t.origin}</td></tr>
            ))}
          </Table>
        )}
      </Section>
      {!readOnly && (
        <Section title="Ajouter un seuil">
          {msg && <Notice tone={msg.t === "red" ? "red" : "green"}>{msg.m}</Notice>}
          <div className="form-stack">
            <div className="form-row">
              <Select label="Indicateur" value={f.metric_name} onChange={(e) => setF({ ...f, metric_name: e.target.value })}>{metrics.data?.map((x) => <option key={x.metric} value={x.metric}>{x.label}</option>)}</Select>
              <Input label="Technologie (facultatif)" value={f.technology} onChange={(e) => setF({ ...f, technology: e.target.value })} />
              <Input label={`Seuil « bon » (${m?.unit ?? ""})`} type="number" step="any" value={f.good_threshold} onChange={(e) => setF({ ...f, good_threshold: e.target.value })} />
              <Input label={`Seuil « mauvais » (${m?.unit ?? ""})`} type="number" step="any" value={f.poor_threshold} onChange={(e) => setF({ ...f, poor_threshold: e.target.value })} />
              <Input label="En vigueur depuis" type="date" value={f.valid_from} onChange={(e) => setF({ ...f, valid_from: e.target.value })} />
            </div>
            <Notice tone="blue">{m?.higher_is_better ? "Pour cet indicateur, plus la valeur est élevée, meilleure est la qualité : le seuil « bon » doit être supérieur ou égal au seuil « mauvais »." : "Pour cet indicateur, plus la valeur est basse, meilleure est la qualité : le seuil « bon » doit être inférieur ou égal au seuil « mauvais »."}</Notice>
            <Input label="Origine du seuil (texte, décision, norme)" value={f.origin} onChange={(e) => setF({ ...f, origin: e.target.value })} />
            <div><Button disabled={!f.good_threshold || !f.poor_threshold || f.origin.trim().length < 5} onClick={save}>Enregistrer le seuil</Button></div>
          </div>
        </Section>
      )}
    </div>
  )
}
