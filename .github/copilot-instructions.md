# Copilot Instructions — Neocare WESAD AI API

Projeto focado em Inteligência Artificial para detecção de estresse com base no dataset WESAD, exposto por uma API em Python com FastAPI e pensado para integração com Oracle APEX e Oracle Database.

---

## Objetivo do Repositório

Este repositório deve apoiar a entrega técnica do Challenge com foco em:

- definir o problema de IA que será resolvido dentro da aplicação Oracle APEX;
- construir uma API em Python com FastAPI para servir inferência, consulta de dados e suporte à integração;
- documentar o fluxo entre APEX, Oracle Database e o componente de IA;
- usar os dados da pasta `WESAD/` como base para exploração, preparo de dados, treinamento e inferência;
- sustentar a apresentação em vídeo com arquitetura, caso de uso, fluxo de dados e justificativas técnicas.

---

## Fluxo Obrigatório em Toda Tarefa

```
1. Entender o caso de uso de IA e o impacto no APEX
2. Definir a solução respeitando separação de responsabilidades
3. Implementar a API, a lógica de ML ou a documentação necessária
4. Validar dados, contrato, erros e rastreabilidade técnica
5. Confirmar aderência aos objetivos do Challenge
```

Se faltar informação essencial sobre integração, dados, infraestrutura Oracle ou critério do Challenge, parar e explicitar a dúvida ao usuário em vez de assumir detalhes críticos.

---

## Agentes do Workspace

O workspace deve usar agentes especializados por etapa para manter foco e rastreabilidade.

| Etapa | Agente | Quando usar |
|---|---|---|
| 1. Definição do problema | `wesad-problem-framing` | Para definir caso de uso, variável alvo, escopo de negócio e encaixe no APEX |
| 2. Análise exploratória | `wesad-eda` | Para inspecionar a pasta `WESAD/`, mapear arquivos, sinais, volume e viabilidade dos dados |
| 3. Arquitetura da solução | `wesad-architecture` | Para desenhar estrutura FastAPI, contratos, camadas e responsabilidades |
| 4. Modelagem de IA | `wesad-modeling` | Para escolher baseline, features, estratégia de treino e avaliação |
| 5. Integração e narrativa | `wesad-apex-integration` | Para descrever fluxo APEX → API → IA → Oracle Database e preparar documentação/diagrama |
| 6. Validação final | `wesad-validation` | Para revisar aderência técnica, lacunas, inconsistências e prontidão para entrega |

Para fluxos amplos ou tarefas multifase, preferir o agente `wesad-workflow`, que orquestra os subagentes acima e divide o trabalho em etapas.

---

## Escopo Técnico Esperado

### Backend

- Linguagem principal: Python 3.11+
- Framework da API: FastAPI
- Modelagem de contratos: Pydantic
- Servidor local: Uvicorn
- Persistência Oracle: preferir `oracledb` quando houver integração real com Oracle Database
- Dados tabulares e sinais: Pandas e NumPy
- Treinamento e baseline de ML: Scikit-learn como padrão inicial; usar redes neurais apenas se houver justificativa clara

### Inteligência Artificial

- O problema deve ser formulado como caso de uso de negócio dentro do APEX.
- O modelo escolhido deve ser justificável com base no tipo de dado disponível no WESAD.
- A primeira entrega deve priorizar simplicidade, explicabilidade e viabilidade de integração.
- Se houver várias opções de modelo, começar pela baseline mais defensável e só aumentar complexidade se isso gerar ganho real.

### Integração Oracle APEX

- O APEX deve ser tratado como cliente da API.
- O Oracle Database deve ser tratado como fonte e/ou destino de dados operacionais, resultados de inferência, auditoria e histórico.
- A documentação sempre deve explicar o caminho completo: ação do usuário no APEX → chamada da API → processamento da IA → persistência/retorno.

---

## Problema de IA Prioritário

O projeto deve assumir como caso de uso principal:

**predição ou classificação de nível de estresse com base em sinais fisiológicos e de movimento do dataset WESAD**, para posterior consumo dentro da aplicação Oracle APEX.

Exemplos aceitáveis de aplicação no APEX:

- classificar uma amostra como `baseline`, `stress` ou `amusement`;
- estimar risco de estresse a partir de sinais agregados;
- exibir recomendação, alerta ou triagem com base no resultado do modelo.

Evitar prometer diagnóstico clínico. A solução deve ser apresentada como apoio analítico ou preditivo, não como diagnóstico médico.

---

## Fonte de Dados

Usar prioritariamente os dados presentes em `WESAD/`.

Ao documentar ou implementar, deixar explícito:

- origem: dataset WESAD local no repositório;
- estrutura: diretórios por participante como `S2`, `S3`, `S10` etc.;
- formatos encontrados: CSV e arquivos auxiliares por sensor;
- granularidade: sinais fisiológicos e de movimento coletados por participante;
- volume: quantidade de participantes, arquivos por participante e colunas efetivamente usadas.

Nunca inventar schema, frequência de amostragem ou labels sem validar contra os arquivos reais ou documentação disponível.

---

## Diretrizes de Arquitetura

Preferir uma estrutura simples e evolutiva como:

```
app/
	api/           ← rotas FastAPI
	schemas/       ← modelos Pydantic
	services/      ← regras de negócio e orquestração
	ml/            ← carga de dados, features, treino, inferência
	repositories/  ← acesso a Oracle ou outras fontes
	core/          ← config, logging, settings
```

Regras:

- rotas não devem concentrar regra de negócio;
- leitura e transformação do WESAD devem ficar fora das rotas;
- treinamento, feature engineering e inferência devem ser isolados em módulos próprios;
- integração com banco não deve ser acoplada à camada HTTP;
- configurações devem sair de variáveis de ambiente ou arquivo de settings.

---

## Regras Globais de Implementação

- Usar type hints em funções públicas.
- Validar payloads e respostas com Pydantic.
- Não colocar lógica pesada diretamente nos endpoints.
- Tratar erros com `HTTPException` ou handlers centralizados.
- Usar logging estruturado; não usar `print` como estratégia principal da aplicação.
- Evitar acoplamento entre código de API, treinamento e persistência.
- Toda decisão técnica relevante deve ser justificável no contexto do pitch.
- Quando houver trade-off entre sofisticação e clareza, priorizar clareza.

---

## Regras para Escolha do Modelo de IA

Ao propor um modelo, a resposta ou documentação deve explicar:

- qual problema será resolvido;
- qual é a variável alvo;
- quais sinais ou features entram no modelo;
- por que o modelo é adequado ao volume e formato dos dados;
- como será avaliado;
- como o resultado será consumido no APEX.

Preferências iniciais:

- Para baseline tabular com features extraídas: `RandomForest`, `XGBoost` equivalente ou `LogisticRegression`, se fizer sentido.
- Para séries temporais brutas: considerar CNN 1D ou arquitetura temporal apenas se houver pipeline e dados suficientes.
- Evitar LLM/NLP se o problema central for classificação de sinais fisiológicos.

Se a escolha for mais complexa que o necessário para a entrega, justificar explicitamente.

---

## Contrato Esperado da API

Sempre que possível, a API deve contemplar estes blocos:

- endpoint de health check;
- endpoint para inferência/predição;
- endpoint opcional para listar classes, métricas ou metadados do modelo;
- endpoint opcional para receber features já preparadas ou referência a dados persistidos no Oracle.

Toda rota deve deixar claro:

- entrada esperada;
- validações;
- formato da resposta;
- possíveis erros de negócio ou integração.

---

## Documentação Obrigatória

O repositório e as respostas geradas devem facilitar a entrega destes artefatos:

- definição do problema de IA no contexto da aplicação APEX;
- descrição dos dados usados, incluindo origem, formato e recorte mínimo;
- justificativa do modelo escolhido;
- descrição do fluxo APEX → API → IA → Oracle Database → APEX;
- diagrama simples de integração;
- explicação objetiva para sustentar um pitch de aproximadamente 5 minutos.

Ao escrever documentação, priorizar linguagem clara, objetiva e reaproveitável na apresentação.

---

## Critérios de Qualidade

As entregas devem maximizar:

- aplicação técnica correta de conceitos de IA;
- clareza de comunicação técnica;
- organização do repositório;
- coerência entre código, dados, arquitetura e narrativa do pitch.

Evitar:

- código sem separação de responsabilidades;
- documentação genérica que não converse com o WESAD;
- endpoints sem contrato claro;
- diagramas inconsistentes com o fluxo real;
- afirmações sobre Oracle APEX ou Oracle Database sem estratégia concreta de integração.

---

## Regra Final

Toda implementação, documentação ou sugestão precisa responder a esta pergunta:

**como essa API de IA baseada em WESAD será entendida, demonstrada e integrada à aplicação Oracle APEX de forma tecnicamente defensável?**