import { createBrowserRouter } from "react-router"
import PublicLayout from "../components/PublicLayout"
import AppLayout from "../components/AppLayout"
import { HomePage, InfoPage, NotFoundPage } from "../pages/PublicPages"
import { PublicationDetailPage, PublicationsPage, QualityPage, SurveyFormPage, SurveysPage } from "../pages/PublicLive"
import { RequireSpace } from "../lib/RequireSpace"
import * as W from "../pages/Workspace"
import LoginPage from "../pages/LoginPage"
import Account from "../pages/Account"
import Predictions from "../pages/Predictions"
import Compliance, { MyCompliance } from "../pages/Compliance"
import { CaseDetail, CasesList } from "../pages/Cases"
import { SurveyBuilder, SurveyManager, SurveyResults } from "../pages/Surveys"
import Thresholds from "../pages/Thresholds"
import { OperatorHome, PublisherHome, RegulationHome } from "../pages/Homes"
import Accounts from "../pages/Accounts"
import Scraping from "../pages/Scraping"
import { ComplaintDetail, ComplaintsList } from "../pages/Complaints"
import { PublicSurveyResults, ReportProblemPage, TrackComplaintPage } from "../pages/PublicReport"

const common = [
  { path: "notifications", Component: W.NotificationsPage },
  { path: "compte", Component: Account },
]

export const router = createBrowserRouter([
  {
    path: "/",
    Component: PublicLayout,
    children: [
      { index: true, Component: HomePage },
      { path: "publications", element: <PublicationsPage /> },
      { path: "publications/:slug", Component: PublicationDetailPage },
      { path: "sondages", Component: SurveysPage },
      { path: "sondages/:id", Component: SurveyFormPage },
      { path: "sondages/:id/resultats", Component: PublicSurveyResults },
      { path: "signalement", Component: ReportProblemPage },
      { path: "signalement/suivi", Component: TrackComplaintPage },
      { path: "qualite", Component: QualityPage },
      { path: "rapports", element: <PublicationsPage category="REPORT" title="Rapports publics" intro="Rapports validés et publiés par l’ARTEC." /> },
      { path: "a-propos", element: <InfoPage page="a-propos" /> },
      { path: "confidentialite", element: <InfoPage page="confidentialite" /> },
      { path: "accessibilite", element: <InfoPage page="accessibilite" /> },
      { path: "*", Component: NotFoundPage },
    ],
  },
  { path: "/connexion", Component: LoginPage },
  {
    path: "/regulation",
    element: (
      <RequireSpace spaces={["regulation"]}>
        <AppLayout mode="regulation" />
      </RequireSpace>
    ),
    children: [
      { index: true, Component: RegulationHome },
      { path: "predictions", Component: Predictions },
      { path: "conformite", Component: Compliance },
      { path: "dossiers", element: <CasesList regulator /> },
      { path: "dossiers/:id", Component: CaseDetail },
      { path: "soumissions", Component: W.RegulationSubmissions },
      { path: "indicateurs", Component: W.QosPage },
      { path: "seuils", element: <Thresholds /> },
      { path: "sondages", element: <SurveyManager base="/regulation" /> },
      { path: "sondages/nouveau", element: <SurveyBuilder base="/regulation" /> },
      { path: "sondages/:id", element: <SurveyResults base="/regulation" /> },
      { path: "rapports", Component: W.PublicationsAdmin },
      { path: "commentaires", Component: W.CommentsAdmin },
      { path: "reclamations", element: <ComplaintsList base="/regulation" /> },
      { path: "reclamations/:id", element: <ComplaintDetail base="/regulation" /> },
      { path: "comptes", Component: Accounts },
      { path: "historique", Component: W.AuditPage },
      ...common,
      { path: "*", Component: NotFoundPage },
    ],
  },
  {
    path: "/administration",
    element: (
      <RequireSpace spaces={["admin"]}>
        <AppLayout mode="admin" />
      </RequireSpace>
    ),
    children: [
      { index: true, Component: Accounts },
      { path: "historique", Component: W.AuditPage },
      ...common,
      { path: "*", Component: NotFoundPage },
    ],
  },
  {
    path: "/operateur",
    element: (
      <RequireSpace spaces={["operator"]}>
        <AppLayout mode="operator" />
      </RequireSpace>
    ),
    children: [
      { index: true, Component: OperatorHome },
      { path: "conformite", Component: MyCompliance },
      { path: "mesures", Component: W.QosPage },
      { path: "datasets", Component: W.OperatorDatasets },
      { path: "soumissions", Component: W.OperatorSubmissions },
      { path: "sondages", element: <SurveyManager base="/operateur" /> },
      { path: "sondages/nouveau", element: <SurveyBuilder base="/operateur" /> },
      { path: "sondages/:id", element: <SurveyResults base="/operateur" /> },
      { path: "publications", Component: W.PublicationsAdmin },
      { path: "scraping", Component: Scraping },
      { path: "dossiers", element: <CasesList regulator={false} /> },
      { path: "dossiers/:id", Component: CaseDetail },
      { path: "reclamations", element: <ComplaintsList base="/operateur" /> },
      { path: "reclamations/:id", element: <ComplaintDetail base="/operateur" /> },
      ...common,
      { path: "*", Component: NotFoundPage },
    ],
  },
  {
    path: "/publications-admin",
    element: (
      <RequireSpace spaces={["publications"]}>
        <AppLayout mode="publications" />
      </RequireSpace>
    ),
    children: [
      { index: true, Component: PublisherHome },
      { path: "contenus", Component: W.PublicationsAdmin },
      { path: "sondages", element: <SurveyManager base="/publications-admin" /> },
      { path: "sondages/nouveau", element: <SurveyBuilder base="/publications-admin" /> },
      { path: "sondages/:id", element: <SurveyResults base="/publications-admin" /> },
      { path: "commentaires", Component: W.CommentsAdmin },
      { path: "historique", Component: W.AuditPage },
      ...common,
      { path: "*", Component: NotFoundPage },
    ],
  },
])
