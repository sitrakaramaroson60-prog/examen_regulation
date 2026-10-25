import { useMemo, useState } from "react"
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"
import { Card, Input, Select, Text } from "../components/ui"
import { Empty, ErrorMsg, Loading, Notice, Section, StatusPill, Table } from "../components/kit"
import { fmtNum } from "../lib/format"
import { useFetch } from "../lib/useFetch"

type OpValue = { operator: string; average: number | null; count: number; status: string | null }
type Group = { unit: string; method: string; operators: OpValue[]; comparable: boolean; trend: ({ month: string } & Record<string, number | string>)[] }
type Indicator = {
  metric: string; label: string; default_unit: string; higher_is_better: boolean
  threshold: { good: number; poor: number; origin: string } | null; groups: Group[]
}
type Dashboard = {
  period: { from: string; to: string }; sources: string[]; operators: string[]; indicators: Indicator[]
  coverage: ({ operator: string } & Record<string, number | string>)[]
  declared_vs_measured: { operator: string; metric: string; unit: string; method: string; declared: number; measured: number; gap: number; gap_pct: number | null }[]
  perception: { operator: string; average: number; responses: number }[]
  notes: string[]
}
type Region = { id: number; name: string }

const OP_COLORS = ["#1d4ed8", "#e08a1e", "#16855b", "#7c3aed", "#c73737", "#0891b2"]
const SOURCE_LABELS: Record<string, string> = { TECHNICAL: "Mesures techniques", DECLARED: "Déclarations opérateurs", SURVEY: "Sondages (perception)", SCRAPED: "Web scraping" }
const PERIODS: [string, string][] = [["30", "30 derniers jours"], ["90", "90 derniers jours"], ["180", "6 derniers mois"], ["365", "12 derniers mois"]]

const isoDaysAgo = (n: number) => new Date(Date.now() - n * 86400000).toISOString().slice(0, 10)

export default function Supervision({ own = false }: { own?: boolean }) {
  const [days, setDays] = useState("90")
  const [region, setRegion] = useState("")
  const [technology, setTechnology] = useState("")
  const [sources, setSources] = useState<string[]>(["TECHNICAL"])
  const [trendMetric, setTrendMetric] = useState("")
  const [chosen, setChosen] = useState<Record<string, string>>({})

  const regions = useFetch<Region[]>("/organizations/regions/", undefined, false)
  const dash = useFetch<Dashboard>("/qos/measurements/dashboard/", { date_from: isoDaysAgo(Number(days)), region, technology, sources: sources.join(",") })
  const d = dash.data

  const withData = useMemo(() => (d?.indicators ?? []).filter((i) => i.groups.length > 0), [d])
  const empty = useMemo(() => (d?.indicators ?? []).filter((i) => i.groups.length === 0 && i.metric !== "satisfaction"), [d])
  const trendInd = withData.find((i) => i.metric === (trendMetric || withData[0]?.metric))
  const trendGroup = trendInd?.groups[Number(chosen[trendInd.metric] ?? 0)] ?? trendInd?.groups[0]
  const toggleSource = (s: string) => setSources((cur) => { const next = cur.includes(s) ? cur.filter((x) => x !== s) : [...cur, s]; return next.length ? next : cur })

  return (
    <div className="page-stack">
      <Card className="kit-section">
        <div className="toolbar">
          <Select label="Période" value={days} onChange={(e) => setDays(e.target.value)}>
            {PERIODS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </Select>
          <Select label="Région" value={region} onChange={(e) => setRegion(e.target.value)}>
            <option value="">Toutes les régions</option>
            {regions.data?.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
          </Select>
          <Input label="Technologie" placeholder="ex. 4G" value={technology} onChange={(e) => setTechnology(e.target.value.trim())} />
          <div className="field">
            <span className="field-label">Sources</span>
            <div style={{ display: "flex", gap: 12, flexWrap: "wrap", minHeight: 42, alignItems: "center" }}>
              {Object.entries(SOURCE_LABELS).filter(([k]) => k !== "SCRAPED").map(([k, l]) => (
                <label key={k} className="check-row" style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 13 }}>
                  <input type="checkbox" checked={sources.includes(k)} onChange={() => toggleSource(k)} /> {l}
                </label>
              ))}
            </div>
          </div>
        </div>
        {!own && sources.some((s) => s !== "TECHNICAL") && (
          <Notice tone="blue">Les déclarations et les sondages sont affichés à titre de comparaison : seules les mesures techniques servent de référence pour l'évaluation des engagements.</Notice>
        )}
      </Card>

      {dash.loading && <Loading />}
      {dash.error && <ErrorMsg>{dash.error}</ErrorMsg>}
      {d?.notes.map((n) => <Notice key={n}>{n}</Notice>)}

      {d && (
        <>
          <div className="ind-grid">
            {withData.map((ind) => {
              const gi = Number(chosen[ind.metric] ?? 0)
              const g = ind.groups[gi] ?? ind.groups[0]
              const max = Math.max(...g.operators.map((o) => o.average ?? 0), ind.threshold?.good ?? 0, 0.0001)
              return (
                <Card className="ind-card" key={ind.metric}>
                  <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                    <div>
                      <h4>{ind.label}</h4>
                      <span className="ind-meta">{ind.higher_is_better ? "Plus élevé = meilleur" : "Plus bas = meilleur"} · {g.unit}</span>
                    </div>
                  </div>
                  {ind.groups.length > 1 && (
                    <Select label="Méthode de mesure" value={String(gi)} onChange={(e) => setChosen({ ...chosen, [ind.metric]: e.target.value })}>
                      {ind.groups.map((x, i) => <option key={i} value={i}>{x.method} ({x.unit})</option>)}
                    </Select>
                  )}
                  {ind.groups.length === 1 && <span className="ind-meta">Méthode : {g.method}</span>}
                  <div className="stack-sm">
                    {g.operators.map((o, i) => (
                      <div className="op-row" key={o.operator}>
                        <strong>{o.operator}</strong>
                        <div className="bar-track" title={`${o.count} mesure(s)`}>
                          <div className={`bar-fill ${o.status === "GOOD" ? "good" : o.status === "MEDIUM" ? "medium" : o.status === "POOR" ? "poor" : ""}`}
                            style={{ width: `${o.average === null ? 0 : Math.max(2, (o.average / max) * 100)}%`, background: o.status ? undefined : OP_COLORS[i % OP_COLORS.length] }} />
                        </div>
                        <span className="val">{o.average === null ? "Aucune donnée" : `${fmtNum(o.average)} ${g.unit}`}</span>
                      </div>
                    ))}
                  </div>
                  <div className="stack-sm">
                    <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
                      {g.operators.filter((o) => o.average !== null).map((o) => <span key={o.operator} style={{ display: "inline-flex", gap: 4, alignItems: "center", fontSize: 12 }}>{o.operator} <StatusPill status={o.status} /></span>)}
                    </div>
                    <span className="ind-meta">
                      {ind.threshold ? `Seuils : bon ${ind.higher_is_better ? "≥" : "≤"} ${ind.threshold.good} · mauvais ${ind.higher_is_better ? "<" : ">"} ${ind.threshold.poor} (${ind.threshold.origin})` : "Aucun seuil de référence configuré pour cet indicateur."}
                    </span>
                    {!own && !g.comparable && <span className="ind-meta">Comparaison impossible : moins de deux opérateurs ont des mesures avec cette méthode.</span>}
                  </div>
                </Card>
              )
            })}
          </div>
          {withData.length === 0 && !dash.loading && <Card className="kit-section"><Empty>Aucune mesure validée pour cette sélection. Les indicateurs apparaissent dès que des datasets sont acceptés par l'ARTEC.</Empty></Card>}
          {empty.length > 0 && withData.length > 0 && <Text as="small">Indicateurs sans donnée sur la période : {empty.map((i) => i.label).join(", ")}.</Text>}

          {trendInd && trendGroup && trendGroup.trend.length > 0 && (
            <Section title="Évolution mensuelle" subtitle="Moyenne mensuelle par opérateur, pour une seule méthode de mesure."
              actions={<Select label="" aria-label="Indicateur" value={trendInd.metric} onChange={(e) => setTrendMetric(e.target.value)}>{withData.map((i) => <option key={i.metric} value={i.metric}>{i.label}</option>)}</Select>}>
              <div className="chart-area">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendGroup.trend}>
                    <CartesianGrid stroke="#E2E8F0" strokeDasharray="4 4" vertical={false} />
                    <XAxis dataKey="month" tickLine={false} axisLine={false} />
                    <YAxis tickLine={false} axisLine={false} unit={` ${trendGroup.unit}`} width={70} />
                    <Tooltip /><Legend />
                    {d.operators.map((op, i) => <Line key={op} type="monotone" dataKey={op} stroke={OP_COLORS[i % OP_COLORS.length]} strokeWidth={2.5} dot={{ r: 3 }} connectNulls />)}
                  </LineChart>
                </ResponsiveContainer>
              </div>
              <span className="ind-meta">Méthode : {trendGroup.method}</span>
            </Section>
          )}

          <div className="grid-2">
            <Section title="Provenance des données" subtitle="Pour ne pas dépendre des seules déclarations ou des avis des usagers.">
              <Table head={["Opérateur", "Mesures techniques", "Déclarées", "Sondages", "Scraping"]}>
                {d.coverage.map((c) => (
                  <tr key={c.operator}><td><strong>{c.operator}</strong></td><td>{c.TECHNICAL}</td><td>{c.DECLARED}</td><td>{c.SURVEY}</td><td>{c.SCRAPED}</td></tr>
                ))}
              </Table>
            </Section>
            <Section title="Contrôle croisé : déclaré / mesuré" subtitle="Écart entre ce que déclare l'opérateur et ce qui est mesuré (même méthode).">
              {d.declared_vs_measured.length === 0 ? <Empty>Aucun indicateur disponible à la fois en déclaration et en mesure technique.</Empty> : (
                <Table head={["Opérateur", "Indicateur", "Déclaré", "Mesuré", "Écart"]}>
                  {d.declared_vs_measured.map((r, i) => (
                    <tr key={i}><td>{r.operator}</td><td>{r.metric}</td><td>{fmtNum(r.declared)} {r.unit}</td><td>{fmtNum(r.measured)} {r.unit}</td>
                      <td style={{ color: Math.abs(r.gap_pct ?? 0) >= 5 ? "var(--red)" : undefined }}>{fmtNum(r.gap)} ({r.gap_pct === null ? "—" : `${fmtNum(r.gap_pct, 1)} %`})</td></tr>
                  ))}
                </Table>
              )}
            </Section>
          </div>

          {d.perception.length > 0 && (
            <Section title="Perception des usagers (sondages)" subtitle="Score moyen de satisfaction sur 5, rapporté aux mesures techniques ci-dessus.">
              <Table head={["Opérateur", "Satisfaction moyenne", "Réponses"]}>
                {d.perception.map((p) => <tr key={p.operator}><td><strong>{p.operator}</strong></td><td>{fmtNum(p.average)} / 5</td><td>{p.responses}</td></tr>)}
              </Table>
            </Section>
          )}
        </>
      )}
    </div>
  )
}
