from datetime import date, datetime

import pytest

from commerceops.domain.decisions import Decision
from commerceops.tools.actions import execute
from commerceops.tools.orders import OrderAccessDenied, VerifiedCustomer
from tests.test_decisions import delivered

U1 = VerifiedCustomer(customer_unique_id="u1")


class FakeRepo:
    def __init__(self, owner="u1"):
        self.owner, self.calls, self.actions = owner, [], []

    def _ok(self, name, cid, *args):
        self.calls.append((name, cid, *args))
        return 7 if cid == self.owner else None

    def open_ticket(self, cid, oid, ttype, escalated, policies, at, scenario):
        return self._ok("ticket", cid, ttype, escalated, policies, at)

    def request_cancellation(self, cid, oid, at):
        return self._ok("cancelamento", cid)

    def request_return(self, cid, oid, reason, legal, version, at):
        return self._ok("devolucao", cid, reason, legal, version)

    def record_action(self, tool, oid_hash, allowed, reason):
        self.actions.append((tool, oid_hash, allowed))


def test_executa_ocorrencia_e_devolucao_na_data_de_referencia():
    repo = FakeRepo()
    d = Decision(("POL-DEV-001-S03@1.1",), (), True, "outro", "devolucao", "arrependimento", None, "1.1")
    out = execute(repo, U1, delivered(3), d, hmac_key="k")
    assert (out.ticket_id, out.request_id) == (7, 7)
    assert repo.calls[0] == ("ticket", "u1", "outro", True, ["POL-DEV-001"], datetime(2018, 3, 1))
    assert repo.calls[1] == ("devolucao", "u1", "arrependimento", None, "1.1")
    assert all(a[2] for a in repo.actions) and "a" * 32 not in str(repo.actions)


def test_decisao_sem_acao_nao_escreve():
    repo = FakeRepo()
    assert execute(repo, U1, delivered(3), Decision((), ()), hmac_key="k").ticket_id is None
    assert repo.calls == [] and repo.actions == []


def test_sem_posse_registra_recusa_e_interrompe():
    repo = FakeRepo(owner="outro")
    with pytest.raises(OrderAccessDenied):
        execute(repo, U1, delivered(3), Decision((), (), True, "outro", "cancelamento"), hmac_key="k")
    assert repo.actions == [("open_ticket", repo.actions[0][1], False)]
    assert len(repo.calls) == 1  # parou antes do cancelamento


def test_data_de_referencia_nunca_e_o_relogio():
    repo = FakeRepo()
    execute(repo, U1, delivered(3, ref=date(2017, 5, 2)), Decision((), (), False, "outro"), hmac_key="k")
    assert repo.calls[0][-1] == datetime(2017, 5, 2)
