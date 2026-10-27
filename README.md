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
| 2. Aplicação básica: API, SQL seguro, RAG | ✅ busca lexical, vetorial e híbrida (RRF) filtrada pela versão vigente |
| 3. Agente com validação e encaminhamento | ✅ decisão em código, LLM sem ferramentas, validador de saída (D10) |
| 4. Observabilidade e avaliação no Langfuse | ✅ span por passo, 24 cenários, métricas determinísticas e experimentos no Langfuse |
| 5. Testes, Docker, CI/CD, Kubernetes | ✅ manifests (base + dev/staging) validados no CI; ver `k8s/README.md` |
| 6. Experimentos comparativos | 🟡 busca medida (vetorial > híbrida > lexical); modelos: roteiro pronto, falta a chave do LLM |

Nenhuma afirmação de ganho de qualidade, custo ou latência será feita sem medição publicada,
inclusive quando o resultado for negativo.

## Arquitetura atual

```
POST /v1/chat ─► verificar (pedido + CEP) ─► OrderSummary ─► classificar (LLM, JSON validado)
                                                                   │
   resposta ◄─ validar ◄─ redigir (LLM) ◄─ contexto (busca) ◄─ executar ◄─ decidir (código)
      │           │                            │                   │
      │           └─ reprovou: resposta-modelo  └─ kb.chunks         └─ sim.* (com checagem de posse)
      └─► Langfuse: um span por passo, dados pessoais mascarados, order_id só como HMAC
```

Princípios:
- **O LLM não tem ferramentas.** Ele classifica a intenção e redige o texto. Consultas, autorização,
  decisões e escritas são código (`domain/decisions.py`, `tools/`), testado caso a caso (D10).
- **Nada sai sem validação.** Política citada, datas, valores e frases proibidas são conferidos; se o
  texto reprovar, sai uma resposta-modelo que só afirma o que o código fez.
- **A autorização fica na ferramenta e no SQL.** O cliente se identifica com número do pedido +
  prefixo do CEP; toda escrita confere a posse do pedido no próprio banco.
- **Privilégio mínimo no banco.** A aplicação lê `olist` e `kb` e escreve em `sim` sem poder apagar.
- **Respostas indistinguíveis.** "Pedido inexistente" e "CEP errado" devolvem a mesma resposta.
- Controles de segurança e seus testes: [`docs/04_seguranca.md`](docs/04_seguranca.md).

## Como rodar

Pré-requisitos: Python 3.12, [uv](https://docs.astral.sh/uv/) e Docker.

```bash
cp .env.example .env              # preencha senhas e ORDER_ID_HMAC_KEY
# baixe os CSVs em data/raw/ (ver data/raw/README.md)

uv sync --locked                  # dependências exatas do uv.lock
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

Conversa com o agente (exige `LLM_*` no `.env`; sem LLM, responde com a resposta-modelo):

```bash
curl -s localhost:8000/v1/chat -H 'content-type: application/json' \
  -d '{"order_id": "<32 hex>", "zip_prefix": "01310", "reference_date": "2018-03-14",
       "message": "Comprei há duas semanas e me arrependi, posso devolver?"}'
```

`reference_date` é o "hoje" do ambiente simulado: os pedidos são de 2016–2018, e o sistema nunca
usa o relógio real para decidir prazos.

## Avaliação

```bash
python scripts/run_eval.py --retrieval       # Recall@5 e MRR@5 da busca, por método
python scripts/run_eval.py --oracle-intent   # intenção do gabarito: mede decisão, ações e redação
python scripts/run_eval.py                   # agente completo (exige LLM_*)
```

Os cenários (`evals/scenarios.yaml`) são simulados sobre pedidos reais e exigem o dataset carregado.
Resultados em `reports/eval/`; com `LANGFUSE_*`, cada execução também vira um experimento no Langfuse.

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
  agent.py               fluxo de atendimento, prompts e validador da resposta
  llm.py                 clientes de chat e embeddings (API compatível com OpenAI)
  domain/                regras determinísticas (estágio, atraso, decisão de atendimento)
  knowledge/             base de conhecimento: modelos, validação e busca (lexical, vetorial, híbrida)
  tools/                 consulta e ações sobre pedidos, com autorização
  data/                  auditoria e carga do dataset
  api/                   FastAPI, limites de requisição e health checks
db/init/                 schemas olist/sim/kb e usuário de privilégio mínimo
scripts/                 auditoria, carga, indexação, catálogo e avaliação
evals/                   cenários de avaliação (simulados)
k8s/                     manifests Kubernetes (Kustomize)
reports/                 auditoria e avaliações (gerados)
docs/                    decisões e análises
```

## Documentação

- [Pacote de políticas v1.1: decisões](docs/01_politicas_v1.1.md)
- [Catálogo de políticas (gerado)](docs/catalogo_politicas.md)
- [Auditoria dos dados v2](docs/02_auditoria_dados.md)
- [Arquitetura e decisões técnicas](docs/03_arquitetura.md) (D9: LLM Groq)
- [Segurança: controles e evidências](docs/04_seguranca.md)
- [Experimentos e resultados](docs/05_experimentos.md)

## Limitações conhecidas

- Avaliação pós-compra não equivale a ticket de suporte; comentários têm no máximo ~200 caracteres.
- Não há eventos de reembolso, devolução, rastreamento ou SLA no dataset: tudo isso é simulado.
- O dataset cobre 2016–2018; a janela analítica padrão é jan/2017–ago/2018.

## Licença dos dados

O dataset Olist é distribuído pelo Kaggle sob CC BY-NC-SA 4.0 e não é redistribuído aqui.
