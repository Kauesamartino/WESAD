# Integrantes

- Kauê Vinicius Samartino da Silva - 559317
- João dos Santos Cardoso de Jesus - 560400
- Davi Praxedes Santos - 560719

# Neocare - WESAD Stress Prediction API

API em Python com FastAPI para classificar estresse a partir de sinais fisiologicos do dataset WESAD. O sistema foi estruturado para funcionar como o componente de IA de uma solucao integrada com Oracle APEX e Oracle Database, servindo inferencia, metadados do modelo e uma base tecnica para demonstracao do Challenge.

Esta solucao entrega suporte analitico e preditivo. Nao realiza diagnostico medico.

## Visao Geral

O fluxo principal do sistema e:

1. Ler dados do WESAD na pasta local `WESAD/`.
2. Extrair janelas rotuladas de baseline e stress a partir do protocolo experimental.
3. Gerar features HRV tabulares por janela de 60 segundos.
4. Treinar e selecionar automaticamente o melhor classificador entre RandomForest, GradientBoosting e SVM-RBF com validacao Leave-One-Subject-Out.
5. Salvar o modelo treinado em `stress_model.joblib`.
6. Expor a inferencia via FastAPI para consumo por clientes como Oracle APEX.

## Problema de IA

Problema priorizado: classificar uma janela fisiologica como `baseline` ou `stress`.

Entrada esperada: features HRV extraidas de uma janela de IBI.

Saida do modelo: classe prevista e probabilidades por classe.

Valor para o APEX: permitir dashboards, alertas, historico de inferencias e apoio a triagem operacional com base em risco de estresse.

## Arquitetura do Sistema

O repositorio hoje esta organizado em um formato simples e funcional:

```text
.github/
  agents/                    agentes especializados do workspace
.gitignore                   regras de exclusao para dataset, cache e artefatos locais
README.md                    documentacao principal do sistema
features_dataset.csv         dataset tabular de features ja extraidas
main.py                      API FastAPI e contratos HTTP
pipeline.py                  leitura do WESAD, feature engineering, treino e inferencia
requirements.txt             dependencias Python
retrain_from_csv.py          retreino sem depender da pasta WESAD/
WESAD/                       dataset bruto local por participante
```

Separacao de responsabilidades atual:

- `pipeline.py`: concentra regras de dados, extracao de features, treino, selecao de modelo e inferencia local.
- `main.py`: concentra somente a camada HTTP, validacao de payload e respostas da API.
- `retrain_from_csv.py`: oferece uma rota alternativa de operacao quando o dataset bruto nao estiver disponivel.
- `.github/agents/`: define agentes de apoio para framing, EDA, arquitetura, modelagem, integracao APEX e validacao do projeto.

## Fonte de Dados

O sistema usa o dataset WESAD armazenado localmente na pasta `WESAD/`.

Caracteristicas confirmadas no repositorio:

- Participantes: 15 sujeitos.
- Estrutura: diretorios `S2`, `S3`, `S4` ... `S17`.
- Arquivos por sujeito: questionario, arquivos auxiliares e subpasta `S*_E4_Data/`.
- Sensores visiveis no repositorio: `IBI.csv`, `HR.csv`, `BVP.csv`, `EDA.csv`, `ACC.csv`, `TEMP.csv`, `tags.csv` e `info.txt`.
- Sinais usados na versao atual do pipeline: IBI como fonte principal da modelagem; HR possui loader implementado para evolucao futura.

Rotulagem usada:

- `Base` -> `0` -> baseline.
- `TSST` -> `1` -> stress.

As janelas sao derivadas a partir de `# ORDER`, `# START` e `# END` nos arquivos `_quest.csv`.

## Pipeline de Dados e ML

### 1. Ingestao

Funcoes principais em `pipeline.py`:

- `load_ibi(subject_path)`: le o `IBI.csv` do Empatica E4 e retorna timestamp inicial e serie `[offset_s, ibi_s]`.
- `load_hr(subject_path)`: le `HR.csv` e retorna timestamp inicial, sample rate e valores de bpm.
- `parse_phase_boundaries(quest_file)`: converte o questionario do participante em intervalos rotulados de interesse.

### 2. Segmentacao temporal

Configuracoes usadas no pipeline:

- janela: 60 segundos.
- passo: 30 segundos.
- minimo de batimentos por janela apos filtro: 10.

Cada janela e gerada somente dentro dos limites temporais das fases `Base` e `TSST`.

### 3. Tratamento de artefatos

O pipeline aplica criterio de Malik com limiar de 20% entre batimentos consecutivos.

Saidas desse passo:

- serie IBI filtrada.
- `artifact_ratio`, que mede a proporcao de batimentos removidos e tambem entra como feature do modelo.

### 4. Features extraidas

As features aceitas pela API e usadas no treino sao:

| Feature | Descricao |
|---|---|
| `mean_ibi_ms` | media dos intervalos RR em ms |
| `median_ibi_ms` | mediana dos intervalos RR em ms |
| `sdnn_ms` | desvio padrao dos intervalos RR |
| `rmssd_ms` | raiz da media dos quadrados das diferencas sucessivas |
| `sdsd_ms` | desvio padrao das diferencas sucessivas |
| `pnn50` | proporcao de diferencas sucessivas acima de 50 ms |
| `iqr_ibi_ms` | intervalo interquartil dos intervalos RR |
| `mean_hr_bpm` | frequencia cardiaca media convertida do IBI |
| `cv_ibi` | coeficiente de variacao do IBI |
| `artifact_ratio` | proporcao de artefatos removidos |

### 5. Montagem do dataset

`build_dataset()` agrega todos os participantes validos e gera um dataset tabular com features, label e sujeito.

Resultado registrado em `treino_output.txt`:

- 692 janelas.
- 15 sujeitos.
- distribuicao de labels: 436 baseline e 256 stress.

O arquivo `features_dataset.csv` guarda uma versao pre-extraida desse dataset para reuso em ambientes sem o WESAD bruto.

### 6. Treino e selecao de modelo

O treino compara tres pipelines:

- RandomForest + StandardScaler.
- GradientBoosting + StandardScaler.
- SVM-RBF + StandardScaler.

Estrategia de avaliacao:

- Leave-One-Subject-Out Cross-Validation.

Racional:

- evita avaliar no mesmo sujeito usado no treino.
- aproxima o caso real de generalizacao para um novo paciente ou nova pessoa monitorada.

Melhor modelo registrado atualmente:

- SVM-RBF.
- F1-macro: 0.618.
- accuracy global: 0.62.

Resumo do melhor resultado salvo em `treino_output.txt`:

```text
baseline: precision 0.82, recall 0.51, f1-score 0.63
stress:   precision 0.49, recall 0.81, f1-score 0.61
accuracy: 0.62 em 692 janelas
```

Isso indica um modelo mais sensivel para capturar stress, com sacrificio de recall da classe baseline.

### 7. Persistencia do modelo

O melhor pipeline treinado e salvo em `stress_model.joblib`.

Esse artefato e ignorado no Git por desenho, para evitar versionamento de binarios gerados localmente.

## API FastAPI

O arquivo `main.py` expoe a aplicacao HTTP.

Metadados da API:

- titulo: `Neocare - WESAD Stress Prediction API`.
- versao: `1.0.0`.
- documentacao Swagger: `http://localhost:8000/docs`.

### Contratos

#### `GET /health`

Verifica se a API esta no ar e se o modelo treinado esta disponivel em disco.

Resposta tipica:

```json
{
  "status": "ok",
  "model_loaded": true,
  "model_path": "D:\\Projetos\\Neocare\\WESAD\\stress_model.joblib"
}
```

#### `POST /predict`

Recebe um conjunto completo de features HRV e retorna classe prevista e probabilidades.

Payload esperado:

```json
{
  "mean_ibi_ms": 810.2,
  "median_ibi_ms": 805.0,
  "sdnn_ms": 42.7,
  "rmssd_ms": 38.4,
  "sdsd_ms": 36.9,
  "pnn50": 0.18,
  "iqr_ibi_ms": 51.6,
  "mean_hr_bpm": 74.1,
  "cv_ibi": 0.052,
  "artifact_ratio": 0.03
}
```

Resposta tipica:

```json
{
  "label": 1,
  "emotional_state": "stress",
  "probabilities": {
    "baseline": 0.2134,
    "stress": 0.7866
  },
  "model_version": "1.0.0"
}
```

Validacoes aplicadas:

- valores positivos ou nao negativos conforme o campo.
- `pnn50` entre 0 e 1.
- `artifact_ratio` entre 0 e 1.
- checagem de consistencia entre `mean_ibi_ms` e `mean_hr_bpm`.

Erros relevantes:

- `503`: modelo ausente em disco.
- `422`: payload invalido.
- `500`: falha interna de inferencia.

#### `GET /model/info`

Retorna metadados do modelo e a lista oficial de features esperadas pelo endpoint de predicao.

Exemplo:

```json
{
  "features": [
    "mean_ibi_ms",
    "median_ibi_ms",
    "sdnn_ms",
    "rmssd_ms",
    "sdsd_ms",
    "pnn50",
    "iqr_ibi_ms",
    "mean_hr_bpm",
    "cv_ibi",
    "artifact_ratio"
  ],
  "classes": {
    "baseline": 0,
    "stress": 1
  },
  "window_seconds": 60,
  "description": "Melhor entre RandomForest, GradientBoosting e SVM-RBF..."
}
```

## Integracao com Oracle APEX e Oracle Database

Papel de cada componente:

- Oracle APEX: cliente da API e camada de experiencia do usuario.
- FastAPI: camada de servico para inferencia e exposicao do contrato HTTP.
- Modelo de ML: componente decisor que classifica baseline ou stress.
- Oracle Database: persistencia de historico, auditoria e base para dashboards.

Fluxo sugerido de ponta a ponta:

```text
Usuario interage com tela no Oracle APEX
-> APEX coleta ou recebe features HRV
-> APEX chama POST /predict via REST
-> FastAPI valida o payload
-> pipeline.py carrega o modelo salvo
-> modelo retorna classe e probabilidades
-> APEX recebe JSON da inferencia
-> Oracle Database persiste historico da chamada e do resultado
-> APEX exibe score, classe prevista e tendencia historica
```

Persistencia recomendada no Oracle Database:

- identificador do paciente ou usuario.
- timestamp da inferencia.
- features enviadas.
- classe prevista.
- probabilidades.
- versao do modelo.
- identificador do canal ou tela de origem.

Esse desenho sustenta rastreabilidade tecnica para o pitch e para auditoria funcional.

## Como Executar

### 1. Instalar dependencias

```bash
py -m pip install -r requirements.txt
```

### 2. Treinar a partir do dataset bruto WESAD

```bash
py pipeline.py
```

Efeito:

- constroi o dataset a partir da pasta `WESAD/`.
- compara os tres modelos.
- salva o melhor em `stress_model.joblib`.

### 3. Retreinar a partir do CSV de features

Use esta opcao quando a pasta `WESAD/` nao estiver disponivel no ambiente:

```bash
py retrain_from_csv.py
```

### 4. Subir a API

```bash
py -m uvicorn main:app --reload
```

### 5. Testar a API

Exemplo com `curl`:

```bash
curl -X POST http://localhost:8000/predict ^
  -H "Content-Type: application/json" ^
  -d "{\"mean_ibi_ms\":810.2,\"median_ibi_ms\":805.0,\"sdnn_ms\":42.7,\"rmssd_ms\":38.4,\"sdsd_ms\":36.9,\"pnn50\":0.18,\"iqr_ibi_ms\":51.6,\"mean_hr_bpm\":74.1,\"cv_ibi\":0.052,\"artifact_ratio\":0.03}"
```

## Artefatos do Projeto

- `features_dataset.csv`: dataset tabular ja processado para treino rapido e reproducao.
- `treino_output.txt`: log com distribuicao por sujeito e metricas dos classificadores avaliados.
- `stress_model.joblib`: modelo serializado gerado localmente.

## Dependencias

Dependencias principais declaradas em `requirements.txt`:

- FastAPI.
- Uvicorn.
- scikit-learn.
- joblib.
- NumPy.
- pandas.

## Automacao de Workspace

O repositorio inclui agentes em `.github/agents/` para apoiar evolucao e documentacao do projeto:

- definicao do problema.
- analise exploratoria do WESAD.
- arquitetura da API.
- modelagem de IA.
- integracao com Oracle APEX.
- validacao final.

Isso melhora rastreabilidade das decisoes no workspace, mas nao interfere na execucao da API em producao.

## Limitacoes Atuais

- O problema esta reduzido para classificacao binaria `baseline` vs `stress`.
- A versao atual usa features HRV no dominio do tempo; nao usa ainda features espectrais ou multimodais.
- O loader de HR existe, mas o fluxo principal de modelagem se apoia nas janelas de IBI.
- O desempenho atual ainda e moderado e deve ser tratado como apoio decisorio, nao como resposta clinica definitiva.
- O dataset WESAD possui contexto experimental controlado; generalizacao fora desse protocolo exige validacao adicional.

## Proximos Passos Tecnicos Sugeridos

1. Persistir inferencias no Oracle Database com um schema formal de auditoria.
2. Adicionar endpoint para receber referencia de amostra ou paciente, alem das features cruas.
3. Expandir a modelagem com EDA, BVP e features espectrais de HRV.
4. Separar a estrutura atual em pacotes `api`, `schemas`, `services` e `ml` para facilitar evolucao.

## Referencia

Dataset no Kaggle: https://www.kaggle.com/datasets/orvile/wesad-wearable-stress-affect-detection-dataset

Schmidt, P., Reiss, A., Duerichen, R., Marberger, C., and Van Laerhoven, K. Introducing WESAD, a Multimodal Dataset for Wearable Stress and Affect Detection. ICMI 2018.
