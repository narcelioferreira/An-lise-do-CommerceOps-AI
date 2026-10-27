# CLAUDE.md

Instruções para o Claude Code neste repositório. Leia antes de qualquer mudança.

## O projeto

CommerceOps AI: atendimento e análise operacional para e-commerce com LLM, RAG, ferramentas SQL
seguras e observabilidade (Langfuse), sobre o dataset público da Olist (2016–2018). É um projeto de
portfólio: o valor está nas **evidências medidas**, não na quantidade de ferramentas.

- **Idioma:** português do Brasil em código voltado ao usuário, documentação, docstrings,
  comentários, mensagens de erro e commits. Identificadores (variáveis, IDs de intenção) em ASCII,
  sem acentos.
- **Etapas:** ver a tabela de status no `README.md`. Atualize-a quando uma etapa avançar.

## Comandos

```bash
uv sync --locked                         # instala exatamente o uv.lock (com hashes)
ruff check . && ruff format --check .   # inclui as regras de segurança (bandit)
pip-audit --skip-editable                # vulnerabilidades conhecidas nas dependências
pytest                                   # unitários: sem banco e sem CSVs
pytest -m integration                    # exige ADMIN_DATABASE_URL e DATABASE_URL
python scripts/render_policies.py        # regenera docs/catalogo_politicas.md
python scripts/render_policies.py --check
python scripts/audit_dataset.py          # exige os CSVs em data/raw/
docker compose up -d db                  # Postgres + pgvector com db/init/
python scripts/load_olist.py && python scripts/load_kb.py
python scripts/run_eval.py [--retrieval | --oracle-intent]   # exige o dataset real carregado
```

Antes de considerar uma tarefa pronta: lint, formatação, `pytest` e `render_policies.py --check`
precisam passar. O CI (`.github/workflows/ci.yml`) roda tudo isso, mais os testes de integração com
pgvector e o build da imagem.

## Regras que não podem ser quebradas

**Honestidade dos dados**
- Pedidos, itens, pagamentos e avaliações são **reais**. Políticas são **fictícias**. Conversas,
  ocorrências, devoluções, reembolsos e SLA são **simulados**. Nunca apresente nada simulado como
  registro da Olist, e marque cenários com `simulated: true`.
- Avaliação pós-compra **não é ticket de suporte**. Nota baixa não é sinônimo de atraso ou defeito.
- Não afirme ganho de qualidade, custo ou latência sem medição publicada. Resultados negativos
  também são publicados.

**Cálculos determinísticos, nunca pelo LLM**
- Estágio do pedido, atraso, janelas de devolução e versão de política vêm de
  `src/commerceops/domain/orders.py` e das ferramentas. O LLM só lê `OrderSummary`.
- Compare **datas, não timestamps** (decisão D2). A previsão de entrega é sempre meia-noite, e
  `review_creation_date` só tem data.
- Prazos em **dias corridos** (D1). O "hoje" é sempre o `reference_date` do cenário (D4), nunca o
  relógio do sistema.
- Versão de política aplicável = a vigente na **data da compra** (D3).

**Segurança** (controles e testes em `docs/04_seguranca.md`)
- O LLM não recebe ferramentas: classifica e redige. Decisão e escrita são código (D10). Toda resposta
  passa por `agent.validate`; não afrouxe o validador para uma resposta passar.
- Autorização fica **na ferramenta**, nunca no prompt. O cliente é verificado por `order_id` +
  prefixo do CEP e só acessa pedidos do próprio `customer_unique_id`. `customer_id` é único por
  pedido e **não** identifica a pessoa.
- "Pedido inexistente" e "dados não conferem" devolvem a mesma resposta.
- Nenhum SQL gerado pelo LLM: só consultas parametrizadas em `src/commerceops/db.py`.
- `order_id` nunca vai cru para traces ou logs: use `hash_id` (HMAC) de `observability.py`.
- O usuário de banco da aplicação lê `olist`, escreve em `sim` sem `DELETE` e só lê `kb`. Não
  amplie esses privilégios sem justificativa explícita.
- Langfuse é observabilidade, não dependência: falha dele não pode derrubar o atendimento, e o
  provedor de LLM não entra nas probes do Kubernetes (só em `/health/deep`).

**Consumo de tokens do LLM (D12)**
- Testes nunca chamam o LLM real: use LLM falso. Não remova a trava de rede de `tests/conftest.py`.
- Desenvolvimento usa `LLM_MODEL` (`gpt-oss-20b`). O `gpt-oss-120b` (`LLM_MODEL_OFICIAL`) é só para
  rodadas oficiais (`run_eval.py --oficial`) e o teste final, e só quando o usuário pedir.
- Mantenha `LLM_CACHE_PATH` ligado: a mesma chamada nunca vai ao provedor duas vezes. Rodar sem cache
  (medir variação) também exige pedido do usuário.
- Ao diagnosticar chamadas autenticadas, imprima só o tipo da exceção e o status HTTP, nunca `str(e)`.

**Dados brutos**
- Os CSVs ficam em `data/raw/` e **nunca** são commitados. Também nunca commite `.env`.
- Prefixos de CEP são **texto** (zero à esquerda, ex.: `"09790"`): leia com `dtype=str`.
- Leia CSVs com `encoding="utf-8-sig"` (a tradução de categorias tem BOM).
- `review_id` não é único: use `review_row_id`.

## Base de conhecimento

- Os YAML em `knowledge_base/` são a **fonte única** das políticas. `docs/catalogo_politicas.md` é
  gerado; não edite à mão.
- IDs: `POL-XXX-000` para políticas, `POL-XXX-000-S00` para seções, `LEG-CDC-000` para lei. Chunk =
  `section_id@version`.
- Toda intenção usada em política precisa existir em `intents.yaml`, e o mapeamento é bidirecional.
  O carregador (`knowledge/loader.py`) recusa inconsistências. Se ele falhar, corrija os dados, não
  afrouxe a validação.
- Texto legal fica separado das regras fictícias, nunca no mesmo chunk. As políticas citam o artigo
  pelo ID em vez de parafrasear.
- Os textos do CDC foram conferidos com a fonte oficial. Se um texto legal mudar, ele volta para
  `verification_status: pendente` até nova conferência; `load_kb.py` recusa texto não verificado.
- Uma janela operacional de devolução nunca pode ser menor que os 7 dias legais. Casos duvidosos
  são **encaminhados para humano, nunca negados**.

## Estilo de código

- Python 3.12, ruff com linha de 110 caracteres, type hints, Pydantic v2 para entradas e saídas.
- Regras de negócio em funções puras e testáveis; I/O nas bordas (repositório, scripts, API).
- Ferramentas recebem o repositório como `Protocol` (`OrderRepository`), para os testes usarem fakes.
- Testes unitários não dependem de banco nem dos CSVs: use mini-datasets sintéticos. Todo bug
  encontrado com dados reais ganha um caso no teste correspondente.
- Comentários explicam o **porquê** (em geral um achado dos dados ou uma decisão D1–D8), não o quê.
- Scripts em `scripts/` são finos; a lógica vive em `src/commerceops/`.

## Documentação de referência

- `docs/01_politicas_v1.1.md`: decisões D1–D8 e formato dos cenários de avaliação.
- `docs/02_auditoria_dados.md`: achados dos dados e suas implicações.
- `docs/03_arquitetura.md`: decisões de stack (D9: LLM Groq via API compatível com OpenAI).
- `docs/04_seguranca.md`: controles de segurança (OWASP LLM, ASI e AST) com o teste de cada um.
  Todo controle novo entra nessa tabela com sua verificação.
- `reports/audit/audit.md`: números atuais da auditoria (gerado).
- `reports/eval/`: resultados de avaliação (gerados). Todo número citado vem de um arquivo daqui.

Se uma mudança contrariar uma dessas decisões, registre a nova decisão no documento correspondente
na mesma mudança.
