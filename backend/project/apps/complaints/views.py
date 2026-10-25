import hashlib
import hmac
import secrets

from django.conf import settings
from django.db import transaction
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.audit.services import log as audit_log
from apps.common.permissions import ARTEC_REGULATOR, OPERATOR_USER, roles_required
from apps.notifications.models import Notification
from apps.notifications.services import notify, users_of

from .models import Complaint, ComplaintAttachment, ComplaintMessage
from .serializers import (
    AttachmentSerializer,
    AttachmentUploadSerializer,
    ComplaintSerializer,
    MessageSerializer,
    PublicComplaintSerializer,
    StaffUpdateSerializer,
    TrackSerializer,
)

Participants = roles_required(OPERATOR_USER, ARTEC_REGULATOR)


def _hash(token):
    return hmac.new(settings.SECRET_KEY.encode(), token.encode(), hashlib.sha256).hexdigest()


class PublicComplaintView(APIView):
    """Dépôt anonyme d'une réclamation. Retourne une référence et un jeton de suivi (affiché une seule fois)."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_complaint"

    @extend_schema(request=PublicComplaintSerializer, responses={201: dict})
    def post(self, request):
        s = PublicComplaintSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        token = secrets.token_urlsafe(24)
        c = Complaint.objects.create(tracking_token_hash=_hash(token), **s.validated_data)
        notify(users_of(roles=(ARTEC_REGULATOR,)), "Nouvelle réclamation", f"Réclamation {c.reference} reçue.", Notification.Type.CONTESTATION, c)
        return Response({"reference": c.reference, "tracking_token": token, "message": "Conservez ce jeton : il est nécessaire pour suivre votre réclamation."}, status=status.HTTP_201_CREATED)


class PublicTrackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_complaint"

    @extend_schema(request=TrackSerializer, responses={200: dict})
    def post(self, request):
        s = TrackSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        c = Complaint.objects.filter(reference=s.validated_data["reference"]).first()
        if c is None or not c.tracking_token_hash or not hmac.compare_digest(c.tracking_token_hash, _hash(s.validated_data["token"])):
            return Response({"error": {"code": "not_found", "message": "Référence ou jeton invalide.", "details": None}}, status=status.HTTP_404_NOT_FOUND)
        messages = c.messages.filter(is_internal=False)
        return Response({"reference": c.reference, "status": c.status, "category": c.category, "conclusion": c.conclusion if c.status in ("RESOLVED", "REJECTED", "CLOSED") else "",
                         "messages": [{"author_kind": m.author_kind, "content": m.content, "created_at": m.created_at} for m in messages]})


class ComplaintViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Opérateur : ses contestations. ARTEC Régulation : toutes. ARTEC Publications : aucun accès."""

    serializer_class = ComplaintSerializer
    permission_classes = [Participants]
    filterset_fields = ["status", "complaint_type", "target_operator__code"]
    search_fields = ["reference", "category", "description"]
    ordering_fields = ["created_at", "deadline"]

    def get_queryset(self):
        qs = Complaint.objects.select_related("organization", "target_operator").prefetch_related("attachments")
        user = self.request.user
        if user.role == ARTEC_REGULATOR:
            return qs
        return qs.filter(organization=user.organization)

    def perform_create(self, serializer):
        user = self.request.user
        if user.role != OPERATOR_USER:
            raise PermissionDenied("Seuls les opérateurs déposent une contestation via cet endpoint.")
        c = serializer.save(submitter=user, organization=user.organization)
        notify(users_of(roles=(ARTEC_REGULATOR,)), "Nouvelle contestation", f"Contestation {c.reference} déposée.", Notification.Type.CONTESTATION, c)
        audit_log(user, "complaint.created", "Complaint", c.pk, {"type": c.complaint_type}, request=self.request)

    @extend_schema(request=MessageSerializer, responses=MessageSerializer(many=True))
    @action(detail=True, methods=["get", "post"])
    def messages(self, request, pk=None):
        c = self.get_object()
        if request.method == "GET":
            qs = c.messages.all() if request.user.role == ARTEC_REGULATOR else c.messages.filter(is_internal=False)
            return Response(MessageSerializer(qs, many=True).data)
        if c.status in ("CLOSED",):
            raise ValidationError("Dossier clôturé.")
        s = MessageSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        staff = request.user.role == ARTEC_REGULATOR
        internal = bool(s.validated_data.get("is_internal")) and staff
        m = ComplaintMessage.objects.create(complaint=c, author_user=request.user, author_kind="ARTEC" if staff else "SUBMITTER", content=s.validated_data["content"], is_internal=internal)
        if staff and not internal and c.organization_id:
            notify(users_of(c.organization, roles=(OPERATOR_USER,)), "Nouveau message", f"Réponse de l'ARTEC sur {c.reference}.", Notification.Type.RESPONSE_RECEIVED, c)
        if not staff:
            notify(([c.assigned_to] if c.assigned_to else users_of(roles=(ARTEC_REGULATOR,))), "Nouveau message", f"Message du déposant sur {c.reference}.", Notification.Type.RESPONSE_RECEIVED, c)
        return Response(MessageSerializer(m).data, status=status.HTTP_201_CREATED)

    @extend_schema(request=StaffUpdateSerializer, responses=ComplaintSerializer)
    @action(detail=True, methods=["post"])
    @transaction.atomic
    def process(self, request, pk=None):
        if request.user.role != ARTEC_REGULATOR:
            raise PermissionDenied("Traitement réservé à ARTEC Régulation et Prédiction.")
        c = self.get_object()
        s = StaffUpdateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        new_status = data.get("status")
        if new_status in ("RESOLVED", "REJECTED") and not (data.get("conclusion") or c.conclusion).strip():
            raise ValidationError({"conclusion": "Une conclusion motivée est obligatoire."})
        for k, v in data.items():
            setattr(c, k, v)
        c.save()
        audit_log(request.user, "complaint.processed", "Complaint", c.pk, {"status": c.status}, request=request)
        return Response(ComplaintSerializer(c, context={"request": request}).data)

    @extend_schema(request=AttachmentUploadSerializer, responses=AttachmentSerializer)
    @action(detail=True, methods=["post"])
    def attachments(self, request, pk=None):
        c = self.get_object()
        s = AttachmentUploadSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        f = s.validated_data["file"]
        att = ComplaintAttachment.objects.create(complaint=c, file=f, original_name=f.name[:255], size=f.size, uploaded_by=request.user)
        return Response(AttachmentSerializer(att).data, status=status.HTTP_201_CREATED)
