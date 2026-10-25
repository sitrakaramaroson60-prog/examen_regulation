export type Tone = "blue" | "green" | "orange" | "red" | "gray"

export const STATUS: Record<string, [string, Tone]> = {
  // qualité (seuils)
  GOOD: ["Bon", "green"], MEDIUM: ["Moyen", "orange"], POOR: ["Mauvais", "red"],
  // conformité
  COMPLIANT: ["Conforme", "green"], NON_COMPLIANT: ["Écart détecté", "red"], INSUFFICIENT_DATA: ["Données insuffisantes", "gray"], PARTIAL: ["Partiel", "orange"],
  // alertes
  INFO: ["Information", "blue"], WARNING: ["Vigilance", "orange"], CRITICAL: ["Écart important", "red"],
  NEW: ["Nouvelle", "blue"], ACKNOWLEDGED: ["Prise en compte", "orange"], DISMISSED: ["Sans suite", "gray"], ESCALATED: ["Dossier ouvert", "green"],
  // soumissions
  SUBMITTED: ["Soumis", "blue"], UNDER_REVIEW: ["En examen", "orange"], CORRECTION_REQUIRED: ["Correction demandée", "orange"], ACCEPTED: ["Accepté", "green"], REJECTED: ["Rejeté", "red"],
  // rapports de validation
  VALID: ["Valide", "green"], VALID_WITH_WARNINGS: ["Avertissements", "orange"], INVALID: ["Invalide", "red"],
  // dossiers
  OPEN: ["Ouvert", "blue"], AWAITING_OPERATOR_RESPONSE: ["Réponse attendue", "orange"], UNDER_CORRECTION: ["Correction en cours", "orange"], DECIDED: ["Décision rendue", "green"], CLOSED: ["Clos", "gray"],
  // modèles / exécutions
  READY: ["Prêt", "green"], NOT_READY: ["Non prêt", "orange"], LOW_QUALITY: ["Performances insuffisantes", "red"], TRAINING: ["Entraînement", "blue"], FAILED: ["Échec", "red"],
  COMPLETED: ["Terminée", "green"], RUNNING: ["En cours", "blue"], PENDING: ["En attente", "orange"],
  // contenus
  DRAFT: ["Brouillon", "gray"], PUBLISHED: ["Publié", "green"], SCHEDULED: ["Planifié", "blue"], ARCHIVED: ["Archivé", "gray"], PENDING_APPROVAL: ["À valider", "orange"],
  APPROVED: ["Approuvé", "green"], HIDDEN: ["Masqué", "gray"],
  // actions correctives, contrôles
  REQUESTED: ["Demandée", "blue"], IN_PROGRESS: ["En cours", "orange"], VERIFIED: ["Vérifiée", "green"], NOT_COMPLIED: ["Non réalisée", "red"], PLANNED: ["Planifié", "blue"], DONE: ["Réalisé", "green"],
  // décisions
  WARNING_DECISION: ["Avertissement", "red"], CONGRATULATIONS: ["Félicitations", "green"], EXPLANATION_REQUEST: ["Demande d'explication", "orange"], RECOMMENDATION: ["Recommandation", "blue"],
  CORRECTION_REQUEST: ["Demande de correction", "orange"], NO_BREACH: ["Aucun manquement établi", "green"], CLOSURE: ["Clôture", "gray"],
}


export const fmtDate = (iso?: string | null) => (iso ? new Date(iso).toLocaleDateString("fr-FR") : "—")
export const fmtDateTime = (iso?: string | null) => (iso ? new Date(iso).toLocaleString("fr-FR") : "—")
export const fmtNum = (v?: number | null, digits = 2) => (v === null || v === undefined ? "—" : Number(v.toLocaleString("en-US", { maximumFractionDigits: digits }).replace(/,/g, "")).toLocaleString("fr-FR"))

