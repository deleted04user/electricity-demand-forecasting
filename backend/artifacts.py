"""Validate the trusted repository artifact before deserializing it.

Checksums detect accidental replacement, not hostile files. Pickle/joblib can execute
code: both the manifest and model must come from a trusted repository/release.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol, cast

import joblib
import numpy as np
import pandas as pd
import xgboost
from numpy.typing import NDArray
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Predictor(Protocol):
    def predict(self, data: pd.DataFrame) -> NDArray[np.floating[Any]]: ...

    def get_params(self) -> dict[str, Any]: ...


class ArtifactError(ValueError):
    """A required artifact failed an explicit trust or compatibility check."""


class Period(BaseModel):
    start: str
    end: str

    @model_validator(mode="after")
    def valid_range(self) -> Period:
        start, end = pd.Timestamp(self.start), pd.Timestamp(self.end)
        if pd.isna(start) or pd.isna(end) or start.tzinfo or end.tzinfo or start > end:
            raise ValueError("Artifact periods must contain ordered naive timestamps")
        return self


class Manifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: int = Field(strict=True, ge=1, le=1)
    model_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    features: list[str] = Field(min_length=1)
    xgboost_major_minor: str = Field(pattern=r"^\d+\.\d+$")

    @field_validator("features")
    @classmethod
    def unique_features(cls, values: list[str]) -> list[str]:
        if any(not value for value in values) or len(values) != len(set(values)):
            raise ValueError("Artifact feature names must be unique and nonempty")
        return values


class PackageMetadata(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)
    features: list[str] = Field(min_length=1)
    feature_importance: dict[str, float]
    training_date: datetime
    training_period: Period
    early_stopping_period: Period
    test_period: Period
    metrics: dict[str, float]
    model_params: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def compatible_schema(self) -> PackageMetadata:
        if len(self.features) != len(set(self.features)):
            raise ValueError("Duplicate model features")
        if set(self.feature_importance) != set(self.features):
            raise ValueError("Feature importance does not match the model feature schema")
        if pd.Timestamp(self.training_period.end) >= pd.Timestamp(self.test_period.start):
            raise ValueError("Training and held-out periods overlap")
        if pd.Timestamp(self.early_stopping_period.end) >= pd.Timestamp(self.test_period.start):
            raise ValueError("Early-stopping and held-out periods overlap")
        return self


@dataclass(frozen=True)
class ModelArtifact:
    model: Predictor
    package: dict[str, Any]
    sha256: str
    features: list[str]


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_sha256(path: Path) -> str:
    """Git checkouts may use LF or CRLF; source identity must be portable."""
    return hashlib.sha256(path.read_text(encoding="utf-8").encode()).hexdigest()


def publish_model_manifest(path: Path, manifest_path: Path, features: list[str]) -> None:
    """Pin a model just produced by trusted training; never call on user uploads."""
    manifest = Manifest(
        schema_version=1,
        model_sha256=file_sha256(path),
        features=features,
        xgboost_major_minor=".".join(xgboost.__version__.split(".")[:2]),
    )
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)


def load_model(path: Path, manifest_path: Path) -> ModelArtifact:
    """Refuse any unpinned model before joblib executes its trusted contents."""
    try:
        manifest = Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        serialized = path.read_bytes()
        digest = hashlib.sha256(serialized).hexdigest()
        if digest != manifest.model_sha256:
            raise ArtifactError("Model checksum does not match the trusted manifest")
        if ".".join(xgboost.__version__.split(".")[:2]) != manifest.xgboost_major_minor:
            raise ArtifactError("XGBoost runtime does not match the trusted artifact manifest")
        package: object = joblib.load(BytesIO(serialized))
        if not isinstance(package, dict) or "model" not in package:
            raise ArtifactError("Model package must contain a model and metadata")
        metadata = PackageMetadata.model_validate(package)
        model = package["model"]
        if not isinstance(model, xgboost.XGBRegressor):
            raise ArtifactError("Model package requires an XGBRegressor")
        if metadata.features != manifest.features:
            raise ArtifactError("Model feature order does not match the trusted manifest")
        if model.get_booster().feature_names != metadata.features:
            raise ArtifactError("Model feature order does not match the fitted booster")
        return ModelArtifact(cast(Predictor, model), package, digest, metadata.features)
    except ArtifactError:
        raise
    except Exception as exc:
        raise ArtifactError(f"Model artifact validation failed ({type(exc).__name__})") from exc
