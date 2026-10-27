<!-- Gerado por scripts/audit_dataset.py. Não editar à mão. -->

# Auditoria do dataset Olist (v2.0)

## Arquivos

| Arquivo | Linhas | Colunas | BOM | Status |
|---|---|---|---|---|
| olist_customers_dataset.csv | 99.441 | 5 | não | ok |
| olist_geolocation_dataset.csv | 1.000.163 | 5 | não | ok |
| olist_order_items_dataset.csv | 112.650 | 7 | não | ok |
| olist_order_payments_dataset.csv | 103.886 | 5 | não | ok |
| olist_order_reviews_dataset.csv | 99.224 | 7 | não | ok |
| olist_orders_dataset.csv | 99.441 | 8 | não | ok |
| olist_products_dataset.csv | 32.951 | 9 | não | ok |
| olist_sellers_dataset.csv | 3.095 | 4 | não | ok |
| product_category_name_translation.csv | 71 | 2 | sim | ok |

## Pedidos

| Estágio calculado | Pedidos |
|---|---|
| entregue | 96.470 |
| em_transito | 1.107 |
| pre_envio | 622 |
| cancelado | 619 |
| indisponivel | 609 |
| inconsistente | 14 |

| Inconsistência | Pedidos |
|---|---|
| delivered sem data de entrega ao cliente | 8 |
| canceled com data de entrega ao cliente | 6 |

Janela analítica 2017-01-01 a 2018-08-31: 99.092 pedidos dentro, 349 fora.

| Mês da compra | Pedidos |
|---|---|
| 2016-09 | 4 |
| 2016-10 | 324 |
| 2016-12 | 1 |
| 2017-01 | 800 |
| 2017-02 | 1.780 |
| 2017-03 | 2.682 |
| 2017-04 | 2.404 |
| 2017-05 | 3.700 |
| 2017-06 | 3.245 |
| 2017-07 | 4.026 |
| 2017-08 | 4.331 |
| 2017-09 | 4.285 |
| 2017-10 | 4.631 |
| 2017-11 | 7.544 |
| 2017-12 | 5.673 |
| 2018-01 | 7.269 |
| 2018-02 | 6.728 |
| 2018-03 | 7.211 |
| 2018-04 | 6.939 |
| 2018-05 | 6.873 |
| 2018-06 | 6.167 |
| 2018-07 | 6.292 |
| 2018-08 | 6.512 |
| 2018-09 | 16 |
| 2018-10 | 4 |

## Clientes

| Métrica | Valor |
|---|---|
| customer_id_unique | 99.441 |
| customer_id_equals_orders | 1 |
| customer_unique_id | 96.096 |
| customers_with_gt1_order | 2.997 |
| max_orders_per_customer | 17 |

## Avaliações

| Métrica | Valor |
|---|---|
| rows | 99.224 |
| review_id_unique | 98.410 |
| review_id_duplicated_rows | 814 |
| review_id_in_gt1_order | 789 |
| with_message | 40.950 |
| with_title | 11.566 |
| with_title_or_message | 42.687 |

| Tamanho da mensagem (não vazia) | Caracteres |
|---|---|
| p50 | 53.00 |
| p90 | 160.00 |
| p99 | 200.00 |
| max | 208 |
| n | 40.950 |

| Horário em review_creation_date | Linhas |
|---|---|
| 00:00:00 | 99.139 |
| 01:00:00 | 85 |

| Nota | Com texto | Total | Taxa |
|---|---|---|---|
| 1 | 8.829 | 11.424 | 77.30% |
| 2 | 2.165 | 3.151 | 68.70% |
| 3 | 3.643 | 8.179 | 44.50% |
| 4 | 6.274 | 19.142 | 32.80% |
| 5 | 21.776 | 57.328 | 38.00% |

| Status do pedido | Avaliações com texto |
|---|---|
| delivered | 40.784 |
| shipped | 647 |
| unavailable | 418 |
| canceled | 412 |
| invoiced | 217 |
| processing | 207 |
| created | 2 |

## Avaliação × eventos do pedido

_by_date é a medida de referência; by_timestamp superestima porque a avaliação é sempre 00:00_

| Avaliações criadas… | Por timestamp | Por data |
|---|---|---|
| before_purchase | 74 | 64 |
| before_delivery | 8.319 | 5.126 |
| before_delivery_with_text | 4.575 | 3.232 |

## Entrega

_dias corridos, comparando datas (entrega normalizada × previsão)_

| Métrica | Todos | Janela analítica |
|---|---|---|
| n | 96.476 | 96.204 |
| late | 6.535 | 6.532 |
| late_rate | 6.77% | 6.79% |
| late_gt_5d | 3.765 | 3.763 |
| late_gt_5d_rate | 3.90% | 3.91% |

| Despacho × prazo do vendedor | Valor |
|---|---|
| orders_with_carrier_date | 97.657 |
| late_dispatch | 5.658 |
| rate | 5.79% |

## Itens e pagamentos

| Itens | Valor |
|---|---|
| rows | 112.650 |
| orders | 98.666 |
| orders_gt1_item | 9.803 |
| orders_gt1_seller | 1.278 |

| Pedido sem itens — status | Pedidos |
|---|---|
| unavailable | 603 |
| canceled | 164 |
| created | 5 |
| invoiced | 2 |
| shipped | 1 |

| Pagamentos | Valor |
|---|---|
| rows | 103.886 |
| orders | 99.440 |
| orders_without_payment | 1 |
| installments_zero | 2 |
| orders_gt1_payment_row | 2.961 |
| orders_gt1_payment_type | 2.246 |
| orders_paid_gt_1000 | 1.174 |

| Meio de pagamento | Registros |
|---|---|
| credit_card | 76.795 |
| boleto | 19.784 |
| voucher | 5.775 |
| debit_card | 1.529 |
| not_defined | 3 |

| payment_value | R$ |
|---|---|
| p50 | 100.00 |
| p90 | 297.27 |
| p99 | 1,039.92 |

_soma dos pagamentos − soma de preço+frete; diferença não implica erro (juros, voucher)_

| Pagamento × itens | Pedidos |
|---|---|
| orders_compared | 98.665 |
| abs_diff_gt_1_real | 249 |
| paid_more | 232 |
| paid_less | 17 |

## Catálogo

| Métrica | Valor |
|---|---|
| products | 32.951 |
| products_without_category | 610 |
| categories | 73 |
| categories_without_translation | pc_gamer, portateis_cozinha_e_preparadores_de_alimentos |
| sellers | 3.095 |
| items_with_unknown_seller | 0 |
| seller_state_top5 | SP, PR, MG, SC, RJ |

| Geolocalização | Valor |
|---|---|
| rows | 1.000.163 |
| zip_prefixes | 19.015 |
| rows_per_prefix_mean | 52.60 |
