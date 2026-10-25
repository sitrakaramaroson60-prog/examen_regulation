import os

from django.conf import settings
from django.utils.html import strip_tags
from rest_framework import serializers

from apps.accounts.models import User
from apps.organizations.models import City, Organization, Region
from apps.regulation.models import RegulatoryCase, RegulatoryDecision

from .models import Complaint, ComplaintAttachment, ComplaintMessage

ALLOWED_EXT = {"pdf", "png", "jpg", "jpeg", "csv", "xlsx", "docx", "txt"}


class PublicComplaintSerializer(serializers.Serializer):
    complaint_type = serializers.ChoiceField(choices=["PUBLIC_COMPLAINT", "REPORT"], default="PUBLIC_COMPLAINT")
    category = serializers.CharField(max_length=60)
    description = serializers.CharField(min_length=10, max_length=4000)
    target_operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"), required=False, allow_null=True)
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all(), required=False, allow_null=True)
    city = serializers.PrimaryKeyRelatedField(queryset=City.objects.all(), required=False, allow_null=True)
    contact_email = serializers.EmailField(required=False, allow_blank=True)
    website = serializers.CharField(required=False, allow_blank=True)  # honeypot

    def validate(self, attrs):
        if attrs.pop("website", ""):
            raise serializers.ValidationError("Soumission refusée.")
        if attrs.get("city") and attrs.get("region") and attrs["city"].region_id != attrs["region"].pk:
            raise serializers.ValidationError({"city": "Cette ville n'appartient pas à la région indiquée."})
        attrs["description"] = strip_tags(attrs["description"]).strip()
        attrs["category"] = strip_tags(attrs["category"]).strip()
        return attrs


class TrackSerializer(serializers.Serializer):
    reference = serializers.CharField()
    token = serializers.CharField()


class MessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintMessage
        fields = ["id", "author_kind", "content", "is_internal", "created_at"]
        read_only_fields = ["id", "author_kind", "created_at"]


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ComplaintAttachment
        fields = ["id", "original_name", "size", "created_at"]
        read_only_fields = fields


class ComplaintSerializer(serializers.ModelSerializer):
    organization = serializers.CharField(source="organization.code", default=None, read_only=True)
    target_operator = serializers.SlugRelatedField(slug_field="code", queryset=Organization.objects.filter(organization_type="OPERATOR"), required=False, allow_null=True)
    related_case = serializers.PrimaryKeyRelatedField(queryset=RegulatoryCase.objects.all(), required=False, allow_null=True)
    related_decision = serializers.PrimaryKeyRelatedField(queryset=RegulatoryDecision.objects.all(), required=False, allow_null=True)
    assigned_to = serializers.PrimaryKeyRelatedField(read_only=True)
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Complaint
        fields = [
            "id", "reference", "complaint_type", "category", "description", "status", "organization", "target_operator",
            "related_case", "related_decision", "assigned_to", "deadline", "conclusion", "attachments", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "reference", "status", "organization", "assigned_to", "deadline", "conclusion", "attachments", "created_at", "updated_at"]

    def validate_complaint_type(self, value):
        user = self.context["request"].user
        if user.role == "OPERATOR_USER" and value not in ("OPERATOR_CONTESTATION", "REVIEW_REQUEST"):
            raise serializers.ValidationError("Un opérateur dépose une contestation ou une demande de réexamen.")
        return value

    def validate(self, attrs):
        user = self.context["request"].user
        decision, case = attrs.get("related_decision"), attrs.get("related_case")
        if user.role == "OPERATOR_USER":
            if decision is not None and decision.case.operator_id != user.organization_id:
                raise serializers.ValidationError({"related_decision": "Décision introuvable."})
            if case is not None and case.operator_id != user.organization_id:
                raise serializers.ValidationError({"related_case": "Dossier introuvable."})
        if attrs.get("complaint_type") in ("OPERATOR_CONTESTATION", "REVIEW_REQUEST") and decision is None and case is None:
            raise serializers.ValidationError("Une contestation doit viser un dossier ou une décision.")
        return attrs


class StaffUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=Complaint.Status.choices, required=False)
    assigned_to = serializers.PrimaryKeyRelatedField(queryset=User.objects.filter(role="ARTEC_REGULATOR", is_active=True), required=False, allow_null=True)
    deadline = serializers.DateField(required=False, allow_null=True)
    conclusion = serializers.CharField(required=False, allow_blank=True)


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, f):
        ext = os.path.splitext(f.name)[1].lower().lstrip(".")
        if ext not in ALLOWED_EXT:
            raise serializers.ValidationError(f"Extension non autorisée ({', '.join(sorted(ALLOWED_EXT))}).")
        if f.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError("Fichier trop volumineux.")
        return f
