"""Réponses d'erreur uniformes : {"error": {"code", "message", "details"}}."""
from django.core.exceptions import PermissionDenied, ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import exceptions, status
from rest_framework.response import Response
from rest_framework.views import exception_handler


def _message(detail):
    if isinstance(detail, dict):
        return "Les données transmises sont invalides."
    if isinstance(detail, list):
        return "Les données transmises sont invalides."
    return str(detail)


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc = exceptions.ValidationError(detail=exc.message_dict if hasattr(exc, "error_dict") else exc.messages)
    elif isinstance(exc, Http404):
        exc = exceptions.NotFound()
    elif isinstance(exc, PermissionDenied):
        exc = exceptions.PermissionDenied()
    response = exception_handler(exc, context)
    if response is None:
        return None
    code = getattr(exc, "default_code", "error")
    details = response.data
    if isinstance(exc, exceptions.APIException) and not isinstance(details, (dict, list)):
        details = None
    response.data = {"error": {"code": code, "message": _message(getattr(exc, "detail", "")), "details": details}}
    if isinstance(exc, (exceptions.NotAuthenticated, exceptions.AuthenticationFailed)) and response.status_code == status.HTTP_403_FORBIDDEN:
        response.status_code = status.HTTP_401_UNAUTHORIZED
    return response
