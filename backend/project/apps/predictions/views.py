import csv

from django.http import HttpResponse
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import ARTEC_REGULATOR, roles_required
from apps.datasets.views import visible_datasets

from . import frames, services, tasks
from .models import PredictionModel, PredictionResult, PredictionRun
from .serializers import (
    BuildTrainingSetSerializer,
    ForecastSerializer,
    PredictionModelSerializer,
    PredictionRunSerializer,
    ResultSerializer,
    RunRequestSerializer,
    TrainRequestSerializer,
)

Regulator = roles_required(ARTEC_REGULATOR)


def _check_version_access(user, version):
    if not visible_datasets(user).filter(pk=version.dataset_id).exists():
        raise ValidationError({"dataset_version": "Version introuvable."})


class PredictionModelViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PredictionModel.objects.all()
    serializer_class = PredictionModelSerializer
    permission_classes = [Regulator]
    filterset_fields = ["status", "name"]

    @extend_schema(request=TrainRequestSerializer, responses={201: PredictionModelSerializer})
    @action(detail=False, methods=["post"])
    def train(self, request):
        s = TrainRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data["training_dataset_version"]
        _check_version_access(request.user, v)
        model = services.request_training(request.user, s.validated_data["name"], v, s.validated_data.get("features"), request, s.validated_data.get("risk_type"))
        tasks.train_model_task.delay(model.pk)
        model.refresh_from_db()
        return Response(PredictionModelSerializer(model).data, status=status.HTTP_201_CREATED)

    @extend_schema(responses={200: dict})
    @action(detail=False, methods=["get"])
    def compare(self, request):
        try:
            a, b = (PredictionModel.objects.get(pk=request.query_params[k]) for k in ("a", "b"))
        except (KeyError, ValueError, PredictionModel.DoesNotExist):
            raise ValidationError("Paramètres `a` et `b` (identifiants de modèles existants) requis.")
        keys = ["accuracy", "macro_f1"]
        delta = {k: round(b.metrics.get(k, 0) - a.metrics.get(k, 0), 4) for k in keys if k in a.metrics and k in b.metrics}
        return Response({"a": PredictionModelSerializer(a).data, "b": PredictionModelSerializer(b).data, "delta_b_minus_a": delta})


class TrainingSetView(APIView):
    """Construit un jeu étiqueté « période t -> classe de t+1 » à partir des mesures validées et des seuils configurés."""

    permission_classes = [Regulator]

    @extend_schema(request=BuildTrainingSetSerializer, responses={201: dict})
    def post(self, request):
        s = BuildTrainingSetSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        df, meta = frames.build_training_frame(d["risk_type"], d["granularity"], d["sources"])
        name = d.get("name") or f"Entraînement {frames.RISK_TYPES[d['risk_type']]['label']} ({d['granularity']})"
        version = services.store_frame_as_dataset(request.user, name, df, "LABELED_TRAINING", meta)
        counts = df["quality_class"].value_counts().to_dict()
        return Response({"dataset_version": version.pk, "dataset_name": name, "rows": len(df), "class_counts": counts, "periods": int(df["campaign_id"].nunique()),
                         "report_status": version.report.status, "note": frames.RISK_TYPES[d["risk_type"]]["note"], "meta": meta}, status=status.HTTP_201_CREATED)


class RiskTypesView(APIView):
    permission_classes = [Regulator]

    @extend_schema(responses={200: dict})
    def get(self, request):
        return Response([{"risk_type": k, "label": v["label"], "note": v["note"]} for k, v in frames.RISK_TYPES.items()])


class ForecastView(APIView):
    """Applique un modèle prêt aux dernières périodes de chaque (opérateur, région, technologie)."""

    permission_classes = [Regulator]

    @extend_schema(request=ForecastSerializer, responses={201: PredictionRunSerializer})
    def post(self, request):
        s = ForecastSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        model = s.validated_data["model_version"]
        meta = (model.training_dataset_version.schema_definition or {}).get("_meta") or {}
        granularity = s.validated_data.get("granularity") or meta.get("granularity", "month")
        sources = s.validated_data.get("sources") or meta.get("sources", ["TECHNICAL"])
        if model.status != "READY":
            raise ValidationError({"model_version": f"Modèle non prêt (statut : {model.status}). {model.status_reason}".strip()})
        df, _ = frames.build_inference_frame(granularity, sources)
        version = services.store_frame_as_dataset(request.user, f"Prévision {model.name} v{model.version}", df, "OTHER", {"granularity": granularity, "sources": sources})
        run = services.request_run(request.user, model, version, request)
        tasks.execute_run_task.delay(run.pk)
        run.refresh_from_db()
        return Response(PredictionRunSerializer(run).data, status=status.HTTP_201_CREATED)


class PredictionRunViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = PredictionRun.objects.select_related("model_version")
    serializer_class = PredictionRunSerializer
    permission_classes = [Regulator]
    filterset_fields = ["status", "model_version"]

    @extend_schema(request=RunRequestSerializer, responses={201: PredictionRunSerializer})
    def create(self, request):
        s = RunRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data["input_dataset_version"]
        _check_version_access(request.user, v)
        run = services.request_run(request.user, s.validated_data["model_version"], v, request)
        tasks.execute_run_task.delay(run.pk)
        run.refresh_from_db()
        return Response(PredictionRunSerializer(run).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["get"])
    def results(self, request, pk=None):
        run = self.get_object()
        qs = run.results.all()
        if cls := request.query_params.get("predicted_class"):
            qs = qs.filter(predicted_class=cls)
        page = self.paginate_queryset(qs)
        return self.get_paginated_response(ResultSerializer(page, many=True).data)

    @action(detail=True, methods=["get"])
    def export(self, request, pk=None):
        run = self.get_object()
        resp = HttpResponse(content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="prediction_run_{run.pk}.csv"'
        w = csv.writer(resp)
        w.writerow([f"# {services.DISCLAIMER}"])
        w.writerow([f"# modèle={run.model_version.name} v{run.model_version.version} ; dataset_version={run.input_dataset_version_id}"])
        w.writerow(["observation_reference", "predicted_class", "probability_good", "probability_medium", "probability_poor", "confidence", "top_factors"])
        for r in run.results.all().iterator():
            w.writerow([r.observation_reference, r.predicted_class, r.probability_good, r.probability_medium, r.probability_poor, r.confidence, "; ".join(f"{f['label']} ({f['effect']})" for f in r.top_factors)])
        return resp
