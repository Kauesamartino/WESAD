"""
controller.py — Pipeline de coleta e modelagem de estresse cardíaco com WESAD.

Fonte de dados: pasta local WESAD/ (dispositivo E4 da Empatica).
Sinais usados : IBI (Inter-Beat Interval) e HR (Heart Rate).
Labels         : fases baseline e TSST extraídas do questionário _quest.csv.
Modelo         : RandomForest / SVM / GradientBoosting com features HRV (domínio do tempo).
Avaliação      : Leave-One-Subject-Out (LOSO) cross-validation.

Nota técnica (E4 PPG): O dispositivo Empatica E4 usa fotopletismografia de pulso,
susceptível a artefatos de movimento. Durante o TSST (tarefa de discurso em pé),
o IBI medido tende a ser mais alto (batimentos perdidos), o que por si só é um
sinal discriminante (artifact_ratio). O filtro de Malik remove transições
consecutivas > MALIK_PCT antes do cálculo das features.
"""
from __future__ import annotations

import logging
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.metrics import classification_report, f1_score
from sklearn.model_selection import LeaveOneGroupOut, cross_val_predict
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

# ---------------------------------------------------------------------------
# Configurações globais
# ---------------------------------------------------------------------------

WESAD_DIR = Path(__file__).parent / "WESAD"
MODEL_PATH = Path(__file__).parent / "stress_model.joblib"

LABEL_BASELINE = 0
LABEL_STRESS = 1

# Fases do protocolo WESAD que nos interessam para classificação binária
PHASE_LABEL_MAP: dict[str, int] = {
    "Base": LABEL_BASELINE,
    "TSST": LABEL_STRESS,
}

WINDOW_SECONDS = 60
STEP_SECONDS = 30
MIN_IBI_PER_WINDOW = 10

# Critério de Malik: transição consecutiva > MALIK_PCT do beat anterior é artefato
MALIK_PCT = 0.20

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Leitura dos arquivos E4
# ---------------------------------------------------------------------------

def load_ibi(subject_path: Path) -> tuple[float, pd.DataFrame]:
    """
    Lê o arquivo IBI.csv do dispositivo E4.

    Retorna:
        start_ts  : timestamp Unix do início da gravação.
        DataFrame : colunas [offset_s, ibi_s] — offset em segundos desde
                    o início e intervalo entre batimentos em segundos.
    """
    ibi_file = subject_path / f"{subject_path.name}_E4_Data" / "IBI.csv"
    with ibi_file.open() as f:
        header_line = f.readline()

    start_ts = float(header_line.split(",")[0].strip())
    df = pd.read_csv(
        ibi_file,
        skiprows=1,
        header=None,
        names=["offset_s", "ibi_s"],
    )
    return start_ts, df


def load_hr(subject_path: Path) -> tuple[float, float, np.ndarray]:
    """
    Lê o arquivo HR.csv do dispositivo E4.

    Retorna:
        start_ts    : timestamp Unix do início.
        sample_rate : frequência de amostragem em Hz.
        values      : array de frequências cardíacas (bpm).
    """
    hr_file = subject_path / f"{subject_path.name}_E4_Data" / "HR.csv"
    lines = hr_file.read_text().splitlines()
    start_ts = float(lines[0])
    sample_rate = float(lines[1])
    values = np.array([float(v) for v in lines[2:] if v.strip()])
    return start_ts, sample_rate, values


# ---------------------------------------------------------------------------
# 2. Labels via questionário (_quest.csv)
# ---------------------------------------------------------------------------

def parse_phase_boundaries(quest_file: Path) -> list[dict]:
    """
    Extrai limites de fase (início/fim em segundos a partir do início da
    gravação E4) a partir do questionário.

    Retorna lista de dicts com chaves: phase, label, start_s, end_s.
    Apenas as fases presentes em PHASE_LABEL_MAP são incluídas.
    """
    df = pd.read_csv(quest_file, sep=";", index_col=0)

    # Normaliza o índice para remover espaços extras
    df.index = df.index.str.strip()

    order_row = df.loc["# ORDER"].dropna()
    start_row = df.loc["# START"].dropna()
    end_row = df.loc["# END"].dropna()

    phases: list[dict] = []
    for col in order_row.index:
        phase_name = str(order_row[col]).strip()
        if phase_name not in PHASE_LABEL_MAP:
            continue
        try:
            start_min = float(start_row[col])
            end_min = float(end_row[col])
        except (KeyError, ValueError, TypeError):
            logger.debug(f"Fase '{phase_name}': tempo ausente ou inválido em {quest_file.name}")
            continue

        phases.append(
            {
                "phase": phase_name,
                "label": PHASE_LABEL_MAP[phase_name],
                "start_s": start_min * 60.0,
                "end_s": end_min * 60.0,
            }
        )

    return phases


# ---------------------------------------------------------------------------
# 3. Filtro de artefatos e extração de features HRV (domínio do tempo)
# ---------------------------------------------------------------------------

def filter_ibi_artifacts(ibi_s: np.ndarray) -> tuple[np.ndarray, float]:
    """
    Remove batimentos com transição consecutiva > MALIK_PCT (critério de Malik).

    Retorna:
        cleaned     : array filtrado em segundos.
        artifact_ratio : proporção de batimentos removidos (0–1).
    """
    if len(ibi_s) < 2:
        return ibi_s, 0.0

    artifact_mask = np.zeros(len(ibi_s), dtype=bool)
    artifact_mask[0] = False
    for i in range(1, len(ibi_s)):
        ref = ibi_s[i - 1]
        if ref > 0 and abs(ibi_s[i] - ref) / ref > MALIK_PCT:
            artifact_mask[i] = True

    n_artifacts = int(artifact_mask.sum())
    cleaned = ibi_s[~artifact_mask]
    ratio = n_artifacts / len(ibi_s)
    return cleaned, ratio


def extract_hrv_features(ibi_window: np.ndarray) -> dict | None:
    """
    Calcula features HRV no domínio do tempo a partir de um array de
    intervalos RR (em segundos).

    Features calculadas após filtragem de artefatos (Malik):
        mean_ibi_ms    : média dos intervalos (ms).
        median_ibi_ms  : mediana — robusta a artefatos residuais.
        sdnn_ms        : desvio padrão dos intervalos (ms).
        rmssd_ms       : raiz da média dos quadrados das diff. sucessivas (ms).
        sdsd_ms        : desvio padrão das diferenças sucessivas (ms).
        pnn50          : proporção de pares com |diff| > 50 ms.
        iqr_ibi_ms     : intervalo interquartil (ms) — variabilidade robusta.
        mean_hr_bpm    : frequência cardíaca média convertida do IBI.
        cv_ibi         : coeficiente de variação do IBI.
        artifact_ratio : proporção de batimentos removidos pelo filtro Malik.

    Retorna None se não houver batimentos suficientes após filtragem.
    """
    cleaned, artifact_ratio = filter_ibi_artifacts(ibi_window)

    if len(cleaned) < MIN_IBI_PER_WINDOW:
        return None

    ibi_ms = cleaned * 1000.0
    diffs = np.diff(ibi_ms)

    return {
        "mean_ibi_ms": float(np.mean(ibi_ms)),
        "median_ibi_ms": float(np.median(ibi_ms)),
        "sdnn_ms": float(np.std(ibi_ms, ddof=1)),
        "rmssd_ms": float(np.sqrt(np.mean(diffs ** 2))) if len(diffs) > 0 else 0.0,
        "sdsd_ms": float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0,
        "pnn50": float(np.sum(np.abs(diffs) > 50.0) / len(diffs)) if len(diffs) > 0 else 0.0,
        "iqr_ibi_ms": float(np.percentile(ibi_ms, 75) - np.percentile(ibi_ms, 25)),
        "mean_hr_bpm": float(60_000.0 / np.mean(ibi_ms)),
        "cv_ibi": float(np.std(ibi_ms, ddof=1) / np.mean(ibi_ms)),
        "artifact_ratio": float(artifact_ratio),
    }


# ---------------------------------------------------------------------------
# 4. Construção do dataset por sujeito
# ---------------------------------------------------------------------------

def build_subject_windows(
    subject_path: Path,
    window_s: float = WINDOW_SECONDS,
    step_s: float = STEP_SECONDS,
) -> pd.DataFrame:
    """
    Constrói janelas de features HRV com labels para um sujeito.

    O IBI é segmentado em janelas deslizantes dentro de cada fase do protocolo.
    Janelas com poucos batimentos (< MIN_IBI_PER_WINDOW) são descartadas.
    """
    quest_file = subject_path / f"{subject_path.name}_quest.csv"

    try:
        phases = parse_phase_boundaries(quest_file)
        _, ibi_df = load_ibi(subject_path)
    except Exception as exc:
        logger.warning(f"{subject_path.name}: ignorado — {exc}")
        return pd.DataFrame()

    if not phases or ibi_df.empty:
        logger.warning(f"{subject_path.name}: sem fases ou IBI vazio.")
        return pd.DataFrame()

    rows: list[dict] = []
    for phase in phases:
        t = phase["start_s"]
        while t + window_s <= phase["end_s"]:
            mask = (ibi_df["offset_s"] >= t) & (ibi_df["offset_s"] < t + window_s)
            window_ibi = ibi_df.loc[mask, "ibi_s"].values

            features = extract_hrv_features(window_ibi)
            if features is not None:
                features["label"] = phase["label"]
                features["subject"] = subject_path.name
                rows.append(features)

            t += step_s

    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 5. Dataset completo
# ---------------------------------------------------------------------------

def build_dataset(wesad_dir: Path = WESAD_DIR) -> pd.DataFrame:
    """
    Agrega janelas HRV de todos os sujeitos disponíveis em wesad_dir.
    """
    subject_dirs = sorted(wesad_dir.glob("S*"))
    frames: list[pd.DataFrame] = []

    for subject_dir in subject_dirs:
        df = build_subject_windows(subject_dir)
        if not df.empty:
            frames.append(df)
            counts = df["label"].value_counts().to_dict()
            logger.info(f"{subject_dir.name}: {len(df)} janelas — {counts}")

    if not frames:
        raise RuntimeError(f"Nenhum dado encontrado em {wesad_dir}")

    full = pd.concat(frames, ignore_index=True)
    logger.info(
        f"Dataset total: {len(full)} janelas, "
        f"{full['subject'].nunique()} sujeitos, "
        f"labels={full['label'].value_counts().to_dict()}"
    )
    return full


# ---------------------------------------------------------------------------
# 6. Treinamento e avaliação
# ---------------------------------------------------------------------------

FEATURE_COLS = [
    "mean_ibi_ms",
    "median_ibi_ms",
    "sdnn_ms",
    "rmssd_ms",
    "sdsd_ms",
    "pnn50",
    "iqr_ibi_ms",
    "mean_hr_bpm",
    "cv_ibi",
    "artifact_ratio",
]


def train(df: pd.DataFrame, save_path: Path = MODEL_PATH) -> Pipeline:
    """
    Compara RandomForest, GradientBoosting e SVM-RBF com LOSO-CV.
    Salva e retorna o modelo com maior F1-macro.

    A avaliação Leave-One-Subject-Out simula inferência em um sujeito
    nunca visto durante o treino — cenário realista para o APEX.
    """
    X = df[FEATURE_COLS].values
    y = df["label"].values
    groups = df["subject"].values

    candidates: dict[str, Pipeline] = {
        "RandomForest": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", RandomForestClassifier(
                n_estimators=300, random_state=42, n_jobs=-1,
                class_weight="balanced",
            )),
        ]),
        "GradientBoosting": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", GradientBoostingClassifier(
                n_estimators=200, learning_rate=0.1, max_depth=4, random_state=42,
            )),
        ]),
        "SVM-RBF": Pipeline([
            ("scaler", StandardScaler()),
            ("clf", SVC(
                kernel="rbf", C=1.0, gamma="scale",
                class_weight="balanced", probability=True, random_state=42,
            )),
        ]),
    }

    logo = LeaveOneGroupOut()
    label_names = {LABEL_BASELINE: "baseline", LABEL_STRESS: "stress"}
    target_names = [label_names[i] for i in sorted(label_names)]

    best_name: str = ""
    best_f1: float = -1.0
    best_pipeline: Pipeline | None = None

    for name, pipe in candidates.items():
        logger.info(f"Avaliando {name} com LOSO-CV...")
        y_pred = cross_val_predict(pipe, X, y, groups=groups, cv=logo)
        f1 = f1_score(y, y_pred, average="macro")
        print(f"\n=== LOSO-CV — {name} (F1-macro={f1:.3f}) ===")
        print(classification_report(y, y_pred, target_names=target_names))
        if f1 > best_f1:
            best_f1 = f1
            best_name = name
            best_pipeline = pipe

    logger.info(f"Melhor modelo: {best_name} (F1-macro={best_f1:.3f})")
    logger.info("Treinando modelo final em todos os dados...")
    best_pipeline.fit(X, y)  # type: ignore[union-attr]
    joblib.dump(best_pipeline, save_path)
    logger.info(f"Modelo salvo em: {save_path}")

    # Importância de features (disponível para RF e GB)
    clf = best_pipeline.named_steps["clf"]  # type: ignore[union-attr]
    if hasattr(clf, "feature_importances_"):
        importances = clf.feature_importances_
        print(f"\n=== Importância das Features ({best_name}) ===")
        for feat, imp in sorted(zip(FEATURE_COLS, importances), key=lambda x: -x[1]):
            print(f"  {feat:<20}: {imp:.4f}")

    return best_pipeline  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 7. Inferência (usado pelo endpoint FastAPI)
# ---------------------------------------------------------------------------

def predict(features: dict, model_path: Path = MODEL_PATH) -> dict:
    """
    Executa inferência para um conjunto de features HRV já extraídas.

    Parâmetros:
        features : dict com chaves em FEATURE_COLS.

    Retorna:
        dict com 'label' (int), 'class' (str) e 'probabilities' (dict).
    """
    pipeline: Pipeline = joblib.load(model_path)
    X = np.array([[features[col] for col in FEATURE_COLS]])
    label = int(pipeline.predict(X)[0])
    proba = pipeline.predict_proba(X)[0]

    label_names = {LABEL_BASELINE: "baseline", LABEL_STRESS: "stress"}
    return {
        "label": label,
        "class": label_names[label],
        "probabilities": {
            label_names[i]: round(float(p), 4) for i, p in enumerate(proba)
        },
    }


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    df = build_dataset()
    train(df)
