"""Entraînement et exécution d'un classifieur Softmax (régression logistique multinomiale).

Garde-fous : jamais de probabilités simulées ; modèle « non prêt » si les données sont insuffisantes ;
séparation train/test par groupe (campagne) pour éviter les fuites ; intégrité de l'artefact vérifiée au chargement.
"""
import hashlib
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from django.conf import settings
from django.db import transaction
from django.db.models import Max
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, brier_score_loss, confusion_matrix, precision_recall_fscore_support
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from apps.audit.services import log as audit_log
from apps.datasets.services import is_usable_for_analysis, load_dataframe
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .frames import RISK_TYPES, feature_label
from .models import PredictionModel, PredictionResult, PredictionRun

CLASSES = ["GOOD", "MEDIUM", "POOR"]
RESERVED = {"quality_class", "campaign_id", "observation_id", "period_index"}
DISCLAIMER = "Les prédictions sont des estimations probabilistes et non des certitudes. Elles ne constituent jamais, à elles seules, une preuve de manquement."


# ---------- préparation ----------
def candidate_features(df):
    out = []
    for c in df.columns:
        if c in RESERVED:
            continue
        if pd.to_numeric(df[c].dropna(), errors="coerce").notna().all() and df[c].notna().any():
            out.append(c)
    return out


def prepare_training_frame(df, features):
    missing = [f for f in features if f not in df.columns]
    if missing:
        raise ValidationError({"features": f"Colonnes absentes : {', '.join(missing)}."})
    X = df[features].apply(pd.to_numeric, errors="coerce")
    y = df["quality_class"].astype(str).str.strip().str.upper()
    groups = df["campaign_id"].astype(str)
    mask = X.notna().all(axis=1) & y.isin(CLASSES) & df["campaign_id"].notna()
    return X[mask], y[mask], groups[mask], int((~mask).sum())


def readiness(y, groups):
    """Retourne une raison d'indisponibilité, ou None si les données suffisent."""
    if len(y) < settings.ML_MIN_TRAINING_ROWS:
        return f"Données insuffisantes : {len(y)} observation(s) exploitable(s), minimum {settings.ML_MIN_TRAINING_ROWS}."
    counts = y.value_counts()
    for c in CLASSES:
        if counts.get(c, 0) < settings.ML_MIN_ROWS_PER_CLASS:
            return f"Classe {c} insuffisamment représentée ({counts.get(c, 0)} < {settings.ML_MIN_ROWS_PER_CLASS})."
    if groups.nunique() < settings.ML_MIN_GROUPS:
        return f"Pas assez de campagnes distinctes ({groups.nunique()} < {settings.ML_MIN_GROUPS}) pour une évaluation sans fuite."
    return None


def temporal_split(y, df_index, period_index):
    """Entraînement sur les périodes anciennes, test sur les périodes récentes, avec une période d'écart
    (l'étiquette d'une ligne vient de la période suivante : évite toute fuite temporelle)."""
    periods = sorted(period_index.unique())
    if len(periods) < 4:
        return None, None
    cut = max(1, int(len(periods) * 0.7))
    train_p, test_p = set(periods[:cut]), set(periods[cut + 1:])
    if not test_p:
        return None, None
    tr = [i for i, p in enumerate(period_index) if p in train_p]
    te = [i for i, p in enumerate(period_index) if p in test_p]
    if set(y.iloc[tr]) != set(CLASSES) or set(y.iloc[te]) != set(CLASSES):
        return None, None
    return tr, te


def group_split(X, y, groups):
    for seed in range(42, 62):
        splitter = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=seed)
        tr, te = next(splitter.split(X, y, groups))
        if set(y.iloc[tr]) == set(CLASSES) and set(y.iloc[te]) == set(CLASSES):
            assert set(groups.iloc[tr]).isdisjoint(set(groups.iloc[te]))
            return tr, te
    return None, None


def calibration_summary(proba, y_true, bins=5):
    conf = proba.max(axis=1)
    pred = np.array(CLASSES)[proba.argmax(axis=1)]
    correct = (pred == y_true).astype(float)
    edges = np.linspace(0, 1, bins + 1)
    table, ece = [], 0.0
    for lo, hi in zip(edges[:-1], edges[1:]):
        m = (conf > lo) & (conf <= hi) if lo > 0 else (conf >= lo) & (conf <= hi)
        if m.sum() == 0:
            continue
        gap = abs(conf[m].mean() - correct[m].mean())
        ece += gap * m.sum() / len(conf)
        table.append({"bin": f"{lo:.1f}-{hi:.1f}", "n": int(m.sum()), "mean_confidence": round(float(conf[m].mean()), 4), "accuracy": round(float(correct[m].mean()), 4)})
    onehot = np.array([[1.0 if y == c else 0.0 for c in CLASSES] for y in y_true])
    brier = float(np.mean(np.sum((proba - onehot) ** 2, axis=1)))
    return {"expected_calibration_error": round(float(ece), 4), "multiclass_brier_score": round(brier, 4), "reliability_bins": table}


def feature_importance(pipe, features):
    """Importance globale : écart moyen absolu des coefficients Softmax (variables standardisées)."""
    coef = pipe.named_steps["clf"].coef_
    rel = np.abs(coef - coef.mean(axis=0, keepdims=True)).mean(axis=0)
    total = rel.sum() or 1.0
    ranked = sorted(zip(features, rel / total), key=lambda t: -t[1])
    return [{"feature": f, "label": feature_label(f), "weight": round(float(w), 4)} for f, w in ranked]


def explain(pipe, features, X_rows, predicted, top=3):
    """Facteurs principaux pour chaque observation : contribution de chaque variable (standardisée) au logit Softmax
    de la classe prédite, relativement aux autres classes. Valeur positive = la variable soutient la classe prédite."""
    scaler, clf = pipe.named_steps["scaler"], pipe.named_steps["clf"]
    Z = scaler.transform(X_rows)
    coef = clf.coef_ - clf.coef_.mean(axis=0, keepdims=True)
    index = {c: i for i, c in enumerate(clf.classes_)}
    out = []
    for z, raw, cls in zip(Z, X_rows.to_numpy(), predicted):
        contrib = z * coef[index[cls]]
        order = np.argsort(-np.abs(contrib))[:top]
        out.append([
            {"feature": features[j], "label": feature_label(features[j]), "value": round(float(raw[j]), 4), "contribution": round(float(contrib[j]), 4),
             "effect": "soutient" if contrib[j] > 0 else "s'oppose à"}
            for j in order
        ])
    return out


def model_path(model):
    return Path(settings.ML_MODELS_DIR) / f"{model.name.replace(' ', '_')}_v{model.version}.joblib"


# ---------- cycle de vie ----------
def request_training(user, name, training_version, features=None, request=None, risk_type=None):
    if training_version.dataset.data_type != "LABELED_TRAINING":
        raise ValidationError({"training_dataset_version": "Le dataset doit être de type LABELED_TRAINING."})
    if not is_usable_for_analysis(training_version):
        raise ValidationError({"training_dataset_version": "Dataset non validé / non accepté."})
    with transaction.atomic():
        last = PredictionModel.objects.filter(name=name).aggregate(m=Max("version"))["m"] or 0
        model = PredictionModel.objects.create(
            name=name, version=last + 1, training_dataset_version=training_version, created_by=user,
            feature_schema=features or [], status=PredictionModel.Status.TRAINING,
            risk_type=risk_type or (training_version.schema_definition.get("_meta") or {}).get("risk_type", "GENERAL_QUALITY"),
        )
    audit_log(user, "model.training_requested", "PredictionModel", model.pk, {"dataset_version": training_version.pk}, request=request)
    return model


def train_model(model_id):
    model = PredictionModel.objects.select_related("training_dataset_version").get(pk=model_id)
    try:
        df = load_dataframe(model.training_dataset_version)
        features = model.feature_schema or candidate_features(df)
        if not features:
            return _finish(model, PredictionModel.Status.NOT_READY, "Aucune variable explicative numérique trouvée.", features=[])
        X, y, groups, dropped = prepare_training_frame(df, features)
        reason = readiness(y, groups)
        if reason:
            return _finish(model, PredictionModel.Status.NOT_READY, reason, features=features, metrics={"dropped_rows": dropped})
        temporal = "period_index" in df.columns
        if temporal:
            pidx = pd.to_numeric(df.loc[X.index, "period_index"], errors="coerce").fillna(-1)
            tr, te = temporal_split(y, X.index, pidx)
            split_desc = "Découpage temporel : périodes anciennes pour l'entraînement, périodes récentes pour le test, une période d'écart"
        else:
            tr, te = group_split(X, y, groups)
            split_desc = "GroupShuffleSplit par campaign_id (aucune campagne partagée entre train et test)"
        if tr is None:
            return _finish(model, PredictionModel.Status.NOT_READY, "Impossible de former des jeux d'entraînement et de test contenant les trois classes (historique trop court ou classes déséquilibrées).", features=features)
        # solver lbfgs = régression logistique multinomiale : les probabilités sont obtenues par Softmax
        pipe = Pipeline([("scaler", StandardScaler()), ("clf", LogisticRegression(solver="lbfgs", max_iter=2000, random_state=0))])
        pipe.fit(X.iloc[tr], y.iloc[tr])
        proba = pipe.predict_proba(X.iloc[te])
        order = [list(pipe.classes_).index(c) for c in CLASSES]
        proba = proba[:, order]
        pred = np.array(CLASSES)[proba.argmax(axis=1)]
        y_te = y.iloc[te].to_numpy()
        p, r, f1, _ = precision_recall_fscore_support(y_te, pred, labels=CLASSES, zero_division=0)
        macro_f1 = float(np.mean(f1))
        metrics = {
            "accuracy": round(float(accuracy_score(y_te, pred)), 4),
            "precision": dict(zip(CLASSES, np.round(p, 4).tolist())), "recall": dict(zip(CLASSES, np.round(r, 4).tolist())),
            "f1": dict(zip(CLASSES, np.round(f1, 4).tolist())), "macro_f1": round(macro_f1, 4),
            "confusion_matrix": {"labels": CLASSES, "matrix": confusion_matrix(y_te, pred, labels=CLASSES).tolist()},
            "calibration": calibration_summary(proba, y_te),
            "n_train": int(len(tr)), "n_test": int(len(te)),
            "n_groups_train": int(groups.iloc[tr].nunique()), "n_groups_test": int(groups.iloc[te].nunique()),
            "dropped_rows": dropped, "split": split_desc,
            "feature_importance": feature_importance(pipe, features),
        }
        path = model_path(model)
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({"pipeline": pipe, "features": features, "classes": CLASSES}, path)
        model.artifact = str(path.name)
        model.artifact_checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        if macro_f1 < settings.ML_MIN_MACRO_F1:
            return _finish(model, PredictionModel.Status.LOW_QUALITY, f"F1 macro {macro_f1:.2f} inférieur au minimum requis ({settings.ML_MIN_MACRO_F1}).", features=features, metrics=metrics)
        return _finish(model, PredictionModel.Status.READY, "", features=features, metrics=metrics)
    except Exception as exc:  # noqa: BLE001
        return _finish(model, PredictionModel.Status.FAILED, f"{type(exc).__name__}: {str(exc)[:300]}")


def _finish(model, status, reason, features=None, metrics=None):
    model.status = status
    model.status_reason = reason
    if features is not None:
        model.feature_schema = features
    if metrics is not None:
        model.metrics = metrics
    model.save()
    audit_log(model.created_by, "model.trained", "PredictionModel", model.pk, {"status": status, "macro_f1": (model.metrics or {}).get("macro_f1")})
    return model


def load_model(model):
    path = model_path(model)
    if not path.exists() or hashlib.sha256(path.read_bytes()).hexdigest() != model.artifact_checksum:
        raise ValidationError("Artefact du modèle introuvable ou altéré (checksum différent).")
    return joblib.load(path)


def request_run(user, model, input_version, request=None):
    if model.status != PredictionModel.Status.READY:
        raise ValidationError({"model_version": f"Modèle non prêt (statut : {model.status}). {model.status_reason}".strip()})
    if not is_usable_for_analysis(input_version):
        raise ValidationError({"input_dataset_version": "Seuls les datasets validés / acceptés par l'ARTEC peuvent être analysés."})
    run = PredictionRun.objects.create(model_version=model, input_dataset_version=input_version, created_by=user)
    audit_log(user, "prediction.requested", "PredictionRun", run.pk, {"model": model.pk, "dataset_version": input_version.pk}, request=request)
    return run


def execute_run(run_id):
    run = PredictionRun.objects.select_related("model_version", "input_dataset_version", "created_by").get(pk=run_id)
    run.status, run.started_at = PredictionRun.Status.RUNNING, timezone.now()
    run.save(update_fields=["status", "started_at"])
    try:
        bundle = load_model(run.model_version)
        df = load_dataframe(run.input_dataset_version)
        features = bundle["features"]
        missing = [f for f in features if f not in df.columns]
        if missing:
            raise ValidationError(f"Variables manquantes dans le dataset : {', '.join(missing)}.")
        X = df[features].apply(pd.to_numeric, errors="coerce")
        mask = X.notna().all(axis=1)
        ids = df["observation_id"].astype(str) if "observation_id" in df.columns else pd.Series([f"row-{i + 1}" for i in range(len(df))], index=df.index)
        Xv = X[mask]
        pipe = bundle["pipeline"]
        proba = pipe.predict_proba(Xv)[:, [list(pipe.classes_).index(c) for c in CLASSES]]
        predicted = [CLASSES[int(p.argmax())] for p in proba]
        factors = explain(pipe, features, Xv, predicted) if len(Xv) else []
        results = [
            PredictionResult(
                prediction_run=run, observation_reference=ids[idx][:100], predicted_class=cls,
                probability_good=float(p[0]), probability_medium=float(p[1]), probability_poor=float(p[2]), confidence=float(p.max()),
                top_factors=fac,
            )
            for idx, p, cls, fac in zip(Xv.index, proba, predicted, factors)
        ]
        with transaction.atomic():
            PredictionResult.objects.filter(prediction_run=run).delete()
            PredictionResult.objects.bulk_create(results, batch_size=2000)
            counts = {c: sum(1 for r in results if r.predicted_class == c) for c in CLASSES}
            run.summary = {
                "n_observations": int(len(df)), "n_predicted": len(results), "n_skipped_missing_features": int((~mask).sum()),
                "class_counts": counts, "risk_type": run.model_version.risk_type, "needs_review": sum(1 for r in results if r.confidence < settings.ML_REVIEW_CONFIDENCE), "mean_confidence": round(float(np.mean([r.confidence for r in results])), 4) if results else None,
                "model": {"id": run.model_version_id, "name": run.model_version.name, "version": run.model_version.version, "macro_f1": run.model_version.metrics.get("macro_f1")},
                "input_dataset_version": run.input_dataset_version_id, "disclaimer": DISCLAIMER,
            }
            run.status, run.completed_at = PredictionRun.Status.COMPLETED, timezone.now()
            run.save()
        notify([run.created_by], "Prédiction terminée", f"Exécution #{run.pk} terminée ({len(results)} observations).", Notification.Type.PREDICTION_DONE, run)
    except Exception as exc:  # noqa: BLE001
        run.status, run.completed_at = PredictionRun.Status.FAILED, timezone.now()
        run.summary = {"error": f"{type(exc).__name__}: {str(getattr(exc, 'detail', exc))[:300]}"}
        run.save()
    audit_log(run.created_by, "prediction.completed", "PredictionRun", run.pk, {"status": run.status})
    return run


def store_frame_as_dataset(user, name, df, data_type, meta):
    """Enregistre un DataFrame comme nouvelle version d'un dataset propre à l'ARTEC (validé comme tout import)."""
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.datasets.models import Dataset
    from apps.datasets.services import create_version

    dataset, _ = Dataset.objects.get_or_create(
        owner_organization=user.organization, name=name,
        defaults={"data_type": data_type, "source_type": "TECHNICAL", "created_by": user, "description": "Généré automatiquement à partir des mesures QoS validées."},
    )
    if dataset.data_type != data_type:
        raise ValidationError({"name": "Un dataset de même nom et de type différent existe déjà."})
    version = create_version(dataset, SimpleUploadedFile(f"{name}.csv", df.to_csv(index=False).encode("utf-8"), content_type="text/csv"), user)
    version.schema_definition = {**version.schema_definition, "_meta": meta}
    version.save(update_fields=["schema_definition"])
    return version
