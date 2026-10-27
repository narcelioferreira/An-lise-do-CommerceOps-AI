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
