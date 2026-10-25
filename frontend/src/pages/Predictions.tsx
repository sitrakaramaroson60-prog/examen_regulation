import { Fragment, useState } from "react"
import { Link } from "react-router"
import { Download, LineChart as LineIcon } from "lucide-react"
import { Badge, Button, Input, Select, Text } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, PageHeader, Section, StatusPill, Table } from "../components/kit"
import { fmtDateTime, fmtNum } from "../lib/format"
import { api, describeError, downloadFile, type Page } from "../lib/api"
import { useFetch } from "../lib/useFetch"

type RiskType = { risk_type: string; label: string; note: string }
type Model = {
  id: number; name: string; version: number; risk_type: string; risk_label: string; status: string; status_reason: string; created_at: string
  feature_schema: string[]
  metrics: {
    accuracy?: number; macro_f1?: number; n_train?: number; n_test?: number; split?: string
    precision?: Record<string, number>; recall?: Record<string, number>; f1?: Record<string, number>
    confusion_matrix?: { labels: string[]; matrix: number[][] }
    calibration?: { expected_calibration_error: number; multiclass_brier_score: number }
    feature_importance?: { feature: string; label: string; weight: number }[]
  }
}
type VersionRow = { id: number; dataset_name: string; version_number: number; data_type: string; row_count: number; report: { status: string } }
type Run = { id: number; model_name: string; model_number: number; risk_type: string; status: string; created_at: string; summary: { n_predicted?: number; needs_review?: number; class_counts?: Record<string, number>; error?: string } }
type Factor = { label: string; value: number; contribution: number; effect: string }
type Result = {
  id: number; area: { operator: string; region: string; technology: string; period: string } | null; observation_reference: string
  predicted_class: "GOOD" | "MEDIUM" | "POOR"; risk_label: string; confidence: number; needs_review: boolean
  probability_good: number; probability_medium: number; probability_poor: number; top_factors: Factor[]
}
type BuildResult = { dataset_version: number; dataset_name: string; rows: number; class_counts: Record<string, number>; periods: number; report_status: string; note: string }

const CLASS_TONE = { GOOD: "good", MEDIUM: "medium", POOR: "poor" } as const

export default function Predictions() {
  const risks = useFetch<RiskType[]>("/predictions/risk-types/")
  const models = useFetch<Page<Model>>("/predictions/models/")
  const runs = useFetch<Page<Run>>("/predictions/runs/")
  const versions = useFetch<VersionRow[]>("/datasets/versions/", { dataset__data_type: "LABELED_TRAINING" })

  const [risk, setRisk] = useState("GENERAL_QUALITY")
  const [granularity, setGranularity] = useState("month")
  const [includeDeclared, setIncludeDeclared] = useState(false)
  const [build, setBuild] = useState<BuildResult | null>(null)
  const [msg, setMsg] = useState<{ tone: "red" | "green" | "orange"; text: string } | null>(null)
  const [busy, setBusy] = useState("")
  const [trainVersion, setTrainVersion] = useState("")
  const [trainName, setTrainName] = useState("risque-qos")
  const [selectedRun, setSelectedRun] = useState<number | null>(null)
  const [openModel, setOpenModel] = useState<number | null>(null)

  const act = async (label: string, fn: () => Promise<void>) => {
    setBusy(label); setMsg(null)
    try { await fn() } catch (e) { setMsg({ tone: "red", text: describeError(e) }) } finally { setBusy("") }
  }

  const buildSet = () => act("build", async () => {
    const r = await api<BuildResult>("/predictions/training-sets/build/", { method: "POST", body: { risk_type: risk, granularity, sources: includeDeclared ? ["TECHNICAL", "DECLARED"] : ["TECHNICAL"] } })
    setBuild(r); setTrainVersion(String(r.dataset_version)); versions.reload()
    setMsg({ tone: "green", text: `Jeu étiqueté construit : ${r.rows} observations sur ${r.periods} périodes.` })
  })
  const train = () => act("train", async () => {
    const m = await api<Model>("/predictions/models/train/", { method: "POST", body: { name: trainName, training_dataset_version: Number(trainVersion), risk_type: risk } })
    models.reload(); setOpenModel(m.id)
    setMsg(m.status === "READY" ? { tone: "green", text: `Modèle ${m.name} v${m.version} prêt.` } : { tone: "orange", text: `Modèle ${m.name} v${m.version} : ${m.status_reason || m.status}` })
  })
  const forecast = (m: Model) => act(`f${m.id}`, async () => {
    const r = await api<Run>("/predictions/forecast/", { method: "POST", body: { model_version: m.id } })
    runs.reload(); setSelectedRun(r.id)
    setMsg(r.status === "COMPLETED" ? { tone: "green", text: `Prévision terminée : ${r.summary.n_predicted} zone(s), ${r.summary.needs_review ?? 0} à vérifier.` } : { tone: "red", text: r.summary.error ?? "La prévision a échoué." })
  })

  const currentRun = selectedRun ?? runs.data?.results[0]?.id ?? null
  const results = useFetch<Page<Result>>(currentRun ? `/predictions/runs/${currentRun}/results/` : null, { page_size: 200 })

  return (
    <div className="page-stack">
      <PageHeader title="Prédiction des problèmes de qualité de service" subtitle="Anticiper la période suivante plutôt que constater : chaque résultat indique une classe, un score de confiance et les facteurs qui l'expliquent." />
      <Notice tone="blue">Les prédictions sont des estimations probabilistes, jamais des certitudes ni des preuves de manquement. Elles peuvent alimenter une alerte ou l'ouverture d'un dossier, mais ne déclenchent aucune décision.</Notice>
      {msg && <Notice tone={msg.tone === "red" ? "red" : msg.tone}>{msg.text}</Notice>}

      <div className="grid-2">
        <Section title="1. Préparer les données" subtitle="Construit un jeu étiqueté à partir des mesures validées : variables de la période t, classe (seuils configurés) de la période t+1.">
          <div className="form-stack">
            <Select label="Risque à anticiper" value={risk} onChange={(e) => setRisk(e.target.value)}>
              {risks.data?.map((r) => <option key={r.risk_type} value={r.risk_type}>{r.label}</option>)}
            </Select>
            {risks.data?.find((r) => r.risk_type === risk)?.note && <Notice tone="orange">{risks.data.find((r) => r.risk_type === risk)!.note}</Notice>}
            <Select label="Pas de temps" value={granularity} onChange={(e) => setGranularity(e.target.value)}>
              <option value="week">Hebdomadaire</option><option value="month">Mensuel</option>
            </Select>
            <label style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 13 }}><input type="checkbox" checked={includeDeclared} onChange={(e) => setIncludeDeclared(e.target.checked)} /> Inclure aussi les données déclarées par les opérateurs (par défaut : mesures techniques uniquement)</label>
            <Button loading={busy === "build"} onClick={buildSet}>Construire le jeu d'entraînement</Button>
            {build && (
              <Notice tone="green">
                « {build.dataset_name} » : {build.rows} observations · {build.periods} périodes · classes {Object.entries(build.class_counts).map(([k, v]) => `${k} ${v}`).join(", ")} · validation : {build.report_status}.
              </Notice>
            )}
          </div>
        </Section>

        <Section title="2. Entraîner le modèle Softmax" subtitle="Régression logistique multinomiale : trois classes (faible / modéré / élevé), probabilités par Softmax.">
          <div className="form-stack">
            <Select label="Jeu étiqueté" value={trainVersion} onChange={(e) => setTrainVersion(e.target.value)}>
              <option value="">Sélectionner…</option>
              {versions.data?.filter((v) => v.report.status !== "INVALID").map((v) => <option key={v.id} value={v.id}>{v.dataset_name} — v{v.version_number} ({v.row_count} lignes)</option>)}
            </Select>
            <Input label="Nom du modèle" value={trainName} onChange={(e) => setTrainName(e.target.value)} />
            <Button loading={busy === "train"} disabled={!trainVersion || !trainName} onClick={train}>Entraîner et évaluer</Button>
            <Text as="small">Si l'historique est trop court ou déséquilibré, le modèle est déclaré « non prêt » avec le motif. L'évaluation se fait sur les périodes les plus récentes, séparées de l'entraînement.</Text>
          </div>
        </Section>
      </div>

      <Section title="3. Modèles" subtitle="Seul un modèle « prêt » peut produire des prévisions.">
        {models.loading && <Loading />}
        {models.error && <ErrorMsg>{models.error}</ErrorMsg>}
        {models.data && models.data.results.length === 0 && <Empty>Aucun modèle entraîné.</Empty>}
        {models.data && models.data.results.length > 0 && (
          <Table head={["Modèle", "Risque", "Statut", "Accuracy", "F1 macro", "Créé le", ""]}>
            {models.data.results.map((m) => (
              <Fragment key={m.id}>
                <tr>
                  <td><strong>{m.name} v{m.version}</strong></td><td>{m.risk_label}</td><td><StatusPill status={m.status} /></td>
                  <td>{fmtNum(m.metrics.accuracy)}</td><td>{fmtNum(m.metrics.macro_f1)}</td><td>{fmtDateTime(m.created_at)}</td>
                  <td style={{ whiteSpace: "nowrap" }}>
                    <button className="link-btn" onClick={() => setOpenModel(openModel === m.id ? null : m.id)}>{openModel === m.id ? "Masquer" : "Détails"}</button>{" "}
                    {m.status === "READY" && <Button size="sm" loading={busy === `f${m.id}`} onClick={() => forecast(m)}><LineIcon size={14} /> Prévoir</Button>}
                  </td>
                </tr>
                {openModel === m.id && (
                  <tr><td colSpan={7}><ModelDetails m={m} /></td></tr>
                )}
              </Fragment>
            ))}
          </Table>
        )}
      </Section>

      <Section title="4. Prévisions par zone" subtitle="Dernière période disponible de chaque opérateur, région et technologie."
        actions={
          <>
            <Select label="" aria-label="Exécution" value={currentRun ?? ""} onChange={(e) => setSelectedRun(Number(e.target.value))}>
              {runs.data?.results.map((r) => <option key={r.id} value={r.id}>#{r.id} — {r.model_name} v{r.model_number} ({fmtDateTime(r.created_at)})</option>)}
            </Select>
            {currentRun && <Button variant="secondary" size="sm" onClick={() => downloadFile(`/predictions/runs/${currentRun}/export/`, `prevision_${currentRun}.csv`)}><Download size={14} /> CSV</Button>}
          </>
        }>
        {!currentRun && <Empty>Aucune prévision pour l'instant. Entraînez un modèle prêt puis cliquez sur « Prévoir ».</Empty>}
        {results.loading && currentRun && <Loading />}
        {results.data && (
          <Table head={["Opérateur", "Région", "Techno.", "Période", "Risque", "Confiance", "Facteurs principaux"]}>
            {results.data.results.map((r) => (
              <tr key={r.id}>
                <td><strong>{r.area?.operator ?? r.observation_reference}</strong></td><td>{r.area?.region}</td><td>{r.area?.technology}</td><td>{r.area?.period}</td>
                <td><StatusPill status={r.predicted_class} /> <span className="ind-meta">{r.risk_label}</span>
                  <div className="ind-meta">G {fmtNum(r.probability_good * 100, 0)} % · M {fmtNum(r.probability_medium * 100, 0)} % · P {fmtNum(r.probability_poor * 100, 0)} %</div></td>
                <td>
                  <div className="conf"><strong>{fmtNum(r.confidence * 100, 0)} %</strong><div className="bar-track"><div className={`bar-fill ${CLASS_TONE[r.predicted_class]}`} style={{ width: `${r.confidence * 100}%` }} /></div></div>
                  {r.needs_review && <Badge tone="orange">À vérifier</Badge>}
                </td>
                <td>{r.top_factors.map((f) => <span key={f.label} className={`factor-chip ${f.contribution > 0 ? "up" : "down"}`} title={`valeur ${f.value} · contribution ${f.contribution}`}>{f.label} — {f.effect}</span>)}</td>
              </tr>
            ))}
          </Table>
        )}
        {results.data && results.data.results.length === 0 && <Empty>Cette exécution n'a produit aucune prévision (variables manquantes ou historique insuffisant).</Empty>}
        <Text as="small">Une zone à risque élevé peut justifier une <Link to="/regulation/conformite" className="link-btn">vérification des obligations</Link> ou l'ouverture d'un <Link to="/regulation/dossiers" className="link-btn">dossier</Link> — jamais une sanction automatique.</Text>
      </Section>
    </div>
  )
}

function ModelDetails({ m }: { m: Model }) {
  const mt = m.metrics
  if (m.status !== "READY" && m.status !== "LOW_QUALITY") return <Notice tone="orange">{m.status_reason || "Aucun détail disponible."}</Notice>
  return (
    <div className="grid-2" style={{ padding: "8px 0" }}>
      <div className="stack-sm">
        {m.status_reason && <Notice tone="red">{m.status_reason}</Notice>}
        <strong>Évaluation (jeu de test)</strong>
        <span className="ind-meta">{mt.split}</span>
        <span className="ind-meta">{mt.n_train} observations d'entraînement · {mt.n_test} de test</span>
        <Table head={["Classe", "Précision", "Rappel", "F1"]}>
          {["GOOD", "MEDIUM", "POOR"].map((c) => <tr key={c}><td><StatusPill status={c} /></td><td>{fmtNum(mt.precision?.[c])}</td><td>{fmtNum(mt.recall?.[c])}</td><td>{fmtNum(mt.f1?.[c])}</td></tr>)}
        </Table>
        {mt.confusion_matrix && (
          <table className="matrix">
            <thead><tr><th>Réel \ Prédit</th>{mt.confusion_matrix.labels.map((l) => <th key={l}>{l}</th>)}</tr></thead>
            <tbody>{mt.confusion_matrix.matrix.map((row, i) => <tr key={i}><th>{mt.confusion_matrix!.labels[i]}</th>{row.map((v, j) => <td key={j} className={i === j ? "diag" : ""}>{v}</td>)}</tr>)}</tbody>
          </table>
        )}
        {mt.calibration && <span className="ind-meta">Calibration : erreur attendue {fmtNum(mt.calibration.expected_calibration_error, 3)} · score de Brier {fmtNum(mt.calibration.multiclass_brier_score, 3)} (plus bas = mieux)</span>}
      </div>
      <div className="stack-sm">
        <strong>Variables les plus influentes</strong>
        {mt.feature_importance?.slice(0, 8).map((f) => (
          <div className="op-row" key={f.feature} style={{ gridTemplateColumns: "minmax(120px,1.2fr) 1fr auto" }}>
            <span>{f.label}</span><div className="bar-track"><div className="bar-fill" style={{ width: `${f.weight * 100 * 2.5}%` }} /></div><span className="val">{fmtNum(f.weight * 100, 0)} %</span>
          </div>
        ))}
      </div>
    </div>
  )
}
