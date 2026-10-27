# CommerceOps AI

Atendimento e análise operacional para e-commerce com LLM, RAG, ferramentas SQL seguras e
observabilidade com Langfuse, construído sobre o
[Brazilian E-Commerce Public Dataset by Olist](https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce).

> **Ambiente simulado.** Os pedidos, itens, pagamentos e avaliações são dados históricos reais e
> anonimizados (2016–2018). As **políticas de atendimento são fictícias**, e as **conversas, ocorrências,
> devoluções e reembolsos são simulados**. Nada aqui representa regras ou registros da Olist.
> O dataset não contém tickets de suporte: os comentários de avaliação são usados só como sinal de
> intenção e inspiração para cenários.

## Status

| Etapa | Situação |
|---|---|
| 1. Dados e problema: auditoria, políticas, taxonomia | ✅ concluída |
| 2. Aplicação básica: API, SQL seguro, RAG | 🟡 API e ferramentas de pedido prontas; RAG com busca lexical pronta, vetorial pendente |
| 3. Agente LangGraph com validação e encaminhamento | ⏳ |
| 4. Observabilidade e avaliação no Langfuse | 🟡 tracing das ferramentas pronto; datasets e avaliações pendentes |
| 5. Testes, Docker, CI/CD, Kubernetes | 🟡 testes, Docker e CI prontos; Kubernetes pendente |
| 6. Experimentos comparativos | ⏳ |

Nenhuma afirmação de ganho de qualidade, custo ou latência será feita sem medição publicada,
inclusive quando o resultado for negativo.

## Arquitetura atual

```
cliente ──► FastAPI ──► verify_customer ──► get_order_summary ──► OrderSummary (fatos calculados)
                │            │                     │
                │            └──── Postgres ───────┤   olist.* (real, somente leitura)
                │                                  └── sim.agent_actions (trilha de auditoria)
                └──► Langfuse (spans das ferramentas, order_id só como HMAC)
```

Princípios já implementados:
- **O LLM não calcula nem consulta nada sozinho.** Estágio do pedido, atraso e janelas de devolução
  são calculados em código (`src/commerceops/domain/orders.py`) e entregues prontos.
- **A autorização fica na ferramenta, não no prompt.** O cliente se identifica com número do pedido +
  prefixo do CEP e só acessa pedidos do próprio `customer_unique_id`.
- **Privilégio mínimo no banco.** A aplicação lê `olist`, escreve em `sim` sem poder apagar e não
  altera a base de conhecimento. Os testes de integração verificam isso no próprio Postgres.
- **Respostas indistinguíveis.** "Pedido inexistente" e "CEP errado" devolvem a mesma resposta.

## Como rodar

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/) e Docker.

```bash
cp .env.example .env              # preencha senhas e ORDER_ID_HMAC_KEY
# baixe os CSVs em data/raw/ (ver data/raw/README.md)

uv venv && uv pip install -e ".[dev]"
docker compose up -d db           # Postgres + pgvector, schemas e usuário da aplicação

set -a; source .env; set +a
python scripts/audit_dataset.py   # confere os dados → reports/audit/
python scripts/load_olist.py      # carrega o dataset (~15 s)
python scripts/load_kb.py         # indexa políticas e fontes legais

docker compose up -d api          # API em http://localhost:8000/docs
```

Exemplo de consulta (troque pelo pedido e CEP de um cliente real do dataset):

```bash
curl -s localhost:8000/v1/orders/lookup -H 'content-type: application/json' \
  -d '{"order_id": "<32 hex>", "zip_prefix": "01310", "reference_date": "2018-03-14"}'
```

`reference_date` é o "hoje" do ambiente simulado: os pedidos são de 2016–2018, e o sistema nunca
usa o relógio real para decidir prazos.

## Testes

```bash
pytest                    # unitários: não precisam de banco nem dos CSVs
pytest -m integration     # precisam de ADMIN_DATABASE_URL e DATABASE_URL (compose ou CI)
python scripts/render_policies.py --check   # catálogo de políticas sincronizado com os YAML
```

## Estrutura

```
knowledge_base/          políticas fictícias (YAML), taxonomia e textos do CDC: fonte única
src/commerceops/
  domain/                regras determinísticas (estágio do pedido, atraso)
  knowledge/             modelos e validação cruzada da base de conhecimento
  tools/                 ferramentas do agente, com autorização
  data/                  auditoria e carga do dataset
  api/                   FastAPI e health checks
db/init/                 schemas olist/sim/kb e usuário de privilégio mínimo
scripts/                 auditoria, carga, indexação e geração do catálogo
reports/audit/           resultado da auditoria (estatísticas agregadas)
docs/                    decisões e análises
```

## Documentação

- [Pacote de políticas v1.1: decisões](docs/01_politicas_v1.1.md)
- [Catálogo de políticas (gerado)](docs/catalogo_politicas.md)
- [Auditoria dos dados v2](docs/02_auditoria_dados.md)

## Limitações conhecidas

- Avaliação pós-compra não equivale a ticket de suporte; comentários têm no máximo ~200 caracteres.
- Não há eventos de reembolso, devolução, rastreamento ou SLA no dataset: tudo isso é simulado.
- O dataset cobre 2016–2018; a janela analítica padrão é jan/2017–ago/2018.
- Os textos do CDC em `knowledge_base/legal/` ainda não foram conferidos com a fonte oficial.

## Licença dos dados

O dataset Olist é distribuído pelo Kaggle sob CC BY-NC-SA 4.0 e não é redistribuído aqui.
