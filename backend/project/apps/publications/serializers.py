import os

from django.conf import settings
from django.utils import timezone
from django.utils.html import strip_tags
from rest_framework import serializers

from .models import ALLOWED_ATTACHMENT_EXTENSIONS, Comment, Publication, PublicationAttachment


class AttachmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = PublicationAttachment
        fields = ["id", "original_name", "size", "created_at"]
        read_only_fields = fields


class PublicationSerializer(serializers.ModelSerializer):
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    author_name = serializers.SerializerMethodField()
    attachments = AttachmentSerializer(many=True, read_only=True)

    class Meta:
        model = Publication
        fields = [
            "id", "title", "slug", "content", "category", "audience", "status", "published_at",
            "organization_code", "author_name", "attachments", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "slug", "status", "organization_code", "author_name", "attachments", "created_at", "updated_at"]

    def get_author_name(self, obj):
        return obj.organization.name

    def validate_published_at(self, value):
        return value

    def validate_content(self, value):
        return value.strip()


class PublicPublicationSerializer(serializers.ModelSerializer):
    organization_code = serializers.CharField(source="organization.code", read_only=True)
    excerpt = serializers.SerializerMethodField()

    class Meta:
        model = Publication
        fields = ["id", "title", "slug", "content", "excerpt", "category", "published_at", "organization_code"]
        read_only_fields = fields

    def get_excerpt(self, obj):
        text = strip_tags(obj.content)
        return text[:220] + ("…" if len(text) > 220 else "")


class SchedulePublicationSerializer(serializers.Serializer):
    published_at = serializers.DateTimeField()

    def validate_published_at(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("La date de planification doit être dans le futur.")
        return value


class AttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

    def validate_file(self, f):
        ext = os.path.splitext(f.name)[1].lower().lstrip(".")
        if ext not in ALLOWED_ATTACHMENT_EXTENSIONS:
            raise serializers.ValidationError(f"Extension non autorisée ({', '.join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))}).")
        if f.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise serializers.ValidationError("Fichier trop volumineux.")
        return f


class CommentPublicSerializer(serializers.ModelSerializer):
    website = serializers.CharField(write_only=True, required=False, allow_blank=True)  # honeypot anti-bot

    class Meta:
        model = Comment
        fields = ["id", "publication", "content", "author_name", "status", "created_at", "website"]
        read_only_fields = ["id", "status", "created_at"]

    def validate_publication(self, pub):
        if not pub.is_publicly_visible:
            raise serializers.ValidationError("Publication introuvable.")
        return pub

    def validate_content(self, value):
        value = strip_tags(value).strip()
        if len(value) < 3:
            raise serializers.ValidationError("Commentaire trop court.")
        if len(value) > 2000:
            raise serializers.ValidationError("Commentaire trop long (2000 caractères maximum).")
        if value.lower().count("http") > 2:
            raise serializers.ValidationError("Trop de liens dans le commentaire.")
        return value

    def validate_author_name(self, value):
        return strip_tags(value).strip()[:80]

    def validate(self, attrs):
        if attrs.pop("website", ""):
            raise serializers.ValidationError("Soumission refusée.")
        return attrs


class CommentModerationSerializer(serializers.ModelSerializer):
    publication_title = serializers.CharField(source="publication.title", read_only=True)

    class Meta:
        model = Comment
        fields = ["id", "publication", "publication_title", "content", "author_name", "status", "report_count", "created_at"]
        read_only_fields = fields


class CommentReportSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True)
