"""Smoke test do app conectado ao BigQuery, sem BigQuery.

Substitui streamlit, plotly e google.cloud.bigquery por stubs. O stub do
BigQuery devolve DataFrames sintéticos no formato EXATO das duas views
(vw_farol_base e vw_farol_demanda), com as características do dado real:
demanda líquida negativa no mês corrente, chapters sem demanda, vagas sem
chapter, candidatos parados e See You Soon.
"""
import sys
import types
from contextlib import contextmanager
from unittest import mock

import pandas as pd

CALLS = {"markdown": [], "captions": [], "button_keys": [], "plotly_keys": [], "dialogs": []}

CHAPTERS_COM_DEMANDA = ["Analytics Engineering", "Data Consultant", "Data Engineering", "Data Science"]
CHAPTERS_SEM_DEMANDA = ["AI Engineering", "Software Engineering"]
SENIORIDADES = ["Estagiário", "Pleno", "Senior"]
ETAPAS = [
    ("Avaliação de currículo", 1, 2), ("Envio do Case Escrito", 2, 3),
    ("Avaliação case escrito", 3, 3), ("Entrevista Fit", 4, 3),
    ("Entrevista Técnica 1", 5, 5), ("Entrevista Técnica 2", 6, 5),
    ("Conversa Final", 7, 4), ("Oferta", 8, 3),
]
MESES_DEMANDA = ["2026-10", "2026-11", "2026-12", "2027-01"]
HOJE = pd.Timestamp("2026-10-28").date()


def _base_sintetica():
    linhas, app_id = [], 0
    volumes = [60, 24, 16, 10, 7, 5, 3, 2]
    for ch in CHAPTERS_COM_DEMANDA + CHAPTERS_SEM_DEMANDA:
        for sen in SENIORIDADES:
            vaga = f"[XX BR] - {ch} {sen}"
            job_id = abs(hash(vaga)) % 100000
            for (etapa, ordem, meta), vol in zip(ETAPAS, volumes):
                tempo = meta + (ordem % 3) - 0.5          # alguns acima da meta
                esperado = sum(m for _, o, m in ETAPAS if o <= ordem)
                for k in range(max(vol // 6, 1)):
                    app_id += 1
                    dias_pipe = esperado + (12 if k == 0 else -2)   # 1 parado por grupo
                    linhas.append(dict(
                        snapshot_date=HOJE, application_id=app_id, candidate_id=app_id * 7,
                        candidato=f"Candidato {app_id}", job_id=job_id, vaga=vaga,
                        chapter=ch, senioridade=sen, etapa_origem=etapa, etapa=etapa,
                        ordem_etapa=ordem, tipo_etapa="funil",
                        application_status="active", offer_status=None,
                        flag_ativo=1, flag_contratado=0, flag_oferta=0, flag_aceite=0,
                        flag_qualificado=1 if 4 <= ordem <= 8 else 0, flag_see_you_soon=0,
                        total_days_in_pipe=float(dias_pipe),
                        tempo_medio_etapa=float(tempo), conversao_etapa_pct=70.0 if ordem > 1 else None,
                        meta_sla_etapa=meta, excesso_sla_etapa=round(tempo - meta, 1),
                        status_sla_etapa="atencao" if tempo > meta else "ok",
                        dias_esperados_ate_etapa=float(esperado),
                        dias_acima_do_esperado=float(dias_pipe - esperado),
                        status_parado="critico" if dias_pipe > esperado + 5
                                      else ("atencao" if dias_pipe > esperado else "ok"),
                        prob_contratacao=round(0.7 ** (8 - ordem), 3),
                        dias_ate_contratacao=float(sum(m for _, o, m in ETAPAS if o >= ordem)),
                        contrib_oferta_ajustada=round(0.7 ** (8 - ordem), 3),
                        tempo_contratacao_vaga=42.0,
                        su_dias_no_banco_vaga=50.0, su_candidaturas_vaga=4,
                        su_ofertas_vaga=2, su_aceites_vaga=1,
                    ))
            # contratado (vem de status, não de etapa) e alguém no See You Soon
            for etapa, flags in (("Contratação", dict(flag_contratado=1, flag_oferta=1, flag_aceite=1)),
                                 ("See You Soon", dict(flag_see_you_soon=1))):
                app_id += 1
                linha = dict(
                    snapshot_date=HOJE, application_id=app_id, candidate_id=app_id * 7,
                    candidato=f"Candidato {app_id}", job_id=job_id, vaga=vaga,
                    chapter=ch, senioridade=sen, etapa_origem=etapa, etapa=etapa,
                    ordem_etapa=9 if etapa == "Contratação" else None,
                    tipo_etapa="funil" if etapa == "Contratação" else "paralelo",
                    application_status="hired" if etapa == "Contratação" else "active",
                    offer_status="accepted" if etapa == "Contratação" else None,
                    flag_ativo=0 if etapa == "Contratação" else 1,
                    flag_contratado=0, flag_oferta=0, flag_aceite=0,
                    flag_qualificado=0, flag_see_you_soon=0,
                    total_days_in_pipe=70.0, tempo_medio_etapa=None, conversao_etapa_pct=None,
                    meta_sla_etapa=None, excesso_sla_etapa=None, status_sla_etapa=None,
                    dias_esperados_ate_etapa=None, dias_acima_do_esperado=None, status_parado=None,
                    prob_contratacao=1.0, dias_ate_contratacao=0.0, contrib_oferta_ajustada=0.0,
                    tempo_contratacao_vaga=42.0, su_dias_no_banco_vaga=50.0,
                    su_candidaturas_vaga=4, su_ofertas_vaga=2, su_aceites_vaga=1)
                linha.update(flags)
                linhas.append(linha)
    # vaga fora dos chapters do farol (chapter nulo) — tem que ser ignorada
    for k in range(3):
        app_id += 1
        linhas.append(dict(
            snapshot_date=HOJE, application_id=app_id, candidate_id=app_id * 7,
            candidato=f"Fora {k}", job_id=999, vaga="Strategy Consulting Manager",
            chapter=None, senioridade=None, etapa_origem="Entrevista Fit", etapa="Entrevista Fit",
            ordem_etapa=4, tipo_etapa="funil", application_status="active", offer_status=None,
            flag_ativo=1, flag_contratado=0, flag_oferta=0, flag_aceite=0,
            flag_qualificado=1, flag_see_you_soon=0, total_days_in_pipe=10.0,
            tempo_medio_etapa=3.0, conversao_etapa_pct=60.0, meta_sla_etapa=3,
            excesso_sla_etapa=0.0, status_sla_etapa="ok", dias_esperados_ate_etapa=11.0,
            dias_acima_do_esperado=-1.0, status_parado="ok", prob_contratacao=0.3,
            dias_ate_contratacao=20.0, contrib_oferta_ajustada=0.3, tempo_contratacao_vaga=40.0,
            su_dias_no_banco_vaga=None, su_candidaturas_vaga=None,
            su_ofertas_vaga=None, su_aceites_vaga=None))
    return pd.DataFrame(linhas)


def _demanda_sintetica():
    linhas = []
    for mes in MESES_DEMANDA:
        for ch in CHAPTERS_COM_DEMANDA:
            for sen in SENIORIDADES:
                # outubro negativo, como no dado real
                liq = -2.5 if mes == "2026-10" else (0.2 if ch == "Analytics Engineering" else 5.0)
                linhas.append(dict(mes=mes, chapter=ch, senioridade=sen,
                                   demanda_bruta_fte=max(liq, 0) + 1.0,
                                   desalocado_fte=1.0,
                                   demanda_liquida_fte=liq, niveis_origem="Entry 2"))
    return pd.DataFrame(linhas)


# ------------------------- stubs -------------------------
class SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v


class Col:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def __getattr__(self, name): return getattr(sys.modules["streamlit"], name)


class Stub(types.ModuleType):
    session_state = SessionState()

    def markdown(self, body="", **kw): CALLS["markdown"].append(str(body))
    def caption(self, body="", **kw): CALLS["captions"].append(str(body))
    def write(self, *a, **kw): pass
    def divider(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def info(self, *a, **kw): pass
    def dataframe(self, *a, **kw): pass
    def image(self, *a, **kw): pass
    def set_page_config(self, *a, **kw): pass
    def rerun(self, *a, **kw): pass
    def logout(self, *a, **kw): pass

    def error(self, *a, **kw): raise AssertionError(f"st.error: {a}")
    def stop(self): raise AssertionError("st.stop()")

    def columns(self, spec, **kw):
        return [Col() for _ in range(spec if isinstance(spec, int) else len(spec))]

    def tabs(self, labels, **kw): return [Col() for _ in labels]

    @contextmanager
    def expander(self, *a, **kw): yield Col()

    @contextmanager
    def container(self, *a, **kw): yield Col()

    def selectbox(self, label, options, index=0, format_func=None, key=None, **kw):
        options = list(options)
        return options[index or 0] if options else None

    def button(self, label, key=None, **kw):
        CALLS["button_keys"].append(key)
        return False

    def plotly_chart(self, fig, key=None, on_select=None, **kw):
        if on_select:
            CALLS["plotly_keys"].append(key)
            return {"selection": {"points": [], "point_indices": [], "box": [], "lasso": []}}

    def cache_data(self, fn=None, **kw):
        return fn if fn is not None else (lambda f: f)

    def cache_resource(self, fn=None, **kw):
        return fn if fn is not None else (lambda f: f)

    @contextmanager
    def spinner(self, *a, **kw): yield

    def dialog(self, title, **kw):
        CALLS["dialogs"].append(title)
        return lambda fn: fn


class _Fig:
    def __init__(self, data=None, **kw): self.data = [data] if data is not None else []
    def add_trace(self, t): self.data.append(t); return self
    def add_annotation(self, **kw): return self
    def update_layout(self, **kw): return self
    def update_traces(self, **kw): return self
    def update_xaxes(self, **kw): return self
    def update_yaxes(self, **kw): return self


class _Trace:
    def __init__(self, **kw): self.kw = kw


go_stub = types.ModuleType("plotly.graph_objects")
go_stub.Figure = _Fig
for n in ("Bar", "Funnel", "Scatter", "Heatmap"):
    setattr(go_stub, n, _Trace)
px_stub = types.ModuleType("plotly.express")
px_stub.imshow = lambda *a, **kw: _Fig()
plotly_pkg = types.ModuleType("plotly")
plotly_pkg.graph_objects, plotly_pkg.express = go_stub, px_stub
sys.modules.update({"plotly": plotly_pkg, "plotly.graph_objects": go_stub, "plotly.express": px_stub})

sys.modules["streamlit"] = Stub("streamlit")

# auth.py NÃO é stubado: ele é parte do que precisa ser testado agora que a
# allowlist saiu do CSV e virou uma query no BigQuery.

BASE, DEMANDA = _base_sintetica(), _demanda_sintetica()
ALLOWLIST = pd.DataFrame([
    {"email": "Raiis@artefact.com", "role": "admin"},   # maiúscula de propósito
    {"email": "rh@artefact.com", "role": None},
])
QUERIES = []
FALHAR_ALLOWLIST = {"on": False}


class _Job:
    def __init__(self, sql): self.sql = sql

    def to_dataframe(self):
        if "greenhouse_dash_access" in self.sql:
            if FALHAR_ALLOWLIST["on"]:
                raise RuntimeError("403 Access Denied: greenhouse_dash_access")
            return ALLOWLIST.copy()
        return (DEMANDA if "vw_farol_demanda" in self.sql else BASE).copy()


class _Client:
    def __init__(self, project=None, credentials=None, **kw):
        self.project, self.credentials = project, credentials
    def query(self, sql):
        QUERIES.append(sql)
        return _Job(sql)


bigquery_stub = types.ModuleType("google.cloud.bigquery")
bigquery_stub.Client = _Client
gcloud = types.ModuleType("google.cloud")
gcloud.bigquery = bigquery_stub
google = types.ModuleType("google")
google.cloud = gcloud
sys.modules.update({"google": google, "google.cloud": gcloud,
                    "google.cloud.bigquery": bigquery_stub})

with mock.patch("PIL.Image.open"):
    import app

print("IMPORT OK — app.py rodou de ponta a ponta contra as duas views\n")
print(f"  queries disparadas  : {len(QUERIES)}")
for q in QUERIES:
    print("    ", q.strip().replace("\n", " ")[:90])

assert any("vw_farol_base" in q for q in QUERIES), "não leu vw_farol_base"
assert any("vw_farol_demanda" in q for q in QUERIES), "não leu vw_farol_demanda"
assert not any("read_csv" in str(q) for q in QUERIES)

# ---- os dois eixos de tempo ----
assert app.MES_SNAPSHOT == "2026-10", app.MES_SNAPSHOT
assert set(app.MESES) == set(MESES_DEMANDA), app.MESES
print(f"\n  MES_SNAPSHOT (pipe) : {app.MES_SNAPSHOT}")
print(f"  MESES (demanda)     : {app.MESES}")
assert set(app.pipe_df["mes"]) == {"2026-10"}, "pipe deveria ter só o snapshot"

# ---- funil ----
etapas = app.pipe_df.sort_values("ordem_etapa")["etapa"].unique().tolist()
assert etapas == [e for e, _, _ in ETAPAS] + ["Contratação"], etapas
por_etapa = app.pipe_df.groupby("ordem_etapa")["candidatos"].sum()
assert por_etapa.is_monotonic_decreasing, f"funil não decrescente: {por_etapa.tolist()}"
assert app.pipe_df["candidatos"].sum() > 0
print(f"  funil               : {len(etapas)} etapas, decrescente, "
      f"{int(app.pipe_df['candidatos'].sum())} candidatos")
assert "Strategy Consulting Manager" not in set(app.parados_df["vaga"]), "vaga sem chapter vazou"

# ---- farol: o caso que só aparece com dado real ----
out = app.farol_df[app.farol_df["mes"] == "2026-10"]
assert (out["demanda_liquida"] < 0).all()
assert set(out["farol_status"]) == {"pausar"}, f"demanda negativa virou {set(out['farol_status'])}"
print(f"  demanda negativa    : {len(out)} linhas -> todas 'pausar' (não 'acelerar')")

nov = app.farol_df[app.farol_df["mes"] == "2026-11"]
assert nov["oferta_ajustada"].sum() > 0, "oferta ajustada zerada"
assert set(nov["farol_status"]) <= {"acelerar", "manter", "pausar", "sem_dado"}
print(f"  farol nov/2026      : {dict(nov['farol_status'].value_counts())}")
print(f"  oferta ajustada     : {nov['oferta_ajustada'].sum():.1f} (pipe x conversão, <= {app.HORIZONTE_FAROL_DIAS}d)")

# chapters sem demanda não podem aparecer no farol
assert not set(app.farol_df["chapter"]) & set(CHAPTERS_SEM_DEMANDA)
print(f"  chapters no farol   : {sorted(app.farol_df['chapter'].unique())}")

# ---- KPIs que dependem de nome de etapa/flag ----
for nome, v in (("conversao_total_pipe", app.conversao_total_pipe(app.MES_SNAPSHOT)),
                ("taxa_aceite_oferta", app.taxa_aceite_oferta(app.MES_SNAPSHOT)),
                ("tempo_medio_contratacao", app.tempo_medio_contratacao(app.MES_SNAPSHOT)),
                ("pipe_qualificado(DS)", app.pipe_qualificado(app.MES_SNAPSHOT, "Data Science")),
                ("su_tempo_medio_banco", app.su_tempo_medio_banco())):
    assert v is not None and v > 0, f"{nome} voltou {v}"
    print(f"  {nome:24}: {v:.1f}")

# as funções de pipe ignoram o mês: pedir um mês de forecast dá o mesmo
assert app.pipe_qualificado("2027-01", "Data Science") == app.pipe_qualificado(app.MES_SNAPSHOT, "Data Science")

# ---- parados + modais ----
assert len(app.parados_df) > 0, "nenhum candidato parado"
am = app.parados_df.iloc[0]
app.show_parados_vagas(am["etapa"], am["status"], app.MES_SNAPSHOT)
app.show_parados_candidatos(am["etapa"], am["status"], am["vaga"], app.MES_SNAPSHOT)
html = "\n".join(CALLS["markdown"][-6:])
assert am["candidato"] in html and "cand-item" in html
app.show_conv_drilldown("Entrevista Fit", app.MES_SNAPSHOT)
app.show_tempo_drilldown("Conversa Final", app.MES_SNAPSHOT)
print(f"  parados             : {len(app.parados_df)} candidatos, modais OK")

# ---- a seção de recusas tem que ter sumido ----
fonte = open("/root/app/app.py", encoding="utf-8").read()
# "recusa" em si pode aparecer: a taxa de aceite mede recusa pela etapa
# Oferta. O que não pode voltar é a seção, que dependia do motivo da recusa.
assert "propostas recusadas" not in fonte.lower(), "sobrou a seção de propostas recusadas"
assert "Propostas recusadas" not in "\n".join(CALLS["markdown"] + CALLS["captions"])
print("  propostas recusadas : removida do código e da tela")

# ---- o aviso de escopo tem que ser calculado, não escrito à mão ----
aviso = [m for m in CALLS["markdown"] if "Dados oficiais do BigQuery" in m]
assert aviso, "aviso de escopo não apareceu"
assert "Out/2026" in aviso[0], aviso[0]
for ch in CHAPTERS_SEM_DEMANDA:
    assert ch in aviso[0], f"{ch} deveria estar listado como sem demanda"
# "mock" ainda aparece em comentário de CSS; o que não pode é texto visível
for proibido in ("dados mock", "(simulados)", "não conectado ao pipeline real"):
    assert not any(proibido in m.lower() for m in CALLS["markdown"]), f"sobrou na tela: {proibido}"
print(f"  aviso de escopo     : calculado do dado, cita {len(CHAPTERS_SEM_DEMANDA)} chapters sem demanda")

fonte_auth = open("/root/app/auth.py", encoding="utf-8").read()
assert "authorized_users.csv" not in fonte_auth, "sobrou referência ao CSV de allowlist"
assert "read_csv" not in fonte_auth
assert "authorized_users.csv" not in fonte, "sobrou referência ao CSV de allowlist no app"
print("  allowlist em CSV    : removida do auth.py")

# ---- allowlist: agora é uma query, e o auth é o mesmo cliente do app ----
import auth  # noqa: E402  — depois dos stubs, de propósito
import bq as bqmod  # noqa: E402

assert bqmod._credenciais() is None, "sem secrets deveria cair na credencial de aplicação"
print("  credencial          : sem secrets -> ADC (fallback correto)")

ok, role = auth.check_authorization("RAIIS@artefact.com  ")
assert ok and role == "admin", (ok, role)
ok2, role2 = auth.check_authorization("rh@artefact.com")
assert ok2 and role2 is None, (ok2, role2)       # role nulo não quebra
ok3, role3 = auth.check_authorization("estranho@gmail.com")
assert not ok3 and role3 is None, (ok3, role3)
assert any("greenhouse_dash_access" in q for q in QUERIES), "não consultou a allowlist"
print("  allowlist no BQ     : e-mail na lista entra (case-insensitive), fora da lista não")

# ---- fail closed: allowlist ilegível NÃO libera o acesso ----
FALHAR_ALLOWLIST["on"] = True
auth._load_authorized_users.clear() if hasattr(auth._load_authorized_users, "clear") else None
try:
    auth.check_authorization("RAIIS@artefact.com")
except auth.AllowlistIndisponivel as e:
    assert "greenhouse_dash_access" in str(e)
    print("  allowlist ilegível  : levanta AllowlistIndisponivel (fail closed), não libera")
else:
    raise AssertionError("allowlist ilegível deveria bloquear, não liberar")
FALHAR_ALLOWLIST["on"] = False

print("\nTUDO OK")
