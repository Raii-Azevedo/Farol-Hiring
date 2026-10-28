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


# Abaixo disso a REST ganha: abrir a sessão da Storage Read API custa
# ~1,3s fixos, mais do que baixar umas centenas de linhas pela REST.
_LINHAS_PARA_STORAGE = 5000


def _baixar(job):
    """Download do resultado de um job já disparado.

    Resultado grande vai pela Storage Read API (google-cloud-bigquery-
    storage), ~6x mais rápida que a REST na vw_farol_base. Ela exige a
    permissão bigquery.readsessions.create (role "BigQuery Read Session
    User"), que o jobUser NÃO inclui — sem ela, cai na REST em vez de
    quebrar."""
    if (job.result().total_rows or 0) < _LINHAS_PARA_STORAGE:
        return job.to_dataframe(create_bqstorage_client=False)
    try:
        return job.to_dataframe(create_bqstorage_client=True)
    except Exception:  # noqa: BLE001 — permissão ou pacote faltando
        return job.to_dataframe(create_bqstorage_client=False)


def consultar(sql: str):
    """Roda a query e devolve um DataFrame."""
    return _baixar(cliente().query(sql))


def consultar_varias(*sqls: str) -> list:
    """Dispara todas as queries de uma vez e só depois espera: o BigQuery
    executa em paralelo, e o tempo total vira o da mais lenta, não a soma."""
    jobs = [cliente().query(sql) for sql in sqls]
    return [_baixar(job) for job in jobs]


def tabela(nome: str) -> str:
    """Nome qualificado de um objeto do dataset, para interpolar em SQL."""
    return f"`{PROJETO}.{DATASET}.{nome}`"
