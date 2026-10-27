# Segurança: controles e evidências

Cada controle aponta para o código e para o teste que o verifica. Referências:

- **LLM** — [OWASP Top 10 for LLM Applications 2026](https://genai.owasp.org/home/resources/owasp-genai-llm-top-10-2026/)
- **ASI** — [OWASP Top 10 for Agentic Applications 2026](https://genai.owasp.org/)
- **AST** — [OWASP Agentic Skills Top 10 (1.0-2026)](https://owasp.github.io/www-project-agentic-skills-top-10/)

Os nomes dos riscos são citados no lugar dos números do LLM Top 10 2026, porque a edição 2026
reordenou a lista.

## Princípio de projeto

O LLM **não tem ferramentas**. Ele classifica a intenção (saída restrita à taxonomia) e redige a
resposta a partir de fatos e de uma decisão já calculados em código. Consultas, autorização,
decisões e escritas no banco são código determinístico. Isso elimina por construção a maior parte
de *excessive agency*, *tool misuse* (ASI02) e *goal hijack* (ASI01): uma injeção de prompt pode, no
máximo, piorar o texto da resposta, e o texto passa por validação antes de sair.

## Cadeia de suprimentos e infraestrutura

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| AST02, AST07, ASI04, Supply chain | Dependências travadas com hashes; instalação só com `--locked` | `uv.lock`, `Dockerfile`, CI | CI falha se o lock divergir |
| AST02, AST07 | Actions fixadas por SHA; imagens por digest; Dependabot semanal | `.github/`, `Dockerfile`, `docker-compose.yml` | revisão do PR do Dependabot |
| Supply chain | Vulnerabilidades conhecidas nas dependências | CI: `pip-audit` | job `unit` |
| LLM02 | Varredura de segredos no histórico | CI: gitleaks | job `secrets` |
| ASI05 | Regras do bandit no lint; SQL sempre parametrizado ou com `psycopg.sql.Identifier` | `pyproject.toml`, `db.py`, `data/load.py`, `knowledge/store.py` | `ruff check` |
| AST06 | Contêiner sem root, somente leitura, sem capabilities, `no-new-privileges`; contexto de build mínimo | `Dockerfile`, `.dockerignore`, `docker-compose.yml` | smoke test da imagem |
| AST04 | YAML só com `safe_load`; modelos Pydantic com `extra="forbid"` | `knowledge/loader.py`, `knowledge/models.py` | `test_recusa_tag_yaml_executavel`, `test_recusa_campo_desconhecido_no_yaml` |

## Dados e privacidade

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| LLM02 | `order_id` só como HMAC em traces e na trilha de auditoria | `observability.hash_id`, `tools/orders.py` | `test_order_id_nunca_registrado_cru`, `test_acoes_ficam_registradas_sem_id_cru` |
| LLM02 | Mascaramento de IDs, e-mail, CPF, CEP, telefone e cartão em todo dado enviado ao Langfuse, inclusive objetos Pydantic e dataclasses capturados por `@observe` (falha encontrada num trace real em 27/10/2026) | `observability.mask_pii` | `tests/test_observability.py`, conferência de trace real no Langfuse |
| LLM02, ASI03 | Identidade por pedido + CEP; acesso só ao próprio `customer_unique_id`; resposta única para falhas | `tools/orders.py` | `test_verificacao_falha_com_mensagem_unica`, `test_cliente_nao_acessa_pedido_de_outro` |
| ASI03 | Usuário de banco com privilégio mínimo (`olist` e `kb` só leitura, `sim` sem `DELETE`) | `db/init/02_app_role.sh` | `test_usuario_da_aplicacao_tem_privilegio_minimo` |

## API

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| Superfície exposta | `/docs` e `/openapi.json` desligados em produção; sem cabeçalho `server` | `api/main.py`, `Dockerfile` | smoke test da imagem |
| Vazamento em cache/navegador | `nosniff`, `X-Frame-Options: DENY`, `no-referrer`, `Cache-Control: no-store` | `api/main.py` | `test_respostas_tem_cabecalhos_de_seguranca` |
| ASI08 | LLM e Langfuse fora das probes; falha do Langfuse não derruba o atendimento | `api/main.py`, `observability.py` | `test_health` |

## Base de conhecimento e RAG

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| Misinformation | Texto legal conferido com a fonte oficial; indexação recusa texto não verificado | `legal/cdc.yaml`, `scripts/load_kb.py` | `test_textos_legais_conferidos_com_a_fonte_oficial`, `test_modo_estrito_recusa_texto_legal_nao_verificado` |
| Vector and embedding weaknesses, ASI06 | `kb` é somente leitura para a aplicação; chunks só nascem de YAML validado | `02_app_role.sh`, `knowledge/loader.py` | `test_usuario_da_aplicacao_tem_privilegio_minimo` |
| Vector and embedding weaknesses | Filtro por metadados no banco: só a versão vigente na data da compra e, quando informado, só as políticas da intenção | `db.PostgresKnowledgeRepository` | `test_busca_so_devolve_a_versao_vigente_na_compra`, `test_filtro_de_intencao_mantem_transversais_e_lei` |
| Misinformation | Lei e regra fictícia em chunks separados, com `source_type` e `fictional` | `knowledge/loader.py` | `test_texto_legal_nunca_marcado_como_ficticio` |

## Decisão e ações

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| Excessive agency, ASI02 | Decisão e ações em código; o LLM não escolhe nem chama ação | `domain/decisions.py`, `tools/actions.py` | `tests/test_decisions.py` |
| ASI03 | Toda escrita em `sim` confere a posse do pedido no próprio SQL (`WITH owned`) | `db.py` | `test_escrita_em_sim_exige_posse_do_pedido`, `test_sem_posse_registra_recusa_e_interrompe` |
| ASI01, ASI09 | Encaminhamento monotônico: sinais de risco só aumentam a proteção; nada é negado automaticamente | `domain/decisions.py` | `test_sinal_nunca_reduz_encaminhamento`, `test_mesmo_prazo_com_compra_em_2018_vai_para_humano_sem_negar` |
| Unbounded consumption | Escritas idempotentes (índices únicos parciais): repetir a mensagem não multiplica registros | `01_schema.sql` | `test_ocorrencia_idempotente_e_encaminhamento_so_sobe`, `test_solicitacoes_idempotentes` |
| AST09 | Toda ação, permitida ou recusada, fica em `sim.agent_actions` com HMAC do pedido | `tools/actions.py` | `test_executa_ocorrencia_e_devolucao_na_data_de_referencia` |

## Agente e LLM

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| Prompt injection, ASI01 | LLM sem ferramentas; mensagem do cliente vai como dado JSON; regras explícitas no prompt | `agent.py` | `test_injecao_de_prompt_nao_passa_pelo_validador` |
| Misinformation, Improper output handling | Validador: política citada e do contexto, datas e valores só dos fatos, frases proibidas, sem IDs, encaminhamento informado; reprovou → resposta-modelo | `agent.validate`, `agent.fallback` | `test_validador_recusa`, `test_resposta_modelo_sempre_passa_no_validador` |
| Excessive agency, ASI02 | Saída do classificador validada contra a taxonomia; inválida ou com confiança < 0,5 vira `outro_ou_ambiguo`, que não age | `agent.classify` | `test_classificacao_invalida_vira_ambigua_e_nao_age` |
| ASI01, ASI09 | Sinais de risco por regra somados aos do LLM: o LLM não consegue evitar um encaminhamento | `agent.answer`, `domain/decisions.py` | `test_sinal_detectado_em_codigo_encaminha_mesmo_que_o_llm_omita` |
| LLM02, Hidden context exposure | Ao LLM só vão fatos mínimos (sem IDs de pedido, cliente ou vendedor); o prompt não tem segredo | `agent._facts` | `test_dados_enviados_ao_llm_sao_minimos` |
| ASI08 | Timeout e tentativas limitadas; LLM ou embeddings fora do ar degradam (resposta-modelo, busca lexical) em vez de derrubar | `llm.py`, `agent.py` | `test_llm_fora_do_ar_responde_com_modelo_seguro`, `test_sem_llm_configurado_ainda_responde` |
| ASI08, AST09 | Falha do LLM registrada em `llm_failures` e contada à parte na avaliação (`falha_de_infra`); diagnóstico fora da resposta da API | `agent.ChatResult`, `evaluation.score` | `test_falha_so_na_redacao_mantem_a_decisao_e_registra`, `test_falha_de_infra_nao_entra_nas_metricas_de_qualidade` |
| LLM02 | Espaços nas pontas de chaves e URLs removidos ao ler o ambiente (cabeçalho inválido falhava como "Connection error") | `config.Settings` | `test_remove_espacos_colados_em_chaves_e_urls` |
| ASI10 | Fluxo finito e sem laços; nenhuma nova tentativa automática da geração | `agent.py` (D10) | revisão de código |
| Unbounded consumption | Mensagem ≤ 1.000 caracteres, saída ≤ 2.048 tokens, 30 requisições/min por IP (inviabiliza testar CEPs em massa) | `agent.ChatRequest`, `llm.py`, `api/main.py` | `test_api_chat_recusa_entrada_fora_dos_limites`, `test_limite_de_requisicoes_por_ip` |
| ASI03 | Verificação de identidade antes de qualquer chamada ao LLM | `agent.answer` | `test_verificacao_falha_antes_de_chamar_o_llm` |
| AST09 | Intenção, sinais, políticas, confiança, encaminhamento e erros de validação no trace de toda resposta (POL-SLA-001-S03) | `agent.answer` | revisão no Langfuse |

## Kubernetes

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| AST06, ASI05 | Pod Security Admission `restricted`; sem root, FS somente leitura, `drop: [ALL]`, seccomp `RuntimeDefault`, sem token de service account | `k8s/base/deployment.yaml`, `k8s/overlays/*/namespace.yaml` | job `k8s` (kubeconform) e admissão do cluster |
| AST06, ASI08 | NetworkPolicy nega tudo; entrada só do gateway; saída só DNS, Postgres e HTTPS público | `k8s/base/networkpolicy.yaml` | job `k8s` |
| Unbounded consumption | `requests`/`limits` de CPU e memória; `/tmp` com teto; limite global de requisições no gateway | `k8s/base/` | job `k8s` |
| LLM02 | Segredos só em Secret criado fora do git; ConfigMap sem segredo | `k8s/base/kustomization.yaml` | gitleaks |
| ASI08 | Probes só em `/health/live` e `/health/ready`; LLM e Langfuse fora delas | `k8s/base/deployment.yaml` | revisão de código |

## Consumo do LLM (D12)

| Risco | Controle | Onde | Verificação |
|---|---|---|---|
| Unbounded consumption | Testes sem LLM real: credenciais descartadas e conexões fora do `localhost` bloqueadas | `tests/conftest.py` | `test_rede_externa_bloqueada_nos_testes`, `test_chamada_ao_groq_falha_sem_gastar_tokens` |
| Unbounded consumption | Cache persistente: a mesma chamada nunca vai ao provedor duas vezes; erros não entram | `llm.ResponseCache`, `llm.cached` | `tests/test_llm.py` |
| Unbounded consumption | Modelo grande só em rodada oficial (`--oficial`); desenvolvimento com o leve | `evaluation.eval_model`, `k8s/overlays/dev` | `test_modelo_oficial_so_com_flag` |
