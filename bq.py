"""
Cliente BigQuery compartilhado pelo app e pelo auth.

Existe para os dois lerem o BigQuery com a MESMA credencial e a mesma
ordem de precedência, sem duplicar a lógica:

1. service account em `.streamlit/secrets.toml`, sob [gcp_service_account]
   — é o que funciona em servidor, onde não há gcloud;
2. nada lá: cai na credencial de aplicação da máquina, criada por
   `gcloud auth application-default login`.

A conta precisa de leitura no dataset inteiro (`greenhouse_dev`), não só
nas views do farol: o auth também lê a tabela de allowlist que mora lá.
"""

import streamlit as st

PROJETO = "br-in-dataplatform"
DATASET = "greenhouse_dev"


def _credenciais():
    try:
        sa = st.secrets["gcp_service_account"]
    except Exception:
        return None
    from google.oauth2 import service_account

    return service_account.Credentials.from_service_account_info(dict(sa))


@st.cache_resource(show_spinner=False)
def cliente():
    """Cliente BigQuery. Em cache_resource porque é conexão, não dado:
    um por sessão do servidor, reaproveitado entre reruns."""
    from google.cloud import bigquery

    return bigquery.Client(project=PROJETO, credentials=_credenciais())


def consultar(sql: str):
    """Roda a query e devolve um DataFrame."""
    return cliente().query(sql).to_dataframe()


def tabela(nome: str) -> str:
    """Nome qualificado de um objeto do dataset, para interpolar em SQL."""
    return f"`{PROJETO}.{DATASET}.{nome}`"
