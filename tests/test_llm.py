import socket

import httpx
import pytest
from openai import APIConnectionError, OpenAI

from commerceops.config import Settings
from commerceops.llm import ResponseCache, cached, make_chat

MSGS = [{"role": "user", "content": "oi"}]


class CountingChat:
    def __init__(self, fail_first: bool = False):
        self.calls, self.fail_first = 0, fail_first

    def __call__(self, messages, *, json_mode, name):
        self.calls += 1
        if self.fail_first and self.calls == 1:
            raise APIConnectionError(request=httpx.Request("POST", "https://llm.invalid"))
        return f"resposta {self.calls}"


@pytest.fixture
def cache(tmp_path):
    return ResponseCache(str(tmp_path / "llm.sqlite"))


# ---------------------------------------------------------------- cuidado 2: cache


def test_mesma_chamada_nunca_vai_duas_vezes_ao_provedor(cache):
    inner = CountingChat()
    chat = cached(inner, cache, "openai/gpt-oss-20b")
    first = chat(MSGS, json_mode=False, name="redigir")
    assert chat(MSGS, json_mode=False, name="outro-nome-de-span") == first
    assert inner.calls == 1


@pytest.mark.parametrize(
    ("messages", "json_mode", "model"),
    [
        ([{"role": "user", "content": "outra"}], False, "openai/gpt-oss-20b"),
        (MSGS, True, "openai/gpt-oss-20b"),
        (MSGS, False, "openai/gpt-oss-120b"),
    ],
)
def test_requisicao_diferente_nao_reaproveita_resposta(cache, messages, json_mode, model):
    inner = CountingChat()
    cached(inner, cache, "openai/gpt-oss-20b")(MSGS, json_mode=False, name="x")
    cached(inner, cache, model)(messages, json_mode=json_mode, name="x")
    assert inner.calls == 2


def test_cache_persiste_entre_processos(tmp_path):
    path = str(tmp_path / "llm.sqlite")
    inner = CountingChat()
    cached(inner, ResponseCache(path), "m")(MSGS, json_mode=False, name="x")
    assert cached(inner, ResponseCache(path), "m")(MSGS, json_mode=False, name="x") == "resposta 1"
    assert inner.calls == 1


def test_erro_do_provedor_nao_entra_no_cache(cache):
    inner = CountingChat(fail_first=True)
    chat = cached(inner, cache, "m")
    with pytest.raises(APIConnectionError):
        chat(MSGS, json_mode=False, name="x")
    assert chat(MSGS, json_mode=False, name="x") == "resposta 2"


def test_sem_caminho_de_cache_nao_ha_cache():
    s = Settings(llm_base_url="http://127.0.0.1:9/v1", llm_api_key="k", llm_model="m")
    assert s.llm_cache_path is None and make_chat(s) is not None


# ---------------------------------------------------------------- cuidado 1: testes sem LLM real


def test_testes_rodam_sem_credenciais_de_llm():
    s = Settings()
    assert s.llm_api_key is None and s.llm_base_url is None and not s.langfuse_enabled
    assert make_chat(s) is None


def test_rede_externa_bloqueada_nos_testes():
    with pytest.raises(ConnectionRefusedError, match="rede externa"), socket.socket() as sock:
        sock.connect(("1.1.1.1", 443))


def test_chamada_ao_groq_falha_sem_gastar_tokens():
    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key="gsk_falsa", max_retries=0, timeout=5)
    with pytest.raises(APIConnectionError):
        client.chat.completions.create(model="openai/gpt-oss-20b", messages=MSGS)
