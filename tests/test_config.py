from commerceops.config import Settings


def test_remove_espacos_colados_em_chaves_e_urls():
    s = Settings(
        database_url="postgresql://x@localhost/x ",
        order_id_hmac_key=" chave ",
        llm_api_key="gsk_teste   ",
        llm_base_url=" https://api.groq.com/openai/v1\t",
    )
    assert s.llm_api_key.get_secret_value() == "gsk_teste"
    assert s.order_id_hmac_key.get_secret_value() == "chave"
    assert s.llm_base_url == "https://api.groq.com/openai/v1"
