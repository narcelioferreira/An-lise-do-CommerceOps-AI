# Experimentos

Todo número aqui vem de um arquivo em `reports/eval/`, gerado por `scripts/run_eval.py` sobre os
24 cenários simulados de `evals/scenarios.yaml`. Resultados negativos ficam registrados como os
positivos.

## E1 — Busca: lexical × vetorial × híbrida

Fonte: [`retrieval-bge-m3-20261026-235001.json`](../reports/eval/retrieval-bge-m3-20261026-235001.json).
Consulta = mensagem do cliente, sem filtro de intenção; candidatos restritos à versão vigente na data
da compra; k = 5; 21 cenários com chunks esperados.

| Método | Recall@5 | MRR@5 |
|---|---|---|
| Lexical (`tsvector` português, termos com OU) | 0,667 | 0,444 |
| **Vetorial (bge-m3, cosseno)** | **0,810** | **0,613** |
| Híbrida (RRF, k = 60) | 0,762 | 0,571 |

**Leitura.** A vetorial foi a melhor nas duas métricas. A híbrida **não** superou a vetorial: a busca
lexical erra o suficiente para puxar a fusão para baixo. Com n = 21, a diferença de recall entre vetorial
e híbrida equivale a um cenário: é indício, não conclusão. Consequência: decisão D11.

**Limites.** Mensagens curtas e escritas por quem também escreveu as políticas; base com 46 chunks.
A ordem dos métodos pode mudar com mensagens reais de clientes ou com uma base maior.

## E2 — Decisão com intenção do gabarito

Fonte: [`oracle-intent-nenhum-20261026-235022.json`](../reports/eval/oracle-intent-nenhum-20261026-235022.json).
A intenção vem do gabarito; mede decisão, ações em `sim`, encaminhamento e recusa de acesso.

| Métrica | Resultado |
|---|---|
| Ações corretas, encaminhamento correto, recall de políticas | 23/23 |
| Acesso negado a CEP de outro cliente | 1/1 |
| Resposta do LLM validada | 0/23 (sem LLM nesta execução: toda resposta é a resposta-modelo) |

**Leitura.** Este resultado só mostra que regras e gabarito são **coerentes entre si**: os dois foram
escritos pela mesma pessoa. Não é medida independente de qualidade. Ele serve como teste de regressão
das decisões sobre pedidos reais (rodar de novo deu o mesmo resultado, com `sim` já populado, o que
confirma a idempotência).

## E3 — Agente completo e modelo grande × pequeno (roteiro, ainda não executado)

Exige chave do Groq. Mede o que E2 não mede: classificação da intenção e qualidade do texto.

```bash
# banco com o dataset real, base indexada com embeddings (E1)
LLM_MODEL=openai/gpt-oss-120b python scripts/run_eval.py
LLM_MODEL=openai/gpt-oss-20b  python scripts/run_eval.py
LLM_MODEL=llama-3.3-70b-versatile python scripts/run_eval.py   # outra família (D9)
```

Comparar `intencao_correta`, `resposta_validada`, `sem_frase_proibida` e, no Langfuse, latência e
tokens por cenário. Antes de concluir algo: rodar cada modelo mais de uma vez (o resultado do LLM
varia mesmo com temperatura 0) e revisar à mão as respostas recusadas pelo validador.
