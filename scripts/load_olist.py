"""Carrega os CSVs do Olist no schema `olist` (idempotente: esvazia e recarrega).

Uso: ADMIN_DATABASE_URL=postgresql://... python scripts/load_olist.py [--raw-dir data/raw]

Usa o superusuário: a aplicação só tem SELECT em `olist`.
Tratamentos aplicados (ver docs/02_auditoria_dados.md):
- prefixos de CEP lidos como texto (o CSV tem zero à esquerda);
- BOM removido com utf-8-sig;
- review_creation_date truncado para data (resíduo de fuso às 01:00);
- review_row_id como chave técnica e flag de review_id duplicado;
- colunas "lenght" do CSV renomeadas para "length".
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commerceops.data.load import load, prepare  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-dir", type=Path, default=ROOT / "data" / "raw")
    args = ap.parse_args()
    url = os.environ.get("ADMIN_DATABASE_URL")
    if not url:
        print("defina ADMIN_DATABASE_URL", file=sys.stderr)
        return 2
    frames = prepare(args.raw_dir)
    with psycopg.connect(url) as conn:
        load(conn, frames)
        conn.execute("ANALYZE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
