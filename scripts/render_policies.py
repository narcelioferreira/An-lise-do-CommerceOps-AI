"""Gera docs/catalogo_politicas.md a partir dos YAML de knowledge_base/.

Os YAML são a fonte única; o catálogo é só uma visão de leitura e não deve ser editado à mão.
Uso: python scripts/render_policies.py [--check]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from commerceops.knowledge.loader import load_knowledge_base  # noqa: E402

OUT = ROOT / "docs" / "catalogo_politicas.md"
ESCALATION_LABEL = {"none": "não", "conditional": "condicional", "required": "obrigatório"}


def render() -> str:
    kb = load_knowledge_base()
    t = kb.taxonomy
    lines = [
        "<!-- Arquivo gerado por scripts/render_policies.py. Não editar à mão. -->",
        "",
        "# Catálogo de políticas e fontes legais",
        "",
        "> **Políticas fictícias.** As políticas `POL-*` foram escritas para um ambiente de simulação "
        "e não representam regras da Olist nem de qualquer empresa real. Os artigos `LEG-CDC-*` são "
        "transcrições do Código de Defesa do Consumidor.",
        "",
        f"Taxonomia v{t.version}: {len(t.intents)} intenções, {len(kb.policies)} políticas, "
        f"{len(kb.legal.articles)} artigos de lei, {len(kb.chunks())} chunks indexáveis.",
        "",
        "## Intenções e políticas",
        "",
        "| Intenção | Grupo | Políticas |",
        "|---|---|---|",
    ]
    for i in t.intents:
        lines.append(f"| `{i.id}` | {i.group} | {', '.join(i.policies) or '—'} |")
    lines += [
        "",
        f"Políticas transversais (valem para todas as intenções): {', '.join(t.cross_cutting_policies)}.",
        "",
    ]

    for p in kb.policies.values():
        lines += [f"## {p.policy_id} — {p.title}", ""]
        lines.append(f"Intenções: {', '.join(f'`{i}`' for i in p.intents) or 'transversal'}")
        if p.related:
            lines.append(f" · Relacionadas: {', '.join(p.related)}")
        lines.append("")
        for v in p.versions:
            until = v.effective_until.isoformat() if v.effective_until else "em vigor"
            lines += [f"### Versão {v.version} ({v.effective_from.isoformat()} → {until})", ""]
            for s in v.sections:
                lines.append(
                    f"**{s.section_id} — {s.title}** (encaminhamento: {ESCALATION_LABEL[s.escalation]})"
                )
                lines += ["", s.text, ""]
                if s.requires_order_data:
                    fields = ", ".join(f"`{f}`" for f in s.requires_order_data)
                    lines += [f"_Dados exigidos:_ {fields}", ""]

    lines += ["## Fontes legais", "", f"{kb.legal.law} — <{kb.legal.official_url}>", ""]
    for a in kb.legal.articles:
        status = "✅ verificado" if a.verification_status == "verificado" else "⚠️ pendente de conferência"
        lines += [f"### {a.legal_id} — {a.article} ({status})", "", a.text, ""]
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="falha se o catálogo estiver desatualizado")
    args = ap.parse_args()
    content = render()
    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != content:
            print("docs/catalogo_politicas.md desatualizado: rode scripts/render_policies.py")
            return 1
        return 0
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(content, encoding="utf-8")
    print(f"gerado {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
