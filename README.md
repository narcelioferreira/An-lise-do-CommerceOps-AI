# CommerceOps AI

Agente de atendimento para e-commerce com LLM, RAG, ferramentas SQL seguras e observabilidade com
Langfuse, construído sobre o
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).
O foco do projeto são **evidências medidas** e **segurança verificável**, não a quantidade de
ferramentas.

> **Ambiente simulado.** Pedidos, itens, pagamentos e avaliações são dados históricos **reais** e
> anonimizados (2016–2018). As **políticas de atendimento são fictícias**. Conversas, ocorrências,
> devoluções, reembolsos e SLA são **simulados**. Nada aqui representa regras ou registros da Olist.
> O dataset não tem tickets de suporte: os comentários de avaliação servem só como sinal de intenção
> e inspiração para cenários.

## Sumário

- [Status](#status)
- [Resultados medidos](#resultados-medidos)
- [Como uma resposta é produzida](#como-uma-resposta-é-produzida)
- [Segurança](#segurança)
- [Como rodar](#como-rodar)
- [API](#api)
- [Configuração](#configuração)
- [Avaliação](#avaliação)
- [Testes e CI](#testes-e-ci)
- [Kubernetes](#kubernetes)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Decisões registradas](#decisões-registradas)
- [Limitações conhecidas](#limitações-conhecidas)

## Status

| Etapa | Situação |
|---|---|
| 1. Dados e problema: auditoria, políticas, taxonomia | ✅ Auditoria reprodutível, 12 políticas fictícias versionadas, 15 intenções, 3 artigos do CDC conferidos com a fonte oficial |
| 2. Aplicação: API, SQL seguro, RAG | ✅ FastAPI, consultas parametrizadas, busca lexical, vetorial e híbrida filtrada pela versão de política vigente |
| 3. Agente com validação e encaminhamento | ✅ Decisão em código, LLM sem ferramentas, validador de saída, encaminhamento para humano |
| 4. Observabilidade e avaliação no Langfuse | ✅ Um span por passo, dados pessoais mascarados, 24 cenários, experimentos no Langfuse |
| 5. Testes, Docker, CI/CD, Kubernetes | ✅ Testes unitários e de integração, imagem endurecida, CI com varreduras de segurança, manifests validados |
| 6. Experimentos comparativos | 🟡 Busca medida (E1) e decisões medidas (E2); agente completo e modelos (E3) aguardam execução com LLM |

Nenhuma afirmação de ganho de qualidade, custo ou latência é feita sem medição publicada, inclusive
quando o resultado é negativo.

## Resultados medidos

Detalhes, limites e arquivos de origem em [`docs/05_experimentos.md`](docs/05_experimentos.md).

**E1 — Busca** (21 cenários, k = 5, modelo de embeddings bge-m3):

| Método | Recall@5 | MRR@5 |
|---|---|---|
| Lexical (`tsvector` em português) | 0,667 | 0,444 |
| **Vetorial (bge-m3, cosseno)** | **0,810** | **0,613** |
| Híbrida (Reciprocal Rank Fusion) | 0,762 | 0,571 |

A busca híbrida **não** superou a vetorial. Com 21 cenários, a diferença entre as duas equivale a um
cenário: é indício, não conclusão. Por isso o agente usa a vetorial (decisão D11).

**E2 — Decisão com a intenção do gabarito** (24 cenários): ações, encaminhamento e políticas
corretos em 23/23, e acesso negado corretamente em 1/1. Regras e gabarito foram escritos pela mesma
pessoa, então isso mede **coerência entre os dois**, não qualidade independente.

**E3 — Agente completo, modelo grande × pequeno:** ainda não executado; o roteiro está pronto.

## Como uma resposta é produzida

```
POST /v1/chat
  │
  ├─ 1. verificar      pedido + 5 primeiros dígitos do CEP; falhou → 404 (mesma resposta para tudo)
  ├─ 2. consultar      OrderSummary: estágio, atraso, dias desde a entrega (calculados em código)
  ├─ 3. classificar    LLM → JSON validado contra a taxonomia; inválido → "outro_ou_ambiguo"
  ├─ 4. decidir        código: seções de política aplicáveis (na versão vigente na compra),
  │                    ocorrência ou solicitação a registrar, encaminhamento para humano
  ├─ 5. executar       código: escreve em sim.* conferindo a posse do pedido no próprio SQL
  ├─ 6. contextualizar seções da decisão + busca na base de conhecimento
  ├─ 7. redigir        LLM transforma fatos e notas em texto (a mensagem do cliente vai como dado)
  └─ 8. validar        código confere a resposta; reprovou → resposta-modelo segura
                       ▼
                 Langfuse: um span por passo, IDs mascarados, order_id só como HMAC
```

Princípios:

- **O LLM não tem ferramentas.** Ele só classifica a intenção e redige o texto. Consultas,
  autorização, decisões e escritas são código determinístico, testado caso a caso
  ([`domain/decisions.py`](src/commerceops/domain/decisions.py)).
- **Nada sai sem validação.** O validador confere se a resposta cita a política aplicada, se só cita
  políticas do contexto, se datas e valores vieram dos fatos, se não há frases proibidas ("reembolso
  aprovado", "foi extraviado", pedido de senha…) nem identificadores, e se o encaminhamento foi
  informado. Se reprovar, sai uma resposta-modelo que só afirma o que o código fez.
- **Encaminhamento só sobe.** Sinais de risco (saúde, Procon/advogado, cobrança não reconhecida,
  valor diferente) são detectados por regra **e** pelo LLM, somados. O LLM não consegue evitar um
  encaminhamento. Nada é negado automaticamente: fora das regras, o caso vai para uma pessoa.
- **"Hoje" é a data do cenário.** O campo `reference_date` substitui o relógio: os pedidos são de
  2016–2018, e sem isso todo pedido estaria atrasado.
- **A versão da política é a da data da compra.** A POL-DEV-001 tem duas versões (30 e 15 dias); um
  pedido de dezembro de 2017 segue a de 30 dias mesmo que a devolução seja pedida em 2018.
- **Degradação em vez de queda.** LLM fora do ar → resposta-modelo; embeddings fora do ar → busca
  lexical; Langfuse fora do ar → atendimento continua.

## Segurança

Cada controle aponta para o código e para o teste que o verifica em
[`docs/04_seguranca.md`](docs/04_seguranca.md), com referência ao
[OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/home/resources/owasp-genai-llm-top-10-2026/),
ao [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/) (ASI) e ao
[OWASP Agentic Skills Top 10](https://owasp.github.io/www-project-agentic-skills-top-10/) (AST).

| Área | Principais controles |
|---|---|
| Injeção de prompt e agência excessiva | LLM sem ferramentas; mensagem do cliente como dado JSON; saída do classificador restrita à taxonomia; validador de saída |
| Identidade e autorização | Pedido + CEP; acesso só ao próprio `customer_unique_id`; posse conferida no SQL de toda escrita; "não existe" e "não confere" indistinguíveis |
| Dados pessoais | Só fatos mínimos vão ao LLM (sem IDs de pedido, cliente ou vendedor); mascaramento de IDs, e-mail, CPF, CEP, telefone e cartão no Langfuse; `order_id` só como HMAC |
| Banco | Usuário da aplicação com privilégio mínimo: lê `olist` e `kb`, escreve em `sim` sem `DELETE`; escritas idempotentes |
| Consumo | Mensagem ≤ 1.000 caracteres; saída ≤ 2.048 tokens; timeout de 20 s; 30 requisições/min por IP |
| Cadeia de suprimentos | `uv.lock` com hashes; Actions fixadas por SHA; imagens por digest; Dependabot; `pip-audit`; gitleaks; regras do bandit no lint |
| Contêiner e cluster | Sem root, sistema de arquivos somente leitura, sem capabilities; Pod Security `restricted`; NetworkPolicy que nega tudo por padrão |
| Base de conhecimento | YAML só com `safe_load` e schema estrito; texto legal não conferido é recusado na indexação |

## Como rodar

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/) e Docker com Compose.

**1. Configuração e dependências**

```bash
cp .env.example .env     # troque as senhas e gere ORDER_ID_HMAC_KEY (comando no próprio arquivo)
uv sync --locked         # instala exatamente as versões e hashes do uv.lock
source .venv/bin/activate
```

**2. Dados** — baixe os 9 CSVs do Kaggle em `data/raw/` (instruções em
[`data/raw/README.md`](data/raw/README.md)). Os CSVs nunca são versionados.

**3. Banco e carga**

```bash
docker compose up -d db              # Postgres 16 + pgvector; cria schemas e usuário da aplicação
set -a; source .env; set +a
python scripts/audit_dataset.py      # confere os dados → reports/audit/
python scripts/load_olist.py         # carrega o dataset em olist.* (~10 s)
python scripts/load_kb.py            # indexa políticas e CDC em kb.chunks
```

`--raw-dir <pasta>` nos dois primeiros scripts aponta para outra pasta de CSVs.

**4. Embeddings (opcional, recomendado)** — sem eles só a busca lexical funciona.

```bash
docker compose --profile local-llm up -d ollama
docker compose exec ollama ollama pull bge-m3
python scripts/load_kb.py            # reindexa, agora com embeddings
```

**5. API**

```bash
docker compose up -d api             # http://localhost:8000 (documentação em /docs fora de produção)
```

O `.env` também serve para rodar a API fora do Docker:
`uvicorn commerceops.api.main:app --port 8000`.

> **Banco criado antes de 27/10/2026?** `db/init/` ganhou índices e uma permissão nova. Scripts de
> `docker-entrypoint-initdb.d` só rodam na criação do volume: recrie com `docker compose down -v` e
> carregue os dados de novo.

## API

| Rota | Para quê |
|---|---|
| `POST /v1/chat` | Atendimento completo (fluxo acima) |
| `POST /v1/orders/lookup` | Só os fatos do pedido (`OrderSummary`), sem LLM |
| `GET /health/live` | Processo vivo (probe de liveness) |
| `GET /health/ready` | Postgres responde (probe de readiness) |
| `GET /health/deep` | Postgres, LLM (`GET /models`, sem gastar tokens) e Langfuse; para monitoramento, **nunca** como probe |

As rotas `/v1` têm limite de requisições por IP. Pedido inexistente, CEP errado ou pedido de outro
cliente devolvem o mesmo `404`.

**Exemplo** (pedido real do dataset, usado no cenário `DEV-001-caso-limite-versao-01`):

```bash
curl -s localhost:8000/v1/chat -H 'content-type: application/json' -d '{
  "order_id": "02f0618d94e9aeeb35a81835fa5c64d7",
  "zip_prefix": "22753",
  "reference_date": "2018-01-23",
  "message": "Me arrependi da compra, ainda dá para devolver?"
}'
```

Campos da resposta (`ChatResult`):

| Campo | Conteúdo |
|---|---|
| `answer` | Texto para o cliente |
| `intent`, `sentiment`, `confidence` | Classificação (intenção da taxonomia; confiança de 0 a 1) |
| `escalated` | Se o caso foi encaminhado para uma pessoa |
| `policy_ids` | Políticas e artigos de lei que fundamentam a resposta |
| `ticket_id`, `request_id` | Registros criados em `sim` (ocorrência; cancelamento ou devolução) |
| `actions` | Escritas feitas: `ocorrencia:<tipo>`, `devolucao`, `cancelamento` |
| `validated` | `false` quando o texto do LLM foi recusado (ou não havia LLM) e saiu a resposta-modelo |

Sem LLM configurado, a API funciona: a classificação vira `outro_ou_ambiguo` e a resposta pede mais
detalhes.

## Configuração

Todas as variáveis estão em [`.env.example`](.env.example).

| Variável | Obrigatória | Uso |
|---|---|---|
| `DATABASE_URL` | sim | Usuário da aplicação (privilégio mínimo). No compose, é montada automaticamente |
| `ORDER_ID_HMAC_KEY` | sim | Chave do HMAC que pseudonimiza `order_id` em traces e na trilha de auditoria |
| `ADMIN_DATABASE_URL` | scripts | Superusuário, usado só pela carga e indexação |
| `POSTGRES_USER`, `POSTGRES_PASSWORD`, `APP_DB_USER`, `APP_DB_PASSWORD` | compose | Criação do banco e do usuário da aplicação |
| `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL` | não | Provedor com API compatível com OpenAI. Padrão: Groq com `openai/gpt-oss-120b` (D9) |
| `EMBEDDING_BASE_URL`, `EMBEDDING_MODEL` | não | Embeddings para a busca vetorial. Padrão: Ollama com `bge-m3` (1024 dimensões) |
| `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` | não | Tracing e experimentos; sem chaves, o tracing fica desligado |
| `ENVIRONMENT` | não | `production` desliga `/docs` e `/openapi.json` |
| `RATE_LIMIT_PER_MINUTE` | não | Requisições por minuto por IP nas rotas `/v1` (padrão 30) |

## Avaliação

Os cenários ficam em [`evals/scenarios.yaml`](evals/scenarios.yaml): 24 mensagens **simuladas**
sobre pedidos **reais**, cobrindo os casos-limite obrigatórios (versão da política pela data da
compra, prazo legal de 7 dias, devolução fora da janela, pedido inconsistente, CEP de outro cliente,
pagamento com voucher + cartão e injeção de prompt). Exigem o dataset carregado.

```bash
python scripts/run_eval.py --retrieval       # E1: Recall@5 e MRR@5 por método de busca
python scripts/run_eval.py --oracle-intent   # E2: intenção do gabarito; mede decisão, ações e redação
python scripts/run_eval.py                   # E3: agente completo (exige LLM_*)
```

Métricas por cenário: intenção correta, recall de políticas, encaminhamento correto, ações corretas,
ausência de frases proibidas e resposta validada. Todas são determinísticas. Os resultados vão para
`reports/eval/`; com `LANGFUSE_*`, cada execução também vira um experimento no Langfuse, com score por
cenário.

## Testes e CI

```bash
pytest                                      # unitários: sem banco e sem CSVs
pytest -m integration                       # exige ADMIN_DATABASE_URL e DATABASE_URL (banco de db/init/)
ruff check . && ruff format --check .       # lint, incluindo regras de segurança (bandit)
pip-audit --skip-editable                   # vulnerabilidades conhecidas nas dependências
python scripts/render_policies.py --check   # catálogo de políticas sincronizado com os YAML
```

Em 27/10/2026: 271 testes unitários e 24 de integração. Os testes de integração carregam um
mini-dataset sintético e verificam, no próprio Postgres, o privilégio mínimo, a checagem de posse, a
idempotência das escritas e o agente de ponta a ponta.

O CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) roda em push na `main` e em pull
requests:

| Job | O que faz |
|---|---|
| `unit` | Lint, `pip-audit`, catálogo de políticas, testes unitários |
| `secrets` | gitleaks em todo o histórico |
| `integration` | Testes de integração contra Postgres + pgvector |
| `docker` | Build da imagem |
| `k8s` | `kustomize build` + `kubeconform` dos overlays `dev` e `staging` |

## Kubernetes

Manifests Kustomize em [`k8s/`](k8s/README.md): base com Deployment, Service, NetworkPolicy, HTTPRoute
(Gateway API) e ConfigMap, e overlays `dev` (1 réplica) e `staging` (2 réplicas). Os namespaces usam
Pod Security Admission `restricted`. Segredos nunca vão para o git: o Secret é criado à parte, como
descrito em `k8s/README.md`. Os manifests são validados no CI, mas ainda não foram aplicados em um
cluster.

## Estrutura do repositório

```
src/commerceops/
  agent.py              fluxo de atendimento, prompts, validador e resposta-modelo
  llm.py                clientes de chat e embeddings (API compatível com OpenAI)
  evaluation.py         cenários e métricas de avaliação
  config.py             configuração lida do ambiente
  db.py                 todo o SQL da aplicação (parametrizado)
  observability.py      Langfuse, mascaramento de dados pessoais e HMAC
  api/                  FastAPI: rotas, limite de requisições, cabeçalhos de segurança, health checks
  domain/               regras determinísticas: estágio do pedido, atraso, decisão de atendimento
  knowledge/            base de conhecimento: modelos, validação cruzada, indexação e busca
  tools/                consulta de pedido (com autorização) e execução das ações em sim
  data/                 auditoria e carga do dataset
knowledge_base/         fonte única: políticas fictícias (YAML), taxonomia e textos do CDC
db/init/                schemas olist (real), sim (simulado) e kb, e usuário de privilégio mínimo
evals/                  cenários de avaliação (simulados)
scripts/                auditoria, carga, indexação, catálogo e avaliação
reports/                resultados gerados: auditoria e avaliações
k8s/                    manifests Kubernetes (Kustomize)
docs/                   decisões, análises, segurança e experimentos
tests/                  unitários e de integração (tests/integration/)
```

## Decisões registradas

| ID | Decisão | Documento |
|---|---|---|
| D1 | Prazos em dias corridos | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D2 | Comparações por data, nunca por timestamp | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D3 | Vale a versão da política vigente na data da compra | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D4 | "Hoje" é a `reference_date` do cenário, nunca o relógio | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D5 | Estágio do pedido calculado em código a partir do status e das datas | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D6 | Schemas separados: `olist` (real) e `sim` (simulado) | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D7 | Identidade por pedido + CEP; cliente é o `customer_unique_id` | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D8 | Reembolso acima de R$ 1.000 exige aprovação humana (~p99 dos pagamentos) | [01_politicas_v1.1.md](docs/01_politicas_v1.1.md) |
| D9 | LLM via API compatível com OpenAI; padrão Groq | [03_arquitetura.md](docs/03_arquitetura.md) |
| D10 | Fluxo em Python sem LangGraph; LLM sem ferramentas | [03_arquitetura.md](docs/03_arquitetura.md) |
| D11 | Contexto do agente pela busca vetorial (medido no E1) | [03_arquitetura.md](docs/03_arquitetura.md) |

Outros documentos: [auditoria dos dados](docs/02_auditoria_dados.md) e
[catálogo de políticas](docs/catalogo_politicas.md) (gerado a partir dos YAML).

## Limitações conhecidas

**Dos dados**
- Avaliação pós-compra não é ticket de suporte, e os comentários têm no máximo ~200 caracteres.
- Não há eventos de reembolso, devolução, rastreamento ou SLA no dataset: tudo isso é simulado.
- O dataset cobre 2016–2018; a janela analítica padrão é jan/2017–ago/2018.

**Da avaliação**
- Os 24 cenários e as regras foram escritos pela mesma pessoa; falta rotulagem independente e
  medição de concordância entre anotadores.
- O agente completo com LLM (E3) ainda não foi medido.
- Amostras pequenas: as diferenças do E1 são indícios, não conclusões.

**Da operação**
- O limite de requisições fica em memória, por pod; o limite global é responsabilidade do gateway.
- Atendimento de um turno, sem memória de conversa.
- Mudanças de schema exigem recriar o banco: ainda não há ferramenta de migração.
- Manifests Kubernetes validados, mas nunca aplicados em um cluster.

## Licença dos dados

O dataset Olist é distribuído pelo Kaggle sob CC BY-NC-SA 4.0 e não é redistribuído aqui.
