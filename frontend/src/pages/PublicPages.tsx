import { Link } from "react-router"
import { ArrowRight, BarChart3, CheckCircle2, ChevronRight, FileCheck2, FileText, Landmark, MessageSquareText, ShieldCheck, UsersRound } from "lucide-react"
import { Badge, ButtonLink, Card, Heading, Text } from "../components/ui"
import {  } from "../components/kit"
import { fmtDate } from "../lib/format"
import { type Page } from "../lib/api"
import { useFetch } from "../lib/useFetch"

type Summary = { enabled: boolean; participation: { open_surveys: number; responses: number; publications: number }; indicators: unknown[] }
type SurveyItem = { id: number; title: string; description: string; organization_code: string; estimated_minutes: number; ends_at: string | null; responses_count: number }
type PubItem = { id: number; title: string; slug: string; excerpt: string; category: string; published_at: string; organization_code: string }

export function HomePage() {
  const summary = useFetch<Summary>("/qos/public/", undefined, false)
  const surveys = useFetch<Page<SurveyItem>>("/surveys/", { page_size: 3 }, false)
  const pubs = useFetch<Page<PubItem>>("/publications/public/", { page_size: 3 }, false)
  const p = summary.data?.participation
  return (
    <>
      <section className="hero">
        <div className="hero-grid" />
        <div className="container hero-content">
          <div className="hero-copy">
            <Badge tone="blue"><Landmark size={14} /> Initiative de régulation numérique</Badge>
            <Heading as="h1">Une meilleure qualité des télécommunications, <span>mesurée ensemble.</span></Heading>
            <Text>Une plateforme nationale pour collecter, analyser et partager des données fiables sur la qualité des services de télécommunications à Madagascar.</Text>
            <div className="hero-actions">
              <ButtonLink to="/sondages">Participer à un sondage <ArrowRight size={18} /></ButtonLink>
              <ButtonLink to="/qualite" variant="secondary">Voir la qualité des services</ButtonLink>
            </div>
            <div className="hero-trust">
              <span><CheckCircle2 size={16} /> Participation sans compte</span>
              <span><ShieldCheck size={16} /> Réponses anonymes</span>
              <span><FileCheck2 size={16} /> Données validées par l’ARTEC</span>
            </div>
          </div>
          <Card className="hero-panel">
            <div className="panel-head">
              <div><Text as="small">PARTICIPATION</Text><Heading as="h3">En ce moment</Heading></div>
              <Badge tone="green">Données en direct</Badge>
            </div>
            <div className="chart-summary" style={{ marginTop: 18 }}>
              <div><Text as="small">Sondages ouverts</Text><strong>{p?.open_surveys ?? "—"}</strong></div>
              <div><Text as="small">Réponses (résultats publics)</Text><strong>{p?.responses ?? "—"}</strong></div>
              <div><Text as="small">Publications</Text><strong>{p?.publications ?? "—"}</strong></div>
            </div>
            <Text as="small" className="panel-note">
              {summary.data?.enabled ? `${summary.data.indicators.length} indicateur(s) de qualité publié(s) dans le baromètre.` : "Le baromètre public de la qualité sera publié par l’ARTEC après validation des mesures."}
            </Text>
          </Card>
        </div>
      </section>

      <section className="section container">
        <div className="section-heading centered">
          <Text as="small" className="eyebrow">UNE MISSION PARTAGÉE</Text>
          <Heading>Des données au service de l’intérêt général</Heading>
          <Text>La plateforme réunit citoyens, opérateurs et autorité de régulation autour d’une information vérifiable.</Text>
        </div>
        <div className="feature-grid">
          <Card className="feature-card"><span className="feature-icon"><MessageSquareText /></span><Heading as="h3">Écouter les usagers</Heading><Text>Recueillir des retours structurés sur la qualité ressentie, par région et par opérateur.</Text><Link to="/sondages">Voir les sondages <ChevronRight size={16} /></Link></Card>
          <Card className="feature-card"><span className="feature-icon"><BarChart3 /></span><Heading as="h3">Mesurer objectivement</Heading><Text>Comparer les mesures techniques selon une méthodologie commune, sans dépendre des seules déclarations.</Text><Link to="/qualite">Découvrir les indicateurs <ChevronRight size={16} /></Link></Card>
          <Card className="feature-card"><span className="feature-icon"><ShieldCheck /></span><Heading as="h3">Éclairer la régulation</Heading><Text>Fournir aux agents des analyses traçables, sans jamais automatiser les décisions officielles.</Text><Link to="/a-propos">Comprendre la démarche <ChevronRight size={16} /></Link></Card>
        </div>
      </section>

      <section className="section section-muted">
        <div className="container">
          <div className="section-heading split">
            <div><Text as="small" className="eyebrow">PARTICIPEZ</Text><Heading>Sondages actuellement ouverts</Heading></div>
            <ButtonLink to="/sondages" variant="secondary">Voir tous les sondages <ArrowRight size={16} /></ButtonLink>
          </div>
          {surveys.data?.results.length === 0 && <Text>Aucun sondage ouvert pour le moment.</Text>}
          <div className="survey-grid">
            {surveys.data?.results.map((s) => (
              <Card className="survey-card" key={s.id}>
                <div className="survey-top"><Badge tone="green">Ouvert</Badge><span>{s.estimated_minutes} min</span></div>
                <Heading as="h3">{s.title}</Heading>
                {s.description && <Text>{s.description}</Text>}
                <div className="survey-footer"><span>{s.ends_at ? `Jusqu’au ${fmtDate(s.ends_at)}` : "Sans date limite"}</span><span>{s.responses_count} réponses</span></div>
                <ButtonLink to={`/sondages/${s.id}`} className="full-button">Participer <ArrowRight size={16} /></ButtonLink>
              </Card>
            ))}
          </div>
        </div>
      </section>

      <section className="section container">
        <div className="section-heading split">
          <div><Text as="small" className="eyebrow">INFORMATIONS</Text><Heading>Dernières publications</Heading></div>
          <ButtonLink to="/publications" variant="ghost">Toutes les publications <ArrowRight size={16} /></ButtonLink>
        </div>
        {pubs.data?.results.length === 0 && <Text>Aucune publication pour le moment.</Text>}
        <div className="publication-list">
          {pubs.data?.results.map((item) => (
            <Card className="publication-item" key={item.id}>
              <span className="document-icon"><FileText /></span>
              <div className="publication-content">
                <div><Badge tone="blue">{item.category}</Badge><Text as="small">{item.organization_code} · {fmtDate(item.published_at)}</Text></div>
                <Heading as="h3">{item.title}</Heading>
                <Text>{item.excerpt}</Text>
              </div>
              <ButtonLink to={`/publications/${item.slug}`} variant="ghost" aria-label="Lire la publication"><ArrowRight size={19} /></ButtonLink>
            </Card>
          ))}
        </div>
      </section>

      <section className="participate-band">
        <div className="container participate-content">
          <span className="large-icon"><UsersRound /></span>
          <div><Heading>Votre expérience compte</Heading><Text>Répondez en quelques minutes. Aucun nom, numéro de téléphone ou position GPS n’est demandé.</Text></div>
          <ButtonLink to="/sondages" variant="secondary">Participer maintenant <ArrowRight size={17} /></ButtonLink>
        </div>
      </section>
    </>
  )
}

const INFO: Record<string, { title: string; paragraphs: string[] }> = {
  "a-propos": {
    title: "À propos de la plateforme",
    paragraphs: [
      "Cette plateforme réunit l’ARTEC, les opérateurs YAS, AIRTEL et ORANGE et le public autour d’un objectif : mesurer et améliorer la qualité des services de télécommunications.",
      "Les opérateurs collectent leurs propres données et les soumettent à l’ARTEC, qui les examine avant de les intégrer à ses analyses. Le public peut répondre aux sondages et commenter les publications sans créer de compte.",
      "L’ARTEC compare les indicateurs de qualité (disponibilité, débits, latence, gigue, perte de paquets, taux de réussite et de coupure des appels) et suit les engagements de chaque opérateur. Un modèle statistique de classification (Softmax) aide à anticiper les dégradations ; ses résultats sont des estimations, jamais des décisions : les avertissements, demandes d’explication et félicitations restent des actes formels pris et motivés par l’autorité compétente.",
    ],
  },
  confidentialite: {
    title: "Politique de confidentialité",
    paragraphs: [
      "Sondages : nous recueillons votre région, votre ville, le contexte (résidence ou lieu d’utilisation) et vos réponses. Aucune adresse exacte, coordonnée GPS, identité ou numéro de téléphone n’est demandé. Une empreinte technique irréversible et salée, non réutilisable pour vous identifier, sert uniquement à limiter les réponses répétées.",
      "Commentaires : votre texte et un nom facultatif sont conservés ; ils sont modérés avant publication. Réclamations : un contact facultatif peut être indiqué ; un jeton de suivi vous est remis une seule fois.",
      "Les résultats publics sont agrégés et ne sont publiés qu’à partir d’un nombre minimal de réponses. Ce texte est un document d’information à faire valider par l’ARTEC avant toute mise en ligne officielle.",
    ],
  },
  accessibilite: {
    title: "Accessibilité",
    paragraphs: [
      "La plateforme vise une utilisation simple sur téléphone et sur ordinateur, avec une navigation au clavier et des contrastes lisibles.",
      "Si vous rencontrez une difficulté d’accès, vous pouvez la signaler à l’ARTEC par le formulaire de réclamation.",
    ],
  },
}

export function InfoPage({ page }: { page: keyof typeof INFO }) {
  const c = INFO[page]
  return (
    <section className="page-section">
      <div className="container narrow">
        <div className="page-heading"><div><Text as="small" className="eyebrow">ESPACE PUBLIC</Text><Heading as="h1">{c.title}</Heading></div></div>
        <Card className="kit-section">{c.paragraphs.map((t, i) => <Text key={i}>{t}</Text>)}</Card>
      </div>
    </section>
  )
}

export function NotFoundPage() {
  return (
    <section className="page-section"><div className="container narrow"><Card className="placeholder-card"><Heading>Page introuvable</Heading><ButtonLink to="/" variant="secondary">Retour à l’accueil</ButtonLink></Card></div></section>
  )
}
