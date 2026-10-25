import hashlib

from django.conf import settings
from django.core.files.storage import FileSystemStorage


def private_storage():
    """Stockage hors de toute URL publique (pas de base_url)."""
    return FileSystemStorage(location=str(settings.PRIVATE_MEDIA_ROOT), base_url=None)


def sha256_of(uploaded_file):
    digest = hashlib.sha256()
    uploaded_file.seek(0)
    for chunk in iter(lambda: uploaded_file.read(1024 * 1024), b""):
        digest.update(chunk)
    uploaded_file.seek(0)
    return digest.hexdigest()
