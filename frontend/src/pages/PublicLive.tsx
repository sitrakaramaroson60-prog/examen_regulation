import { useEffect, useMemo, useRef, useState } from "react"
import { Link, useParams } from "react-router"
import { ArrowRight, CalendarDays, CheckCircle2, Clock3, FileText, Landmark, Search, ShieldCheck, Signal } from "lucide-react"
import { Badge, Button, ButtonLink, Card, Heading, Input, Select, Text } from "../components/ui"
import { api, describeError, type Page } from "../lib/api"
import { useLiveTick } from "../lib/useLive"

/* ---------- types renvoyés par l'API ---------- */
type SurveyListItem = {
  id: number
  title: string
  description: string
  organization_code: string
  target_operator: string | null
  status: "PUBLISHED" | "CLOSED"
  ends_at: string | null
  estimated_minutes: number
  responses_count: number
  results_public: boolean
}
type Choice = { id: number; label: string }
type Question = {
  id: number
  text: string
  question_type: "SHORT_TEXT" | "LONG_TEXT" | "SINGLE_CHOICE" | "MULTIPLE_CHOICE" | "SATISFACTION" | "NUMBER" | "YES_NO"
  is_required: boolean
  min_value: number | null
  max_value: number | null
  choices: Choice[]
}
type SurveyDetail = SurveyListItem & { questions: Question[]; is_open: boolean }
type Region = { id: number; name: string; cities: { id: number; name: string }[] }
type PublicationItem = { id: number; title: string; slug: string; excerpt: string; content: string; category: string; published_at: string; organization_code: string }

const fmtDate = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("fr-FR") : "—")

function Loading({ text = "Chargement…" }: { text?: string }) {
  return <Card className="placeholder-card"><Text>{text}</Text></Card>
}
function ErrorBox({ message }: { message: string }) {
  return (
    <Card className="placeholder-card">
      <Heading>Service momentanément indisponible</Heading>
      <Text>{message}</Text>
    </Card>
  )
}

/* ---------- liste des sondages ---------- */
export function SurveysPage() {
  const [items, setItems] = useState<SurveyListItem[] | null>(null)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const live = useLiveTick(["surveys"])
  useEffect(() => {
    const t = window.setTimeout(() => {
      api<Page<SurveyListItem>>("/surveys/", { auth: false, query: { search } })
        .then((d) => { setItems(d.results); setError("") })
        .catch((e) => setError(describeError(e)))
    }, 250)
    return () => window.clearTimeout(t)
  }, [search, live])
  return (
    <section className="page-section">
      <div className="container">
        <div className="page-heading">
          <div>
            <Text as="small" className="eyebrow">PARTICIPATION PUBLIQUE</Text>
            <Heading as="h1">Sondages et consultations</Heading>
            <Text>Exprimez votre expérience des services de télécommunications. Aucun compte n’est nécessaire.</Text>
          </div>
        </div>
        <Card className="filter-bar">
          <div className="search-box">
            <Search size={18} />
            <Input placeholder="Rechercher un sondage…" value={search} onChange={(e) => setSearch(e.target.value)} />
          </div>
        </Card>
        {error && <ErrorBox message={error} />}
        {!error && items === null && <Loading />}
        {items && items.length === 0 && <Card className="placeholder-card"><Text>Aucun sondage publié pour le moment.</Text></Card>}
        <div className="survey-grid">
          {items?.map((s) => (
            <Card className="survey-card" key={s.id}>
              <div className="survey-top">
                <Badge tone={s.status === "PUBLISHED" ? "green" : "gray"}>{s.status === "PUBLISHED" ? "Ouvert" : "Clos"}</Badge>
                <span><Clock3 size={15} /> {s.estimated_minutes} min</span>
              </div>
              <Heading as="h3">{s.title}</Heading>
              {s.description && <Text>{s.description}</Text>}
              <div className="survey-meta">
                <span><Landmark size={16} /><small>Publié par</small><strong>{s.organization_code}</strong></span>
                <span><Signal size={16} /><small>Opérateur évalué</small><strong>{s.target_operator ?? "Tous"}</strong></span>
              </div>
              <div className="survey-footer">
                <span><CalendarDays size={15} /> {s.ends_at ? `Jusqu’au ${fmtDate(s.ends_at)}` : "Sans date limite"}</span>
                <span>{s.responses_count} réponses</span>
              </div>
              {s.status === "PUBLISHED" ? (
                <ButtonLink to={`/sondages/${s.id}`} className="full-button">Participer <ArrowRight size={16} /></ButtonLink>
              ) : (
                <ButtonLink to={`/sondages/${s.id}`} variant="secondary" className="full-button">Consulter</ButtonLink>
              )}
              {s.results_public && <ButtonLink to={`/sondages/${s.id}/resultats`} variant="ghost" className="full-button">Voir les résultats publics</ButtonLink>}
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ---------- formulaire de participation ---------- */
type AnswerValue = string | number | boolean | number[] | undefined

export function SurveyFormPage() {
  const { id } = useParams()
  const [survey, setSurvey] = useState<SurveyDetail | null>(null)
  const [regions, setRegions] = useState<Region[]>([])
  const [error, setError] = useState("")
  const [token, setToken] = useState("")
  const [step, setStep] = useState(1)
  const [regionId, setRegionId] = useState("")
  const [cityId, setCityId] = useState("")
  const [context, setContext] = useState<"USAGE" | "RESIDENCE">("USAGE")
  const [operator, setOperator] = useState("")
  const [answers, setAnswers] = useState<Record<number, AnswerValue>>({})
  const [website, setWebsite] = useState("") // champ piège anti-robot, jamais affiché
  const [submitting, setSubmitting] = useState(false)
  const [done, setDone] = useState(false)
  const [formError, setFormError] = useState("")
  const live = useLiveTick(["surveys"])
  const tokenLoaded = useRef(false) // le jeton de participation n'est demandé qu'une fois : son ancienneté minimale compte

  useEffect(() => {
    if (!id) return
    Promise.all([api<SurveyDetail>(`/surveys/${id}/`, { auth: false }), api<Region[]>("/organizations/regions/", { auth: false })])
      .then(([s, r]) => {
        setSurvey(s)
        setRegions(r)
        if (s.target_operator) setOperator(s.target_operator)
        if (s.is_open && !tokenLoaded.current) { tokenLoaded.current = true; api<{ participation_token: string }>(`/surveys/${id}/participation-token/`, { auth: false }).then((t) => setToken(t.participation_token)).catch(() => { tokenLoaded.current = false }) }
      })
      .catch((e) => setError(describeError(e)))
  }, [id, live])

  const cities = useMemo(() => regions.find((r) => String(r.id) === regionId)?.cities ?? [], [regions, regionId])
  const set = (qid: number, v: AnswerValue) => setAnswers((a) => ({ ...a, [qid]: v }))

  if (error) return <section className="page-section"><div className="container narrow"><ErrorBox message={error} /></div></section>
  if (!survey) return <section className="page-section"><div className="container narrow"><Loading /></div></section>

  const missingRequired = survey.questions.filter((q) => q.is_required && (answers[q.id] === undefined || answers[q.id] === "" || (Array.isArray(answers[q.id]) && (answers[q.id] as number[]).length === 0)))

  const submit = async () => {
    setSubmitting(true)
    setFormError("")
    try {
      await api(`/surveys/${survey.id}/responses/`, {
        method: "POST",
        auth: false,
        body: {
          region: Number(regionId),
          city: Number(cityId),
          location_context: context,
          operator: operator || null,
          participation_token: token,
          website,
          answers: Object.entries(answers)
            .filter(([, v]) => v !== undefined && v !== "")
            .map(([q, v]) => ({ question: Number(q), value: v })),
        },
      })
      setDone(true)
    } catch (e) {
      setFormError(describeError(e))
    } finally {
      setSubmitting(false)
    }
  }

  if (done)
    return (
      <section className="page-section survey-form-page">
        <div className="container narrow">
          <Card className="placeholder-card">
            <CheckCircle2 size={36} />
            <Heading>Merci pour votre participation</Heading>
            <Text>Votre réponse a bien été enregistrée de façon anonyme.</Text>
            <ButtonLink to="/sondages" variant="secondary">Retour aux sondages</ButtonLink>
          </Card>
        </div>
      </section>
    )

  const steps = ["Localisation", "Opérateur", "Évaluation", "Vérification"]
  return (
    <section className="page-section survey-form-page">
      <div className="container narrow">
        <Link to="/sondages" className="back-link">← Retour aux sondages</Link>
        <div className="form-title">
          <div>
            <Badge tone={survey.is_open ? "green" : "gray"}>{survey.is_open ? "Sondage ouvert" : "Sondage clos"}</Badge>
            <Heading as="h1">{survey.title}</Heading>
            <Text>Publié par {survey.organization_code} · Temps estimé : {survey.estimated_minutes} minutes</Text>
          </div>
        </div>
        {!survey.is_open ? (
          <Card className="placeholder-card"><Text>Ce sondage n’accepte plus de réponses.</Text></Card>
        ) : (
          <>
            <div className="progress-wrap">
              <div className="progress-labels">{steps.map((s) => <span key={s}>{s}</span>)}</div>
              <div className="progress-track"><span style={{ width: `${step * 25}%` }} /></div>
              <Text as="small">Étape {step} sur 4</Text>
            </div>
            <Card className="survey-form-card">
              {step === 1 && (
                <>
                  <Heading as="h2">Où avez-vous utilisé le service ?</Heading>
                  <div className="privacy-note">
                    <ShieldCheck size={20} />
                    <Text>Aucune adresse exacte, coordonnée GPS, identité ou numéro de téléphone ne vous sera demandé.</Text>
                  </div>
                  {regions.length === 0 && <Text>Le référentiel des régions n’est pas encore configuré.</Text>}
                  <div className="form-grid">
                    <Select label="Région *" value={regionId} onChange={(e) => { setRegionId(e.target.value); setCityId("") }}>
                      <option value="">Sélectionner une région</option>
                      {regions.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
                    </Select>
                    <Select label="Ville *" disabled={!regionId} value={cityId} onChange={(e) => setCityId(e.target.value)}>
                      <option value="">Sélectionner une ville</option>
                      {cities.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
                    </Select>
                  </div>
                  <Select label="Cette localisation correspond à" value={context} onChange={(e) => setContext(e.target.value as "USAGE" | "RESIDENCE")}>
                    <option value="USAGE">Mon lieu d’utilisation du service</option>
                    <option value="RESIDENCE">Mon lieu de résidence</option>
                  </Select>
                </>
              )}
              {step === 2 && (
                <>
                  <Heading as="h2">Quel opérateur évaluez-vous ?</Heading>
                  <Select label="Opérateur concerné" value={operator} disabled={!!survey.target_operator} onChange={(e) => setOperator(e.target.value)}>
                    <option value="">Non précisé</option>
                    <option>YAS</option>
                    <option>AIRTEL</option>
                    <option>ORANGE</option>
                  </Select>
                </>
              )}
              {step === 3 && (
                <>
                  <Heading as="h2">Votre évaluation</Heading>
                  {survey.questions.map((q) => (
                    <QuestionField key={q.id} q={q} value={answers[q.id]} onChange={(v) => set(q.id, v)} />
                  ))}
                  <input type="text" tabIndex={-1} autoComplete="off" aria-hidden="true" value={website} onChange={(e) => setWebsite(e.target.value)} style={{ position: "absolute", left: "-9999px" }} />
                </>
              )}
              {step === 4 && (
                <>
                  <Heading as="h2">Vérification</Heading>
                  <Text>Région : <strong>{regions.find((r) => String(r.id) === regionId)?.name}</strong> · Ville : <strong>{cities.find((c) => String(c.id) === cityId)?.name}</strong></Text>
                  <Text>{Object.keys(answers).length} réponse(s) renseignée(s).</Text>
                  {missingRequired.length > 0 && <p className="field-error">Questions obligatoires sans réponse : {missingRequired.length}.</p>}
                  {formError && <p className="field-error" role="alert">{formError}</p>}
                </>
              )}
              <div className="form-actions">
                <Button variant="secondary" disabled={step === 1} onClick={() => setStep(Math.max(1, step - 1))}>Précédent</Button>
                <Text as="small">Vos réponses ne sont envoyées qu’à l’étape finale.</Text>
                {step < 4 ? (
                  <Button disabled={(step === 1 && (!regionId || !cityId)) || (step === 3 && missingRequired.length > 0)} onClick={() => setStep(step + 1)}>
                    Continuer <ArrowRight size={17} />
                  </Button>
                ) : (
                  <Button loading={submitting} disabled={missingRequired.length > 0 || !token} onClick={submit}>Envoyer</Button>
                )}
              </div>
            </Card>
          </>
        )}
      </div>
    </section>
  )
}

function QuestionField({ q, value, onChange }: { q: Question; value: AnswerValue; onChange: (v: AnswerValue) => void }) {
  const label = `${q.text}${q.is_required ? " *" : ""}`
  switch (q.question_type) {
    case "SHORT_TEXT":
      return <Input label={label} maxLength={255} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />
    case "LONG_TEXT":
      return (
        <label className="field">
          <span className="field-label">{label}</span>
          <textarea className="input" rows={4} maxLength={2000} value={(value as string) ?? ""} onChange={(e) => onChange(e.target.value)} />
        </label>
      )
    case "NUMBER":
      return <Input label={label} type="number" min={q.min_value ?? undefined} max={q.max_value ?? undefined} value={(value as number) ?? ""} onChange={(e) => onChange(e.target.value === "" ? undefined : Number(e.target.value))} />
    case "SATISFACTION":
      return (
        <div className="field">
          <span className="field-label">{label}</span>
          <div className="choice-grid">
            {[1, 2, 3, 4, 5].map((n) => (
              <Button key={n} type="button" variant={value === n ? "primary" : "secondary"} className="choice-button" onClick={() => onChange(n)}>{n}</Button>
            ))}
          </div>
        </div>
      )
    case "YES_NO":
      return (
        <div className="field">
          <span className="field-label">{label}</span>
          <div className="choice-grid">
            <Button type="button" variant={value === true ? "primary" : "secondary"} className="choice-button" onClick={() => onChange(true)}>Oui</Button>
            <Button type="button" variant={value === false ? "primary" : "secondary"} className="choice-button" onClick={() => onChange(false)}>Non</Button>
          </div>
        </div>
      )
    case "SINGLE_CHOICE":
      return (
        <div className="field">
          <span className="field-label">{label}</span>
          <div className="choice-grid">
            {q.choices.map((c) => (
              <Button key={c.id} type="button" variant={value === c.id ? "primary" : "secondary"} className="choice-button" onClick={() => onChange(c.id)}>{c.label}</Button>
            ))}
          </div>
        </div>
      )
    case "MULTIPLE_CHOICE": {
      const current = (value as number[] | undefined) ?? []
      return (
        <div className="field">
          <span className="field-label">{label}</span>
          {q.choices.map((c) => (
            <label className="check-row" key={c.id}>
              <input type="checkbox" checked={current.includes(c.id)} onChange={(e) => onChange(e.target.checked ? [...current, c.id] : current.filter((x) => x !== c.id))} />
              <span>{c.label}</span>
            </label>
          ))}
        </div>
      )
    }
  }
}

/* ---------- publications publiques ---------- */
export function PublicationsPage({ category, title = "Publications", intro = "Informations et communications publiées par l’ARTEC et les opérateurs." }: { category?: string; title?: string; intro?: string }) {
  const [items, setItems] = useState<PublicationItem[] | null>(null)
  const [error, setError] = useState("")
  const [search, setSearch] = useState("")
  const live = useLiveTick(["publications"])
  useEffect(() => {
    const t = window.setTimeout(() => {
      api<Page<PublicationItem>>("/publications/public/", { auth: false, query: { search, category } })
        .then((d) => { setItems(d.results); setError("") })
        .catch((e) => setError(describeError(e)))
    }, 250)
    return () => window.clearTimeout(t)
  }, [search, category, live])
  return (
    <section className="page-section">
      <div className="container">
        <div className="page-heading">
          <div>
            <Text as="small" className="eyebrow">ESPACE PUBLIC</Text>
            <Heading as="h1">{title}</Heading>
            <Text>{intro}</Text>
          </div>
        </div>
        <Card className="filter-bar">
          <div className="search-box"><Search size={18} /><Input placeholder="Rechercher une publication…" value={search} onChange={(e) => setSearch(e.target.value)} /></div>
        </Card>
        {error && <ErrorBox message={error} />}
        {!error && items === null && <Loading />}
        {items && items.length === 0 && <Card className="placeholder-card"><FileText size={36} /><Text>Aucune publication pour le moment.</Text></Card>}
        <div className="survey-grid">
          {items?.map((p) => (
            <Card className="survey-card" key={p.id}>
              <div className="survey-top"><Badge>{p.organization_code}</Badge><span>{fmtDate(p.published_at)}</span></div>
              <Heading as="h3">{p.title}</Heading>
              <Text>{p.excerpt}</Text>
              <ButtonLink to={`/publications/${p.slug}`} variant="secondary" className="full-button">Lire <ArrowRight size={16} /></ButtonLink>
            </Card>
          ))}
        </div>
      </div>
    </section>
  )
}

type PublicComment = { id: number; content: string; author_name: string; created_at: string }

export function PublicationDetailPage() {
  const { slug } = useParams()
  const [pub, setPub] = useState<PublicationItem | null>(null)
  const [comments, setComments] = useState<PublicComment[]>([])
  const [error, setError] = useState("")
  const [text, setText] = useState("")
  const [name, setName] = useState("")
  const [website, setWebsite] = useState("")
  const [notice, setNotice] = useState("")
  const live = useLiveTick(["publications", "comments"])
  useEffect(() => {
    api<PublicationItem>(`/publications/public/${slug}/`, { auth: false })
      .then((p) => {
        setPub(p)
        return api<Page<PublicComment>>("/comments/", { auth: false, query: { publication: p.id } })
      })
      .then((c) => setComments(c.results))
      .catch((e) => setError(describeError(e)))
  }, [slug, live])
  const send = async () => {
    setNotice("")
    try {
      const r = await api<{ message: string }>("/comments/", { method: "POST", auth: false, body: { publication: pub!.id, content: text, author_name: name, website } })
      setNotice(r.message)
      setText("")
    } catch (e) {
      setNotice(describeError(e))
    }
  }
  if (error) return <section className="page-section"><div className="container narrow"><ErrorBox message={error} /></div></section>
  if (!pub) return <section className="page-section"><div className="container narrow"><Loading /></div></section>
  return (
    <section className="page-section">
      <div className="container narrow">
        <Link to="/publications" className="back-link">← Retour aux publications</Link>
        <Badge>{pub.organization_code}</Badge>
        <Heading as="h1">{pub.title}</Heading>
        <Text as="small">{fmtDate(pub.published_at)}</Text>
        {/* Contenu rendu en texte brut : jamais de HTML injecté depuis l'API. */}
        <Card><p style={{ whiteSpace: "pre-wrap" }}>{pub.content}</p></Card>
        <Heading as="h2">Commentaires</Heading>
        {comments.length === 0 && <Text>Aucun commentaire approuvé.</Text>}
        {comments.map((c) => (
          <Card key={c.id}><strong>{c.author_name}</strong><p style={{ whiteSpace: "pre-wrap" }}>{c.content}</p></Card>
        ))}
        <Card>
          <Heading as="h3">Laisser un commentaire</Heading>
          <Input label="Nom (facultatif)" maxLength={80} value={name} onChange={(e) => setName(e.target.value)} />
          <label className="field">
            <span className="field-label">Commentaire</span>
            <textarea className="input" rows={4} maxLength={2000} value={text} onChange={(e) => setText(e.target.value)} />
          </label>
          <input type="text" tabIndex={-1} autoComplete="off" aria-hidden="true" value={website} onChange={(e) => setWebsite(e.target.value)} style={{ position: "absolute", left: "-9999px" }} />
          <Text as="small">Les commentaires sont modérés avant publication.</Text>
          {notice && <p role="status">{notice}</p>}
          <Button disabled={text.trim().length < 3} onClick={send}>Envoyer</Button>
        </Card>
      </div>
    </section>
  )
}


/* ---------- baromètre public de la qualité ---------- */
type PublicSummary = {
  enabled: boolean; message?: string; period_days: number
  participation: { open_surveys: number; responses: number; publications: number }
  indicators: { metric: string; label: string; unit: string; method: string; higher_is_better: boolean; operators: { operator: string; average: number; status: "GOOD" | "MEDIUM" | "POOR" | null }[] }[]
}
const STATUS_LABEL = { GOOD: "Bon", MEDIUM: "Moyen", POOR: "Mauvais" } as const

export function QualityPage() {
  const [data, setData] = useState<PublicSummary | null>(null)
  const [error, setError] = useState("")
  const live = useLiveTick(["qos"])
  useEffect(() => {
    api<PublicSummary>("/qos/public/", { auth: false }).then(setData).catch((e) => setError(describeError(e)))
  }, [live])
  return (
    <section className="page-section">
      <div className="container">
        <div className="page-heading">
          <div>
            <Text as="small" className="eyebrow">TRANSPARENCE</Text>
            <Heading as="h1">Qualité des services</Heading>
            <Text>Moyennes des mesures techniques validées par l’ARTEC sur les {data?.period_days ?? 90} derniers jours, par opérateur.</Text>
          </div>
        </div>
        {error && <ErrorBox message={error} />}
        {!data && !error && <Loading />}
        {data && !data.enabled && <Card className="placeholder-card"><ShieldCheck size={36} /><Heading>Baromètre en préparation</Heading><Text>{data.message}</Text><ButtonLink to="/sondages" variant="secondary">Participer à un sondage</ButtonLink></Card>}
        {data?.enabled && data.indicators.length === 0 && <Card className="placeholder-card"><Text>Pas encore assez de mesures validées pour publier des moyennes.</Text></Card>}
        <div className="survey-grid">
          {data?.enabled && data.indicators.map((i) => (
            <Card className="survey-card" key={i.metric}>
              <Heading as="h3">{i.label}</Heading>
              <Text as="small">{i.higher_is_better ? "Plus élevé = meilleur" : "Plus bas = meilleur"} · méthode : {i.method}</Text>
              {i.operators.map((o) => (
                <div key={o.operator} style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
                  <strong>{o.operator}</strong><span>{o.average.toLocaleString("fr-FR")} {i.unit}</span>
                  {o.status ? <Badge tone={o.status === "GOOD" ? "green" : o.status === "MEDIUM" ? "orange" : "red"}>{STATUS_LABEL[o.status]}</Badge> : <Badge tone="gray">—</Badge>}
                </div>
              ))}
            </Card>
          ))}
        </div>
        {data?.enabled && <Text as="small">Les moyennes ne sont publiées que lorsque le nombre de mesures est suffisant. Les déclarations des opérateurs ne figurent jamais dans ce baromètre.</Text>}
      </div>
    </section>
  )
}
