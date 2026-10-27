# Dados brutos (não versionados)

Baixe o **Brazilian E-Commerce Public Dataset by Olist** em
<https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce> e extraia os 9 CSVs nesta pasta.

```bash
# com a CLI do Kaggle configurada
kaggle datasets download -d olistbr/brazilian-ecommerce -p data/raw --unzip
```

Confira com `python scripts/audit_dataset.py`: os totais devem bater com `reports/audit/audit.md`
(99.441 pedidos, 99.224 avaliações). `olist_geolocation_dataset.csv` é opcional.

Licença: CC BY-NC-SA 4.0, conforme a página do dataset. Os CSVs não são redistribuídos neste repositório.
