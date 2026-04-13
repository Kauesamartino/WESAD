"""
main.py — API FastAPI para predição de estado emocional via HRV cardíaco.

Endpoints:
    GET  /health          → status da API e do modelo.
    POST /predict         → prediz baseline ou stress a partir de features HRV.
    GET  /model/info      → metadados do modelo e features esperadas.

Uso rápido:
    py -m uvicorn main:app --reload
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, model_validator

from pipeline import FEATURE_COLS, MODEL_PATH, predict

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Neocare — WESAD Stress Prediction API",
    description=(
        "Predição de estado emocional (baseline vs. stress) com base em "
        "features de Variabilidade da Frequência Cardíaca (HRV) extraídas "
        "de dados do dispositivo E4 do dataset WESAD."
    ),
    version="1.0.0",
)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class HRVFeatures(BaseModel):
    """Features HRV no domínio do tempo derivadas de uma janela de IBI (após filtro Malik)."""

    mean_ibi_ms: float = Field(
        ..., gt=0, description="Média dos intervalos RR em milissegundos."
    )
    median_ibi_ms: float = Field(
        ..., gt=0, description="Mediana dos intervalos RR em ms (robusta a artefatos)."
    )
    sdnn_ms: float = Field(
        ..., ge=0, description="Desvio padrão dos intervalos RR em ms (SDNN)."
    )
    rmssd_ms: float = Field(
        ..., ge=0,
        description="Raiz quadrada da média dos quadrados das diferenças sucessivas (ms).",
    )
    sdsd_ms: float = Field(
        ..., ge=0, description="Desvio padrão das diferenças sucessivas em ms (SDSD)."
    )
    pnn50: float = Field(
        ..., ge=0.0, le=1.0,
        description="Proporção de pares de batimentos com diferença > 50 ms.",
    )
    iqr_ibi_ms: float = Field(
        ..., ge=0, description="Intervalo interquartil do IBI em ms (variabilidade robusta)."
    )
    mean_hr_bpm: float = Field(
        ..., gt=0, description="Frequência cardíaca média em bpm."
    )
    cv_ibi: float = Field(
        ..., ge=0, description="Coeficiente de variação do IBI."
    )
    artifact_ratio: float = Field(
        default=0.0, ge=0.0, le=1.0,
        description="Proporção de batimentos removidos pelo filtro Malik (0–1).",
    )

    @model_validator(mode="after")
    def check_consistency(self) -> "HRVFeatures":
        expected_hr = 60_000.0 / self.mean_ibi_ms
        if abs(expected_hr - self.mean_hr_bpm) > 30:
            raise ValueError(
                "mean_hr_bpm e mean_ibi_ms parecem inconsistentes. "
                f"IBI {self.mean_ibi_ms:.1f} ms implica ~{expected_hr:.1f} bpm."
            )
        return self


class PredictionResponse(BaseModel):
    label: int = Field(..., description="0 = baseline, 1 = stress.")
    emotional_state: str = Field(..., description="Estado emocional previsto.")
    probabilities: dict[str, float] = Field(
        ..., description="Probabilidade por classe (baseline, stress)."
    )
    model_version: str = Field(default="1.0.0")


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_path: str


class ModelInfoResponse(BaseModel):
    features: list[str]
    classes: dict[str, int]
    window_seconds: int
    description: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health", response_model=HealthResponse, tags=["infra"])
def health() -> HealthResponse:
    """Verifica se a API está operacional e se o modelo está disponível."""
    model_loaded = Path(MODEL_PATH).exists()
    return HealthResponse(
        status="ok" if model_loaded else "model_missing",
        model_loaded=model_loaded,
        model_path=str(MODEL_PATH),
    )


@app.post("/predict", response_model=PredictionResponse, tags=["predição"])
def predict_emotional_state(features: HRVFeatures) -> PredictionResponse:
    """
    Prediz o estado emocional a partir de features HRV de uma janela de 60s.

    **Estados possíveis:**
    - `baseline` — estado de repouso / sem estresse induzido.
    - `stress` — estresse detectado com base nos padrões HRV.

    **Para integração com Oracle APEX:** envie um JSON com as features HRV
    já calculadas a partir dos dados do paciente e use `emotional_state`
    e `probabilities` para alimentar o dashboard.
    """
    if not Path(MODEL_PATH).exists():
        raise HTTPException(
            status_code=503,
            detail=(
                "Modelo não encontrado. Execute controller.py para treinar "
                "antes de usar este endpoint."
            ),
        )

    try:
        result = predict(features.model_dump())
    except Exception as exc:
        logger.exception("Erro durante a inferência.")
        raise HTTPException(status_code=500, detail=f"Erro na inferência: {exc}") from exc

    return PredictionResponse(
        label=result["label"],
        emotional_state=result["class"],
        probabilities=result["probabilities"],
    )


@app.get("/model/info", response_model=ModelInfoResponse, tags=["modelo"])
def model_info() -> ModelInfoResponse:
    """Retorna metadados do modelo: features esperadas, classes e contexto."""
    return ModelInfoResponse(
        features=FEATURE_COLS,
        classes={"baseline": 0, "stress": 1},
        window_seconds=60,
        description=(
            "Melhor entre RandomForest, GradientBoosting e SVM-RBF (F1-macro LOSO-CV). "
            "Features HRV extraídas de janelas de 60s do IBI do Empatica E4 "
            "após filtragem de artefatos (critério de Malik). "
            "Dataset: WESAD — 15 sujeitos, protocolo TSST. "
            "Avaliação: Leave-One-Subject-Out CV."
        ),
    )
