from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.audit.services import log as audit_log
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of

from .models import CaseEvent, CorrectiveAction, OperatorResponse, RegulatoryCase, RegulatoryDecision, RegulatoryEvidence

S = RegulatoryCase.Status


def add_event(case, kind, actor, message="", internal=False):
    return CaseEvent.objects.create(case=case, kind=kind, actor=actor, message=message, internal=internal)


def _operator_users(case):
    return users_of(case.operator, roles=("OPERATOR_USER",))


@transaction.atomic
def open_case(data, user, request=None):
    case = RegulatoryCase.objects.create(opened_by=user, **data)
    add_event(case, CaseEvent.Kind.OPENED, user, f"Dossier ouvert : {case.title}")
    audit_log(user, "case.opened", "RegulatoryCase", case.pk, {"operator": case.operator.code}, request=request)
    return case


def _ensure_not_closed(case):
    if case.status == S.CLOSED:
        raise ValidationError("Ce dossier est clos.")


@transaction.atomic
def request_explanation(case, user, message, deadline=None, request=None):
    _ensure_not_closed(case)
    if not message.strip():
        raise ValidationError({"message": "Le motif de la demande est obligatoire."})
    case.status = S.AWAITING_OPERATOR_RESPONSE
    if deadline:
        case.deadline = deadline
    case.save(update_fields=["status", "deadline"])
    add_event(case, CaseEvent.Kind.EXPLANATION_REQUESTED, user, message)
    notify(_operator_users(case), "Demande d'explication", f"L'ARTEC vous demande des explications (dossier {case.reference_number}).", Notification.Type.EXPLANATION_REQUESTED, case)
    audit_log(user, "case.explanation_requested", "RegulatoryCase", case.pk, request=request)
    return case


@transaction.atomic
def operator_respond(case, user, content, request=None):
    if case.status != S.AWAITING_OPERATOR_RESPONSE:
        raise ValidationError("Aucune réponse n'est attendue pour ce dossier.")
    if not content.strip():
        raise ValidationError({"content": "La réponse ne peut pas être vide."})
    resp = OperatorResponse.objects.create(case=case, responder=user, content=content.strip())
    case.status = S.UNDER_REVIEW
    case.save(update_fields=["status"])
    add_event(case, CaseEvent.Kind.OPERATOR_RESPONSE, user, "Réponse transmise par l'opérateur.")
    notify(([case.assigned_to] if case.assigned_to else users_of(roles=("ARTEC_REGULATOR",))), "Réponse reçue", f"{case.operator.code} a répondu (dossier {case.reference_number}).", Notification.Type.RESPONSE_RECEIVED, case)
    audit_log(user, "case.operator_responded", "RegulatoryCase", case.pk, request=request)
    return resp


@transaction.atomic
def add_evidence(case, user, data, request=None):
    _ensure_not_closed(case)
    ev = RegulatoryEvidence.objects.create(case=case, added_by=user, **data)
    add_event(case, CaseEvent.Kind.EVIDENCE_ADDED, user, f"Élément ajouté : {ev.get_kind_display()}", internal=not ev.visible_to_operator)
    audit_log(user, "case.evidence_added", "RegulatoryCase", case.pk, {"evidence": ev.pk}, request=request)
    return ev


@transaction.atomic
def decide(case, user, category, justification, evidence_ids, request=None):
    """Enregistre une décision motivée prise par une personne habilitée. Jamais déclenchée automatiquement."""
    _ensure_not_closed(case)
    justification = (justification or "").strip()
    if len(justification) < 20:
        raise ValidationError({"justification": "Une justification détaillée (20 caractères minimum) est obligatoire."})
    evidence = list(case.evidence.filter(pk__in=evidence_ids))
    if len(evidence) != len(set(evidence_ids)):
        raise ValidationError({"evidence": "Éléments de preuve inconnus pour ce dossier."})
    Cat = RegulatoryDecision.Category
    if category in (Cat.WARNING, Cat.CORRECTION_REQUEST) and not evidence:
        raise ValidationError({"evidence": "Au moins un élément de preuve est requis pour cette catégorie de décision."})
    if category == Cat.WARNING and not case.events.filter(kind=CaseEvent.Kind.EXPLANATION_REQUESTED).exists():
        raise ValidationError("Un avertissement exige qu'une demande d'explication ait été adressée à l'opérateur (respect du contradictoire).")
    if category == Cat.WARNING and case.status == S.AWAITING_OPERATOR_RESPONSE:
        raise ValidationError("La réponse de l'opérateur est encore attendue.")
    decision = RegulatoryDecision.objects.create(case=case, category=category, justification=justification, decided_by=user)
    decision.evidence.set(evidence)
    case.status = S.DECIDED
    case.save(update_fields=["status"])
    add_event(case, CaseEvent.Kind.DECISION, user, f"Décision : {decision.get_category_display()}")
    notify(_operator_users(case), "Décision rendue", f"Une décision a été rendue sur le dossier {case.reference_number}.", Notification.Type.DECISION, case)
    audit_log(user, "case.decision", "RegulatoryDecision", decision.pk, {"case": case.pk, "category": category}, request=request)
    return decision


@transaction.atomic
def amend_decision(decision, user, category, justification, reason, evidence_ids, request=None):
    if not decision.is_current:
        raise ValidationError("Seule la décision en vigueur peut être modifiée.")
    if len((reason or "").strip()) < 10:
        raise ValidationError({"reason": "Le motif de modification est obligatoire."})
    case = decision.case
    justification = (justification or "").strip()
    if len(justification) < 20:
        raise ValidationError({"justification": "Une justification détaillée est obligatoire."})
    evidence = list(case.evidence.filter(pk__in=evidence_ids))
    new = RegulatoryDecision.objects.create(case=case, category=category, justification=justification, decided_by=user, supersedes=decision, amendment_reason=reason.strip())
    new.evidence.set(evidence)
    add_event(case, CaseEvent.Kind.DECISION_AMENDED, user, f"Décision #{decision.pk} remplacée par #{new.pk} : {reason.strip()}")
    notify(_operator_users(case), "Décision modifiée", f"Une décision du dossier {case.reference_number} a été modifiée.", Notification.Type.DECISION, case)
    audit_log(user, "case.decision_amended", "RegulatoryDecision", new.pk, {"supersedes": decision.pk, "reason": reason}, request=request)
    return new


@transaction.atomic
def create_corrective_action(case, user, description, due_date, decision=None, request=None):
    _ensure_not_closed(case)
    if due_date < timezone.localdate():
        raise ValidationError({"due_date": "L'échéance doit être future."})
    action = CorrectiveAction.objects.create(case=case, decision=decision, description=description, due_date=due_date, created_by=user)
    case.status = S.UNDER_CORRECTION
    case.save(update_fields=["status"])
    add_event(case, CaseEvent.Kind.CORRECTIVE_ACTION, user, f"Action corrective demandée avant le {due_date}.")
    notify(_operator_users(case), "Correction demandée", f"Action corrective à réaliser (dossier {case.reference_number}).", Notification.Type.CORRECTION_REQUESTED, case)
    audit_log(user, "case.corrective_action", "CorrectiveAction", action.pk, {"case": case.pk}, request=request)
    return action


@transaction.atomic
def operator_update_action(action, user, new_status, report, request=None):
    if new_status not in (CorrectiveAction.Status.IN_PROGRESS, CorrectiveAction.Status.SUBMITTED):
        raise ValidationError({"status": "Statuts autorisés : IN_PROGRESS, SUBMITTED."})
    if action.status in (CorrectiveAction.Status.VERIFIED,):
        raise ValidationError("Action déjà vérifiée.")
    action.status = new_status
    action.operator_report = report or action.operator_report
    action.save()
    add_event(action.case, CaseEvent.Kind.CORRECTIVE_ACTION, user, f"Action corrective : {action.get_status_display()}.")
    audit_log(user, "corrective_action.updated", "CorrectiveAction", action.pk, {"status": new_status}, request=request)
    return action


@transaction.atomic
def verify_action(action, user, ok, comment, request=None):
    if action.status != CorrectiveAction.Status.SUBMITTED:
        raise ValidationError("L'opérateur n'a pas encore transmis cette action pour vérification.")
    action.status = CorrectiveAction.Status.VERIFIED if ok else CorrectiveAction.Status.NOT_COMPLIED
    action.verification_comment = comment
    action.save()
    add_event(action.case, CaseEvent.Kind.CORRECTIVE_ACTION, user, f"Vérification : {action.get_status_display()}.")
    audit_log(user, "corrective_action.verified", "CorrectiveAction", action.pk, {"ok": ok}, request=request)
    return action


@transaction.atomic
def close_case(case, user, comment, request=None):
    if case.status not in (S.DECIDED, S.UNDER_CORRECTION) or not case.decisions.exists():
        raise ValidationError("Un dossier ne peut être clos qu'après décision.")
    if case.corrective_actions.exclude(status__in=[CorrectiveAction.Status.VERIFIED, CorrectiveAction.Status.NOT_COMPLIED]).exists():
        raise ValidationError("Des actions correctives sont encore en cours.")
    case.status = S.CLOSED
    case.closed_at = timezone.now()
    case.save(update_fields=["status", "closed_at"])
    add_event(case, CaseEvent.Kind.CLOSED, user, comment or "Dossier clôturé.")
    audit_log(user, "case.closed", "RegulatoryCase", case.pk, request=request)
    return case


def notify_deadlines(days=2):
    """Notifie les échéances proches (une seule notification par dossier et par jour)."""
    from apps.notifications.models import Notification as N

    today = timezone.localdate()
    cases = RegulatoryCase.objects.exclude(status=S.CLOSED).filter(deadline__isnull=False, deadline__lte=today + timedelta(days=days))
    sent = 0
    for case in cases:
        if N.objects.filter(notification_type=N.Type.DEADLINE, related_resource_type="RegulatoryCase", related_resource_id=str(case.pk), created_at__date=today).exists():
            continue
        recipients = ([case.assigned_to] if case.assigned_to else users_of(roles=("ARTEC_REGULATOR",))) + (_operator_users(case) if case.status == S.AWAITING_OPERATOR_RESPONSE else [])
        notify(recipients, "Échéance proche", f"Dossier {case.reference_number} : échéance le {case.deadline}.", N.Type.DEADLINE, case)
        sent += 1
    return sent
