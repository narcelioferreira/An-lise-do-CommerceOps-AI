# Arquitetura e decisões técnicas

Decisões de stack e infraestrutura. As decisões D1–D8, sobre dados e políticas, estão em
[`01_politicas_v1.1.md`](01_politicas_v1.1.md).

## D9 — LLM: Groq no plano gratuito, por meio de API compatível com OpenAI

**Decisão.** O provedor padrão é o Groq (plano gratuito), acessado pela API compatível com OpenAI
(`LLM_BASE_URL=https://api.groq.com/openai/v1`). Modelo, URL e chave vêm do ambiente
(`LLM_MODEL`, `LLM_BASE_URL`, `LLM_API_KEY`), nunca do código.

**Por quê.**
- Custo zero para desenvolver e avaliar, com modelos abertos de boa qualidade em português.
- Latência baixa, o que ajuda a rodar o conjunto de avaliação várias vezes.
- A mesma API serve o Ollama local (`http://localhost:11434/v1`), então trocar de provedor é só
  configuração. Isso sustenta o experimento "modelo maior × modelo pequeno" da etapa 6.

**Modelos (catálogo de produção do Groq consultado em 27/10/2026).**

| Papel | Modelo | Por quê |
|---|---|---|
| Agente (padrão) | `openai/gpt-oss-120b` | Bom em raciocínio e chamada de ferramentas; contexto de 131 mil tokens |
| Modelo pequeno (experimento da etapa 6) | `openai/gpt-oss-20b` | Mesma família do padrão: a comparação isola o efeito do tamanho |
| Alternativa a avaliar | `llama-3.3-70b-versatile` | Outra família, para checar se o resultado depende do fornecedor. **Indisponível na chave usada no E3 (27/10/2026)** |

Os modelos `llama-*` aparecem com preço "sob consulta" na tabela de produção; os limites do plano
gratuito devem ser conferidos no console antes de usá-los nas avaliações. A escolha do padrão é uma
hipótese: só vira conclusão depois de medida no conjunto de avaliação. **Medida no E3**
(`docs/05_experimentos.md`): o 120b teve todas as respostas aprovadas pelo validador (22/22); o 20b, 17/23.

**Consequências.**
- **Custo no Langfuse aparece como zero.** Para a métrica de custo fazer sentido, cadastrar no
  Langfuse preços de referência de modelos pagos equivalentes e reportar "custo estimado", sempre
  rotulado como estimativa.
- **Limites de requisição do plano gratuito.** As avaliações precisam de cache de respostas e
  execução em lotes, com nova tentativa em caso de limite atingido (HTTP 429).
- **O catálogo gratuito muda.** Todo experimento registra o identificador exato do modelo usado
  (`LLM_MODEL`) nos metadados do trace, para os resultados continuarem interpretáveis.
- **Privacidade.** Só trafegam dados do dataset público e anonimizado e mensagens simuladas.
- **Health check.** `/health/deep` consulta `GET {LLM_BASE_URL}/models`, que não consome tokens. O LLM
  nunca entra nas probes do Kubernetes.

## D10 — Fluxo do agente em Python, sem LangGraph, e LLM sem ferramentas

**Decisão.** O atendimento é uma sequência fixa de funções em `src/commerceops/agent.py`:
verificar identidade → consultar o pedido → classificar (LLM) → decidir (código) → executar (código)
→ montar contexto (busca) → redigir (LLM) → validar (código). O LLM não recebe ferramentas.

**Por quê.**
- O fluxo não tem laços nem bifurcações que mudem o caminho. LangGraph acrescentaria dependência e
  indireção sem mudar o comportamento. Cada passo já é um span do Langfuse (`@observe`).
- Sem ferramentas, uma injeção de prompt não consegue consultar, gravar nem decidir nada: no máximo
  estraga o texto, que passa pelo validador antes de sair (ver `docs/04_seguranca.md`).
- Decisões em código são testáveis caso a caso (`tests/test_decisions.py`) e reproduzíveis na avaliação.

**Quando rever.** Se surgirem conversas com vários turnos, laços de esclarecimento ou mais de um
agente, um orquestrador de grafo passa a se pagar.

## D11 — Contexto do agente pela busca vetorial

**Decisão.** Com embeddings configurados, o agente monta o contexto extra com a busca vetorial; sem
eles, com a lexical. A híbrida continua disponível em `Retriever.search` e nos experimentos.

**Por quê.** No experimento E1 (`docs/05_experimentos.md`), a vetorial teve Recall@5 0,81 e MRR@5 0,61
contra 0,76 e 0,57 da híbrida e 0,67 e 0,44 da lexical. A busca só acrescenta contexto: as seções que
fundamentam a decisão vêm do código, então a escolha não altera nenhuma decisão.

**Quando rever.** A amostra é pequena (21 cenários). Refazer E1 quando houver mais cenários ou
mensagens reais; se a híbrida empatar ou passar, ela é mais robusta a termos exatos.

## D12 — Economia de tokens: LLM falso nos testes, cache e modelo leve no desenvolvimento

**Decisão.**
1. **Testes nunca chamam o LLM real.** Usam LLM falso; o `tests/conftest.py` descarta `LLM_*`,
   `EMBEDDING_*` e `LANGFUSE_*` do ambiente e bloqueia qualquer conexão fora do `localhost`, então um
   teste que tente alcançar o Groq falha em vez de gastar tokens.
2. **Respostas reais ficam em cache** (`LLM_CACHE_PATH`, SQLite local): a chave é o hash de modelo,
   mensagens e parâmetros, e a mesma chamada nunca vai ao provedor duas vezes. Erros não entram.
3. **Desenvolvimento usa `openai/gpt-oss-20b`** (`LLM_MODEL`); o `openai/gpt-oss-120b`
   (`LLM_MODEL_OFICIAL`) fica para as rodadas oficiais de avaliação e o teste final. O
   `run_eval.py` recusa o modelo oficial sem `--oficial`.

**Por quê.** O plano gratuito do Groq limita tokens por minuto e requisições por dia (E3), e a cota é
compartilhada entre desenvolvimento e avaliação.

**Consequências.**
- Repetir uma rodada com cache devolve o mesmo resultado sem custo. Para medir a variação entre
  execuções, rode com `LLM_CACHE_PATH=` (vazio): é a única situação em que a mesma chamada se repete.
- O cache guarda o texto das respostas (dados simulados) em disco local, ignorado pelo git. Não é para
  produção: lá `LLM_CACHE_PATH` fica vazio, e o sistema de arquivos do contêiner é somente leitura.
- O overlay `dev` do Kubernetes usa o 20b; o `staging`, o oficial.
