window.LANGFUSE = {
  "rodadas": {
    "gpt-oss-120b": {
      "relatorio": "agente-openai_gpt-oss-120b-20261027-090833.json",
      "traces": 24,
      "ponta_a_ponta": {
        "mediana": 12.229500000000002,
        "p90": 20.29
      },
      "passos": {
        "verify_customer": {
          "n": 24,
          "mediana": 0.006,
          "p90": 0.011
        },
        "get_order_summary": {
          "n": 23,
          "mediana": 0.005,
          "p90": 0.011
        },
        "classificar": {
          "n": 23,
          "mediana": 7.155,
          "p90": 10.944
        },
        "contextualizar": {
          "n": 23,
          "mediana": 0.121,
          "p90": 0.209
        },
        "OpenAI-embedding": {
          "n": 23,
          "mediana": 0.114,
          "p90": 0.204
        },
        "redigir": {
          "n": 23,
          "mediana": 6.155,
          "p90": 12.358
        }
      },
      "fracao_llm": 0.989,
      "tokens": {
        "redigir": {
          "entrada": 839,
          "saida": 100,
          "raciocinio": 496
        },
        "classificar": {
          "entrada": 264,
          "saida": 33,
          "raciocinio": 99
        }
      }
    },
    "gpt-oss-20b": {
      "relatorio": "agente-openai_gpt-oss-20b-20261027-091345.json",
      "traces": 24,
      "ponta_a_ponta": {
        "mediana": 20.547,
        "p90": 30.396
      },
      "passos": {
        "verify_customer": {
          "n": 24,
          "mediana": 0.004,
          "p90": 0.006
        },
        "get_order_summary": {
          "n": 23,
          "mediana": 0.004,
          "p90": 0.006
        },
        "classificar": {
          "n": 23,
          "mediana": 7.767,
          "p90": 18.825
        },
        "contextualizar": {
          "n": 23,
          "mediana": 0.106,
          "p90": 0.136
        },
        "OpenAI-embedding": {
          "n": 23,
          "mediana": 0.1,
          "p90": 0.13
        },
        "redigir": {
          "n": 23,
          "mediana": 9.534,
          "p90": 17.516
        }
      },
      "fracao_llm": 0.9929,
      "tokens": {
        "redigir": {
          "entrada": 1018,
          "saida": 101,
          "raciocinio": 835
        },
        "classificar": {
          "entrada": 764,
          "saida": 33,
          "raciocinio": 166
        }
      }
    }
  },
  "exemplo": {
    "scenario_id": "ENT-003-atraso-grave-01",
    "passos": [
      {
        "nome": "atendimento",
        "tipo": "SPAN",
        "nivel": 0,
        "inicio": 0.0,
        "duracao": 3.622,
        "modelo": ""
      },
      {
        "nome": "verify_customer",
        "tipo": "TOOL",
        "nivel": 1,
        "inicio": 0.0,
        "duracao": 0.004,
        "modelo": ""
      },
      {
        "nome": "get_order_summary",
        "tipo": "TOOL",
        "nivel": 1,
        "inicio": 0.004,
        "duracao": 0.006,
        "modelo": ""
      },
      {
        "nome": "classificar",
        "tipo": "GENERATION",
        "nivel": 2,
        "inicio": 0.01,
        "duracao": 0.571,
        "modelo": "openai/gpt-oss-120b"
      },
      {
        "nome": "classificar",
        "tipo": "SPAN",
        "nivel": 1,
        "inicio": 0.01,
        "duracao": 0.572,
        "modelo": ""
      },
      {
        "nome": "contextualizar",
        "tipo": "SPAN",
        "nivel": 1,
        "inicio": 0.589,
        "duracao": 0.148,
        "modelo": ""
      },
      {
        "nome": "OpenAI-embedding",
        "tipo": "EMBEDDING",
        "nivel": 2,
        "inicio": 0.591,
        "duracao": 0.142,
        "modelo": "bge-m3"
      },
      {
        "nome": "redigir",
        "tipo": "SPAN",
        "nivel": 1,
        "inicio": 0.737,
        "duracao": 2.884,
        "modelo": ""
      },
      {
        "nome": "redigir",
        "tipo": "GENERATION",
        "nivel": 2,
        "inicio": 0.739,
        "duracao": 2.882,
        "modelo": "openai/gpt-oss-120b"
      }
    ],
    "consulta": {
      "entrada": {
        "order_id_hash": "6c692fee757cc3ed",
        "reference_date": "2018-02-12"
      },
      "saida": {
        "stage": "em_transito",
        "days_late": 11,
        "severe_delay": true
      }
    },
    "classificacao": {
      "intent": "entrega_atrasada",
      "sentiment": "negativo",
      "signals": [],
      "confidence": 0.99
    }
  }
};
