"""Carrega a base de conhecimento do disco e valida a coerência entre seus arquivos."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from commerceops.knowledge.models import Chunk, LegalSource, Policy, Taxonomy

REF_RE = re.compile(r"\b(POL-[A-Z]{3}-\d{3}|LEG-CDC-\d{3})\b")
# Em desenvolvimento, a pasta do repositório; na imagem Docker, KB_DIR=/app/knowledge_base.
DEFAULT_KB_DIR = Path(os.environ.get("KB_DIR", Path(__file__).resolve().parents[3] / "knowledge_base"))


class KnowledgeBaseError(ValueError):
    pass


@dataclass(frozen=True)
class KnowledgeBase:
    taxonomy: Taxonomy
    policies: dict[str, Policy]
    legal: LegalSource

    @property
    def legal_ids(self) -> set[str]:
        return {a.legal_id for a in self.legal.articles}

    def chunks(self) -> list[Chunk]:
        """Todas as seções de todas as versões, mais os artigos de lei, prontas para indexação."""
        out: list[Chunk] = []
        for p in self.policies.values():
            for v in p.versions:
                for s in v.sections:
                    out.append(
                        Chunk(
                            chunk_id=f"{s.section_id}@{v.version}",
                            doc_id=p.policy_id,
                            version=v.version,
                            source_type="fictional_policy",
                            fictional=True,
                            title=f"{p.title} — {s.title}",
                            effective_from=v.effective_from,
                            effective_until=v.effective_until,
                            intents=p.intents,
                            escalation=s.escalation,
                            text=s.text,
                        )
                    )
        for a in self.legal.articles:
            out.append(
                Chunk(
                    chunk_id=a.legal_id,
                    doc_id=a.legal_id,
                    version=None,
                    source_type="legal_public_source",
                    fictional=False,
                    title=f"CDC {a.article} — {a.topic}",
                    effective_from=None,
                    effective_until=None,
                    intents=[],
                    escalation="none",
                    text=a.text,
                )
            )
        return out


def _read_yaml(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_knowledge_base(kb_dir: Path = DEFAULT_KB_DIR, *, strict_legal: bool = False) -> KnowledgeBase:
    taxonomy = Taxonomy.model_validate(_read_yaml(kb_dir / "intents.yaml"))
    policies: dict[str, Policy] = {}
    for path in sorted((kb_dir / "policies").glob("*.yaml")):
        p = Policy.model_validate(_read_yaml(path))
        if path.stem != p.policy_id:
            raise KnowledgeBaseError(f"{path.name}: nome do arquivo difere de {p.policy_id}")
        policies[p.policy_id] = p
    legal = LegalSource.model_validate(_read_yaml(kb_dir / "legal" / "cdc.yaml"))
    kb = KnowledgeBase(taxonomy=taxonomy, policies=policies, legal=legal)
    errors = validate_consistency(kb)
    if strict_legal:
        errors += [
            f"{a.legal_id}: texto legal ainda não verificado com a fonte oficial"
            for a in legal.articles
            if a.verification_status != "verificado"
        ]
    if errors:
        raise KnowledgeBaseError("base de conhecimento inconsistente:\n- " + "\n- ".join(errors))
    return kb


def validate_consistency(kb: KnowledgeBase) -> list[str]:
    """Regras que cruzam arquivos. Retorna a lista de problemas (vazia = coerente)."""
    errors: list[str] = []
    known_ids = set(kb.policies) | kb.legal_ids
    intent_ids = kb.taxonomy.intent_ids

    for intent in kb.taxonomy.intents:
        for pid in intent.policies:
            if pid not in kb.policies:
                errors.append(f"intenção {intent.id} aponta para política inexistente {pid}")
            elif intent.id not in kb.policies[pid].intents:
                errors.append(f"{pid} não lista a intenção {intent.id}, mas a taxonomia aponta para ela")

    for pid in kb.taxonomy.cross_cutting_policies:
        if pid not in kb.policies:
            errors.append(f"política transversal inexistente: {pid}")

    for p in kb.policies.values():
        for intent in p.intents:
            if intent not in intent_ids:
                errors.append(f"{p.policy_id} usa intenção fora da taxonomia: {intent}")
            elif p.policy_id not in next(i for i in kb.taxonomy.intents if i.id == intent).policies:
                errors.append(f"taxonomia não liga {intent} a {p.policy_id}")
        if not p.intents and p.policy_id not in kb.taxonomy.cross_cutting_policies:
            errors.append(f"{p.policy_id} não tem intenções nem é transversal")
        for ref in p.related:
            if ref not in known_ids:
                errors.append(f"{p.policy_id}.related cita {ref}, que não existe")
        for v in p.versions:
            for s in v.sections:
                for ref in REF_RE.findall(s.text):
                    if ref not in known_ids:
                        errors.append(f"{s.section_id}@{v.version} cita {ref}, que não existe")

    for a in kb.legal.articles:
        for pid in a.related_policies:
            if pid not in kb.policies:
                errors.append(f"{a.legal_id} relaciona política inexistente {pid}")

    return errors
