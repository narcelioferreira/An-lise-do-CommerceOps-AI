# Auditoria dos dados — v2

Números completos em [`reports/audit/audit.md`](../reports/audit/audit.md), gerado por
`python scripts/audit_dataset.py`. Este documento registra **o que mudou** em relação ao parecer
original e **o que cada achado implica** para o projeto.

## 1. Reconciliação com o parecer original

| Número do parecer | Reproduzido na v2 | Situação |
|---|---|---|
| 99.441 pedidos, 99.224 avaliações | iguais | ✅ |
| 40.950 mensagens; 42.687 com título ou mensagem | iguais | ✅ |
| 814 linhas com `review_id` repetido; 789 IDs em pedidos diferentes | iguais | ✅ |
| 74 avaliações antes da compra; 64 por data | iguais | ✅ |
| 5.127 avaliações antes da entrega | **5.126** por data; 8.319 por timestamp | Diferença de 1 (borda de fuso) |
| 4.576 com texto antes da entrega | **3.232** por data; 4.575 por timestamp | ❌ O parecer usava timestamp aqui e data no total |
| 7.827 entregas atrasadas | **6.535 (6,8%)** por data | ❌ Timestamp contava entrega no dia previsto como atraso |
| 4.212 com atraso > 5 dias | **3.765 (3,9%)** por data | ❌ Mesmo motivo |

**Regra adotada (D2):** toda comparação temporal é feita entre **datas**. A auditoria mostra as duas
medidas lado a lado para que a diferença fique documentada.

## 2. Achados novos

| Achado | Número | Implicação |
|---|---|---|
| `customer_id` é único por pedido | 99.441 = 99.441 | Cliente real é `customer_unique_id` (96.096). Autorização usa esse campo |
| Clientes com mais de um pedido | 2.997 (máx. 17) | Regras de "cliente recorrente" serão cenário simulado |
| Resíduo de fuso em `review_creation_date` | 85 linhas às 01:00 | Tratar a coluna como `DATE` |
| Mensagens limitadas a ~200 caracteres | p99 = 200, máx. 208 | Limite do formulário de origem; comentários são curtos por construção |
| Bordas do período esparsas | 349 pedidos fora de jan/2017–ago/2018 | Janela analítica padrão: jan/2017–ago/2018 |
| Pedidos com status e datas contraditórios | 14 | Estágio `inconsistente`; casos de teste de encaminhamento |
| Despacho após o prazo do vendedor | 5.658 (5,8%) | Variável candidata para o modelo de risco de atraso |
| Pedidos sem itens | 775, sendo 603 `unavailable` e 164 `canceled` | Esperado: pedido indisponível nunca teve item faturado |
| Pagamento ≠ preço + frete (> R$ 1) | 249 de 98.665 | Juros de parcelamento e vouchers; não é erro por si só (POL-PAG-001-S02) |
| Pedidos com mais de um meio de pagamento | 2.246 | Cenário de reembolso proporcional (POL-REF-001-S02) |
| Categorias sem tradução | `pc_gamer`, `portateis_cozinha_e_preparadores_de_alimentos` | Manter o nome em português como fallback |
| BOM na tradução de categorias | 1 arquivo | Ler sempre com `utf-8-sig` |
| Geolocalização | 1.000.163 linhas para 19.015 prefixos | Agregar por prefixo antes de qualquer join; não usado na v1 |

## 3. Viés de amostragem dos comentários

| Nota | Com texto | Taxa |
|---|---|---|
| 1 | 8.829 | 77% |
| 2 | 2.165 | 69% |
| 3 | 3.643 | 45% |
| 4 | 6.274 | 33% |
| 5 | 21.776 | 38% |

Mais da metade dos comentários vem de nota 5. Uma amostra aleatória simples para rotulagem seria
dominada por `elogio_ou_satisfacao`. A amostra deve ser **estratificada por nota e por estágio do
pedido**, com reforço nos cerca de 1.900 comentários de pedidos não entregues.

## 4. O que a auditoria não prova

Os limites do parecer original continuam valendo: avaliação não é ticket; não há reembolso, devolução
nem SLA no dataset; a ordem temporal entre avaliação e entrega é incerta. A v2 só torna essas
incertezas **mensuráveis e reprodutíveis**.
