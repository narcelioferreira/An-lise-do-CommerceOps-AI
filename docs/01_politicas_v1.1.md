# Pacote de políticas — v1.1

**Status:** políticas fictícias para simulação. Não representam a política real da Olist nem devem
ser apresentadas como documento jurídico ou operacional de empresa real.

Este documento registra **as decisões** da v1.1. O texto das políticas não está aqui: ele fica nos
arquivos YAML de `knowledge_base/`, que são a fonte única. A versão legível é gerada em
[`catalogo_politicas.md`](catalogo_politicas.md) por `scripts/render_policies.py`.

| Onde | O quê |
|---|---|
| `knowledge_base/intents.yaml` | Taxonomia de intenções, marcações derivadas e sentimentos |
| `knowledge_base/policies/POL-*.yaml` | Uma política por arquivo, com versões e seções |
| `knowledge_base/legal/cdc.yaml` | Artigos do CDC, separados das regras fictícias |
| `src/commerceops/knowledge/` | Modelos Pydantic e validação cruzada entre os arquivos |
| `src/commerceops/domain/orders.py` | Estágio do pedido e cálculo de atraso (determinísticos) |

## 1. O que mudou em relação à v1.0

| Problema na v1.0 | Correção na v1.1 |
|---|---|
| Dois sistemas de IDs (`POL-001` e `POL-ENT-001`); `POL-ENT-003` citado sem existir | IDs semânticos únicos; o carregador recusa referência a ID inexistente |
| Políticas usavam intenções fora da taxonomia (`extravio`, `garantia`, `valor_cobrado`…) | Mapeamento bidirecional intenção ↔ política, validado em teste |
| `cobranca_pagamento` sem política | Nova **POL-PAG-001** |
| `escalonamento` e `entrega_atrasada_grave` tratados como intenção | Viraram política transversal (**POL-SLA-002**) e marcação derivada |
| `rastrear_pedido` separado de `consultar_prazo` | Fundidos: o dataset não tem eventos de rastreamento, então a diferença não é observável |
| `outro_ou_ambíguo` com acento | Identificadores sempre em ASCII |
| Dias úteis sem calendário definido | **Dias corridos** em todas as regras (decisão D1) |
| Vigência em 2026 para pedidos de 2016–2018 | Vigência na linha do tempo simulada (decisão D3) |
| Defeito sem base legal própria | **LEG-CDC-018** e **LEG-CDC-026** |
| Devolução sem regra após o fim da janela | Três faixas: legal, operacional e revisão humana |
| Caso de teste "duas versões" sem segunda versão | **POL-DEV-001** v1.0 (30 dias) e v1.1 (15 dias) |
| Verificação de identidade inexistente | Nova **POL-SEG-001** |
| Regras citando dados ausentes (rastreio, endereço, status de reembolso) | Regras reescritas sobre campos reais; o que não existe vem do schema `sim` (decisão D6) |

## 2. Decisões

**D1 — Dias corridos.** Todos os prazos são contados em dias corridos. O dataset não traz calendário
de feriados, e `order_estimated_delivery_date` é uma data corrida. Dias úteis ficam como extensão
documentada, se um dia forem necessários.

**D2 — Comparação por data, não por timestamp.** A previsão de entrega é sempre meia-noite, e
`review_creation_date` só tem data (com resíduo de horário de verão em 85 linhas). Atrasos e janelas
comparam datas de calendário. É por isso que a auditoria v2 recalcula por data os números do parecer.

**D3 — Vigência na linha do tempo simulada.** As políticas têm datas de vigência entre 2016 e 2018
para conversar com os pedidos históricos. Foram escritas em 2026, e isso está declarado aqui. A
versão aplicável é a **vigente na data da compra** (`order_purchase_timestamp`): o cliente segue as
regras em vigor quando comprou.

**D4 — `reference_date` por cenário.** O agente nunca usa o relógio do sistema. Cada cenário de
avaliação define a data de "hoje", o que torna os casos determinísticos e reproduzíveis. Sem isso,
todo pedido estaria atrasado ou com janela vencida há oito anos.

**D5 — Estágio do pedido calculado em código.** O estágio sai do status **e** das datas:

| Estágio | Regra | Pedidos no dataset |
|---|---|---|
| `entregue` | `delivered` com data de entrega ao cliente | 96.470 |
| `em_transito` | `shipped` com data de despacho e sem data de entrega | 1.107 |
| `pre_envio` | `created`, `approved`, `processing` ou `invoiced`, sem datas de envio | 622 |
| `cancelado` | `canceled` sem data de entrega | 619 |
| `indisponivel` | `unavailable` sem datas de envio | 609 |
| `inconsistente` | status e datas se contradizem | **14** |

Os 14 inconsistentes (8 `delivered` sem data de entrega e 6 `canceled` com data de entrega) são
casos de teste: o agente deve encaminhar, nunca concluir.

**D6 — Dois schemas: `olist` (real, somente leitura) e `sim` (simulado).** Ocorrências, solicitações
de cancelamento, devoluções e reembolsos não existem no dataset. Ficam no schema `sim`, onde o agente
pode escrever. A separação física deixa explícito o que é dado real e o que é simulação.

**D7 — Identidade.** O cliente se identifica com `order_id` e os cinco primeiros dígitos do CEP.
O acesso é limitado ao `customer_unique_id` dele. `customer_id` **não** identifica cliente: é único
por pedido (99.441 para 99.441 pedidos). A checagem fica na ferramenta, nunca no prompt.

**D8 — Limiar de valor alto ancorado nos dados.** Reembolso acima de R$ 1.000,00 exige aprovação
humana. O valor corresponde a cerca do p99 de `payment_value` (R$ 1.039,92), ou seja, aciona
para ~1% dos pagamentos.

## 3. Tratamento do texto legal

Os artigos do CDC ficam em arquivo próprio, com `source_type: legal_public_source`, e nunca no mesmo
chunk de uma regra fictícia. As políticas citam o artigo pelo ID (`LEG-CDC-049`) em vez de
parafraseá-lo.

Os três artigos foram conferidos com a [fonte oficial](https://www.planalto.gov.br/ccivil_03/leis/l8078compilado.htm)
em 2026-10-26 e estão como `verification_status: verificado`. O texto é literal, inclusive "com a
indicações" no art. 18, que está assim na lei. Com `strict_legal=True`, o carregador recusa texto
não verificado.

## 4. Formato dos cenários de avaliação

Todo cenário é **simulado** e deve dizer isso no próprio registro. Os cenários ficam em
`evals/scenarios.yaml`, validados por `commerceops.evaluation.Scenario`. Os campos são:

```yaml
scenario_id: ENT-002-entregue-mas-nao-recebido-01
simulated: true
inspired_by_review_row_id: 18234   # opcional; nunca o texto original com identificadores
reference_date: 2018-03-14         # D4
order_id: <pedido real do dataset>
zip_prefix: "01310"                # verificação de identidade (POL-SEG-001)
customer_message: "Consta como entregue mas não recebi nada."
expected_intent: pedido_nao_recebido
expected_sentiment: negativo
expected_policy_ids: [POL-ENT-002]
expected_chunk_ids: [POL-ENT-002-S02@1.0]
expected_actions: ["ocorrencia:investigacao_entrega"]   # escritas em sim; [] = nenhuma
must_escalate: true
must_not_say: ["foi entregue", "reembolso aprovado"]
```

Casos-limite obrigatórios, além dos oito do pacote v1.0:
- compra em 2017-12-20, entrega em 2018-01-05 e solicitação em 2018-01-25: devolução **dentro** da janela (vale a v1.0);
- devolução no 5º dia: deve citar **LEG-CDC-049**, não só a regra fictícia;
- devolução após o fim da janela: encaminhar, **nunca** negar;
- pedido `inconsistente`: encaminhar sem afirmar o estágio;
- pedido de outro cliente com CEP errado: recusar, sem vazar nenhum dado;
- pedido pago com voucher + cartão: reembolso proporcional por meio.

## 5. Pendências

- [x] Conferir os textos do CDC com a fonte oficial (2026-10-26).
- [ ] Rotular a amostra estratificada e revisar a taxonomia (pode haver fusão ou divisão de classes).
- [ ] Medir a concordância entre anotadores; pode ser intra-anotador, se o trabalho for individual.
- [x] Escrever os cenários de avaliação no formato da seção 4 (`evals/scenarios.yaml`, 24 cenários).
