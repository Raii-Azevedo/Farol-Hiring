"""
Farol de Hiring — protótipo Streamlit (branding Artefact)
Le farol_executivo.csv e funil_pipe.csv (mock) e reproduz as duas paginas
definidas no discovery: Farol Executivo e Visao do Pipe.

Rodar:
    pip install -r requirements.txt
    streamlit run app.py
(os CSVs e a pasta assets/ precisam estar na mesma pasta que este arquivo)
"""

import base64
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from PIL import Image

# ---------------------------------------------------------------------------
# Paleta oficial — extraída do "NEW Branding Guide Artefact - Nov 2024.pptx"
# ---------------------------------------------------------------------------
DARK_BLUE = "#002244"
MEDIUM_BLUE = "#0D1634"
ARTEFACT_BLUE = "#273275"
PURPLE = "#752E7D"
PINK = "#FF0066"
GRADIENT_CSS = f"linear-gradient(120deg, {DARK_BLUE} 0%, {ARTEFACT_BLUE} 38%, {PURPLE} 70%, {PINK} 100%)"

INK = "#0B1330"
MUTED = "#66708A"
PAPER = "#F5F7FB"
LINE = "#E4E8F2"

# cores semânticas do farol (não são cores de marca — são o próprio semáforo)
GREEN, AMBER, RED, GRAY = "#12B76A", "#F5A623", "#E5484D", "#B7BECF"
GREEN_BG, AMBER_BG, RED_BG, GRAY_BG = "#E7F9F1", "#FFF6E5", "#FDECEC", "#F1F3F8"

STATUS_COLOR = {"acelerar": GREEN, "manter": AMBER, "pausar": RED, "sem_dado": GRAY}
STATUS_BG = {"acelerar": GREEN_BG, "manter": AMBER_BG, "pausar": RED_BG, "sem_dado": GRAY_BG}
STATUS_ICON = {"acelerar": "🟢", "manter": "🟡", "pausar": "🔴", "sem_dado": "⚪"}
STATUS_LABEL = {"acelerar": "ACELERAR", "manter": "MANTER", "pausar": "PAUSAR", "sem_dado": "SEM DADO"}

# nomes reais do pipe, conforme o deck "Projeto Farol de Contratacao" (jun/2026)
STAGES_ORDER = [
    "Envio de Currículo", "Entrevista Fit", "Técnica 1", "Técnica 2",
    "Conversa com André", "Oferta", "Contratação",
]

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR
ASSETS_DIR = BASE_DIR / "assets"


def _b64(path: Path) -> str:
    # sem @st.cache_data de propósito: o cache decorator mostra um spinner na
    # primeira chamada, e isso conta como "comando" antes do set_page_config,
    # que precisa ser sempre o primeiro comando Streamlit do script.
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


_logo_path = ASSETS_DIR / "artefact_a_white.png"
_favicon_path = ASSETS_DIR / "artefact_a_gradient.png"
LOGO_B64 = _b64(_logo_path) if _logo_path.exists() else None
FAVICON = Image.open(_favicon_path) if _favicon_path.exists() else "🚦"

st.set_page_config(page_title="Farol de Hiring · Artefact", page_icon=FAVICON, layout="wide")

# ---------------------------------------------------------------------------
# CSS — tipografia Roboto (fonte oficial p/ ativos digitais), esconde o chrome
# padrão do Streamlit e estiliza componentes no padrão do branding Artefact.
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&family=Roboto+Mono:wght@500;700&display=swap');

        * {{ box-sizing: border-box; }}
        html, body, [class*="css"] {{ font-family: 'Roboto', sans-serif; }}
        .stApp {{ background: {PAPER}; }}

        /* remove o chrome padrao do Streamlit por completo (display:none, nao
           visibility:hidden, senao o espaco reservado fica como uma faixa
           em branco no topo da pagina) */
        #MainMenu, footer, header[data-testid="stHeader"] {{ display: none !important; }}

        .block-container {{
            padding: 1.5rem 1.25rem 3rem !important;
            max-width: 1180px;
        }}

        /* ---- header de marca: banner contido dentro do container, nunca
               "sangrando" pra fora dele (evita cortes/gaps em telas menores) ---- */
        .brand-header {{
            background: {GRADIENT_CSS};
            width: 100%;
            padding: 24px 28px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 14px;
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(0,34,68,.16);
            margin-bottom: 22px;
        }}
        .brand-header .left {{ display: flex; align-items: center; gap: 14px; min-width: 0; }}
        .brand-header .left img {{ height: 30px; flex-shrink: 0; }}
        .brand-header .title {{ color: #fff; font-weight: 900; font-size: clamp(17px, 2.4vw, 22px); letter-spacing: -0.02em; line-height:1.15; white-space: nowrap; }}
        .brand-header .subtitle {{ color: rgba(255,255,255,.65); font-size: 11px; letter-spacing: .06em; text-transform: uppercase; margin-top:3px; }}
        .brand-header .right {{ color: rgba(255,255,255,.78); font-size: 12px; text-align: right; line-height:1.6; flex-shrink: 0; }}
        .brand-header .right b {{ color: #fff; }}

        @media (max-width: 700px) {{
            .brand-header {{ flex-direction: column; align-items: flex-start; padding: 20px; }}
            .brand-header .right {{ text-align: left; }}
        }}

        h1, h2, h3 {{ color: {INK}; font-weight: 700; }}
        h3 {{ font-size: 16px; margin: 4px 0 2px; }}

        /* ---- tabs como nav de site (quebra linha em telas estreitas) ---- */
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {LINE}; flex-wrap: wrap; }}
        .stTabs [data-baseweb="tab"] {{
            height: auto; padding: 10px 16px; background: transparent; border-radius: 10px 10px 0 0;
            color: {MUTED}; font-weight: 600; font-size: 14px;
        }}
        .stTabs [aria-selected="true"] {{ color: {ARTEFACT_BLUE}; border-bottom: 3px solid {PINK}; }}

        /* ---- cards do farol: altura e alinhamento consistentes mesmo com
               nomes de chapter de tamanhos diferentes ---- */
        .farol-card {{
            position: relative;
            border: 1px solid {LINE}; border-radius: 16px; padding: 18px 14px;
            text-align: center; background: #fff;
            box-shadow: 0 2px 10px rgba(11,19,48,.04);
            transition: transform .15s ease, box-shadow .15s ease;
            display: flex; flex-direction: column; justify-content: space-between;
            min-height: 190px; width: 100%;
        }}
        .farol-card:hover {{ transform: translateY(-3px); box-shadow: 0 10px 22px rgba(11,19,48,.09); }}

        /* ---- tooltip de insight ao passar o mouse no card ---- */
        .farol-card[data-tip]:hover::after {{
            content: attr(data-tip);
            position: absolute; left: 50%; bottom: calc(100% + 10px);
            transform: translateX(-50%);
            background: {INK}; color: #fff; font-family: 'Roboto', sans-serif;
            font-size: 12px; font-weight: 400; line-height: 1.5; text-align: left;
            padding: 10px 13px; border-radius: 10px; width: 220px;
            box-shadow: 0 10px 24px rgba(0,0,0,.28); z-index: 30; pointer-events: none;
        }}
        .farol-card[data-tip]:hover::before {{
            content: ""; position: absolute; left: 50%; bottom: 100%;
            transform: translateX(-50%); margin-bottom: 4px;
            border: 6px solid transparent; border-top-color: {INK}; z-index: 30;
        }}
        .farol-card .chapter {{
            font-weight: 700; font-size: 13px; color: {INK}; line-height: 1.3;
            min-height: 34px; display: flex; align-items: center; justify-content: center;
        }}
        .farol-card .light {{ font-size: 28px; margin: 6px 0; }}
        .farol-card .badge {{
            display: inline-block; font-weight: 800; letter-spacing: .04em; font-size: 11px;
            padding: 4px 12px; border-radius: 20px; text-transform: uppercase;
        }}
        .farol-card .kpis {{ font-size: 12px; color: {MUTED}; margin-top: 10px; line-height: 1.7; font-family: 'Roboto Mono', monospace; }}
        .farol-card .kpis b {{ color: {INK}; }}

        /* ---- botao ---- */
        .stButton > button {{
            border-radius: 8px; border: 1px solid {LINE}; color: {ARTEFACT_BLUE};
            font-weight: 600; font-size: 12.5px; padding: 4px 0; width: 100%;
        }}
        .stButton > button:hover {{ border-color: {PINK}; color: {PINK}; }}

        /* ---- footer custom ---- */
        .brand-footer {{
            margin-top: 36px; padding-top: 16px; border-top: 1px solid {LINE};
            color: {MUTED}; font-size: 11.5px; text-align: center;
        }}
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Header de marca
# ---------------------------------------------------------------------------
_logo_html = f'<img src="data:image/png;base64,{LOGO_B64}">' if LOGO_B64 else ""
st.markdown(
    f"""
    <div class="brand-header">
        <div class="left">
            {_logo_html}
            <div>
                <div class="title">🚦 Farol de Hiring</div>
                <div class="subtitle">Artefact · People &amp; Talent</div>
            </div>
        </div>
        <div class="right">
            Protótipo visual · dados mock<br>
            <b>Greenhouse + Artefactory</b> (simulados)
        </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.info(
    "Dados mock para prototipagem — ainda não conectado ao pipeline real (BigQuery). "
    "Estrutura das colunas já reflete o modelo de dados planejado.",
    icon="ℹ️",
)

# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
@st.cache_data
def load_data():
    farol = pd.read_csv(DATA_DIR / "farol_executivo.csv")
    pipe = pd.read_csv(DATA_DIR / "funil_pipe.csv")
    recusas_path = DATA_DIR / "propostas_recusadas.csv"
    recusas = pd.read_csv(recusas_path) if recusas_path.exists() else pd.DataFrame(
        columns=["data_recusa", "chapter", "senioridade", "motivo_recusa", "dias_para_recusa"]
    )
    return farol, pipe, recusas


try:
    farol_df, pipe_df, recusas_df = load_data()
except FileNotFoundError as e:
    st.error(
        "Não encontrei farol_executivo.csv e/ou funil_pipe.csv na mesma pasta do app.py. "
        f"Detalhe: {e}"
    )
    st.stop()

MES_LABELS = farol_df.drop_duplicates("mes").set_index("mes")["mes_label"].to_dict()
MESES = sorted(MES_LABELS.keys())


def farol_status(demanda: float, oferta: float):
    if demanda == 0:
        return "sem_dado", None
    gap_pct = round((demanda - oferta) / demanda * 100, 1)
    if gap_pct > 20:
        return "acelerar", gap_pct
    if gap_pct >= -10:
        return "manter", gap_pct
    return "pausar", gap_pct


def farol_insight(status: str, gap_pct, demanda: float, oferta: float) -> str:
    """Frase curta de leitura/ação por trás do status — a 'inteligência' por
    trás do número puro, mostrada no hover do card."""
    if status == "sem_dado":
        return "Sem demanda registrada neste período — dado insuficiente para calcular o farol deste chapter."
    if status == "acelerar":
        return (
            f"Oferta cobre {oferta / demanda * 100:.0f}% da demanda "
            f"(gap {gap_pct:+.0f}%). Priorize abrir vagas neste chapter."
        )
    if status == "manter":
        return (
            f"Oferta e demanda estão equilibradas (gap {gap_pct:+.0f}%). "
            "Mantenha o ritmo atual de contratação."
        )
    return (
        f"Oferta já superou a demanda em {abs(gap_pct):.0f}%. "
        "Considere pausar novas aberturas ou redirecionar candidatos para outro chapter."
    )


def _html_attr(text: str) -> str:
    return text.replace('"', "&quot;")


# paleta navy -> pink p/ heatmap e gráficos (no lugar do azul genérico do plotly)
BRAND_SCALE = [
    [0.0, "#F1F3F8"],
    [0.35, "#8B93C7"],
    [0.65, ARTEFACT_BLUE],
    [1.0, PINK],
]

tab_farol, tab_pipe = st.tabs(["Farol Executivo", "Visão do Pipe"])

# ---------------------------------------------------------------------------
# TAB 1 — FAROL EXECUTIVO
# ---------------------------------------------------------------------------
with tab_farol:
    st.markdown("## 🚦 Farol de Contratação")
    st.caption(
        "Leitura automática do ritmo ideal de contratação: cruza a demanda líquida de projetos "
        "(Artefactory) com a oferta ajustada do funil de candidatos (Greenhouse) e traduz isso "
        "em um semáforo por chapter e senioridade."
    )

    mes_sel = st.selectbox(
        "Mês de referência", MESES, index=len(MESES) - 1, format_func=lambda m: MES_LABELS[m], key="mes_farol"
    )

    df_mes = farol_df[farol_df["mes"] == mes_sel]

    agg = (
        df_mes.groupby("chapter", as_index=False)
        .agg(demanda=("demanda_liquida", "sum"), oferta=("oferta_ajustada", "sum"))
        .sort_values("chapter")
    )
    stat = agg.apply(lambda r: farol_status(r["demanda"], r["oferta"]), axis=1, result_type="expand")
    agg["status"], agg["gap_pct"] = stat[0], stat[1]

    st.markdown("### Farol por chapter")
    st.caption(
        "🟢 Acelerar = abrir vagas · 🟡 Manter = ritmo saudável · 🔴 Pausar = oferta acima da demanda. "
        "Passe o mouse sobre um card para o motivo do status, ou clique em **Ver detalhe** para a quebra por senioridade."
    )
    cols = st.columns(len(agg))
    if "chapter_sel" not in st.session_state:
        st.session_state["chapter_sel"] = agg.iloc[0]["chapter"]

    for col, (_, row) in zip(cols, agg.iterrows()):
        with col:
            color = STATUS_COLOR[row["status"]]
            bg = STATUS_BG[row["status"]]
            gap_txt = f"{row['gap_pct']:+.0f}%" if pd.notna(row["gap_pct"]) else "N/D"
            tip = _html_attr(farol_insight(row["status"], row["gap_pct"], row["demanda"], row["oferta"]))
            st.markdown(
                f"""
                <div class="farol-card" data-tip="{tip}">
                    <div class="chapter">{row['chapter']}</div>
                    <div class="light">{STATUS_ICON[row['status']]}</div>
                    <div class="badge" style="color:{color}; background:{bg}">{STATUS_LABEL[row['status']]}</div>
                    <div class="kpis">
                        Gap: <b>{gap_txt}</b><br>
                        Demanda: <b>{row['demanda']:.0f}</b> · Oferta: <b>{row['oferta']:.1f}</b>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.write("")
            if st.button("Ver detalhe →", key=f"btn_{row['chapter']}", use_container_width=True):
                st.session_state["chapter_sel"] = row["chapter"]

    st.divider()

    chapter_sel = st.session_state["chapter_sel"]
    st.markdown(f"### Demanda vs. oferta por senioridade — {chapter_sel}")
    st.caption(
        "A barra colorida é a oferta ajustada; o traço rosa marca a demanda líquida de referência. "
        "Passe o mouse sobre a barra para o detalhe completo do cálculo."
    )

    detail = df_mes[df_mes["chapter"] == chapter_sel].copy()
    detail_ok = detail[detail["farol_status"] != "sem_dado"]
    detail_semdado = detail[detail["farol_status"] == "sem_dado"]

    if detail_ok.empty:
        st.warning("Sem dado suficiente para nenhuma senioridade deste chapter neste mês.")
    else:
        status_labels = detail_ok["farol_status"].map(STATUS_LABEL)
        customdata_bar = list(zip(detail_ok["demanda_liquida"], detail_ok["gap_pct"], status_labels))
        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=detail_ok["senioridade"],
                x=detail_ok["oferta_ajustada"],
                orientation="h",
                marker_color=[STATUS_COLOR[s] for s in detail_ok["farol_status"]],
                name="Oferta ajustada",
                customdata=customdata_bar,
                hovertemplate=(
                    "<b>%{y}</b><br>"
                    "Oferta ajustada: <b>%{x:.1f}</b> pessoas<br>"
                    "Demanda líquida: <b>%{customdata[0]:.0f}</b> pessoas<br>"
                    "Gap: <b>%{customdata[1]:+.0f}%</b><br>"
                    "Status: <b>%{customdata[2]}</b>"
                    "<extra></extra>"
                ),
            )
        )
        fig.add_trace(
            go.Scatter(
                y=detail_ok["senioridade"],
                x=detail_ok["demanda_liquida"],
                mode="markers",
                marker=dict(symbol="line-ns", size=26, line=dict(width=3, color=PINK)),
                name="Demanda líquida (referência)",
                hovertemplate="<b>%{y}</b><br>Demanda líquida de referência: <b>%{x:.0f}</b> pessoas<extra></extra>",
            )
        )
        fig.update_layout(
            height=260,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="Pessoas",
            plot_bgcolor="white",
            paper_bgcolor="white",
            font=dict(family="Roboto, sans-serif", color=INK, size=13),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            hoverlabel=dict(bgcolor="white", font_size=12.5, font_family="Roboto, sans-serif"),
        )
        st.plotly_chart(fig, use_container_width=True)

    if not detail_semdado.empty:
        st.caption(
            "⚪ Sem dado suficiente para calcular farol: "
            + ", ".join(detail_semdado["senioridade"].tolist())
        )

    with st.expander("Ver tabela detalhada por senioridade"):
        st.dataframe(
            detail[
                ["senioridade", "demanda_liquida", "oferta_ajustada", "gap", "gap_pct", "farol_status"]
            ].rename(
                columns={
                    "senioridade": "Senioridade",
                    "demanda_liquida": "Demanda líquida",
                    "oferta_ajustada": "Oferta ajustada",
                    "gap": "Gap",
                    "gap_pct": "Gap %",
                    "farol_status": "Status",
                }
            ),
            hide_index=True,
            use_container_width=True,
            column_config={
                "Demanda líquida": st.column_config.NumberColumn(
                    help="Pessoas necessárias no período (Artefactory): ongoing + forecast ponderado − alocações previstas."
                ),
                "Oferta ajustada": st.column_config.NumberColumn(
                    format="%.1f",
                    help="Candidatos do pipe (ponderados pela conversão esperada) + SU ponderado pela taxa de reativação.",
                ),
                "Gap %": st.column_config.NumberColumn(
                    format="%.1f%%",
                    help="(Demanda − Oferta) / Demanda. Acima de 20% = acelerar; entre -10% e 20% = manter; abaixo de -10% = pausar.",
                ),
                "Status": st.column_config.TextColumn(help="Farol calculado a partir do Gap %."),
            },
        )

# ---------------------------------------------------------------------------
# TAB 2 — VISÃO DO PIPE
# ---------------------------------------------------------------------------
with tab_pipe:
    st.markdown("## 📈 Visão Completa do Pipe")
    st.caption(
        "KPIs de conversão, tempo por etapa, distribuição de candidatos e alertas de gargalo — "
        "dados do funil de contratação no Greenhouse."
    )

    col_m, col_c = st.columns([1, 1])
    with col_m:
        mes_sel2 = st.selectbox(
            "Mês de referência", MESES, index=len(MESES) - 1, format_func=lambda m: MES_LABELS[m], key="mes_pipe"
        )
    with col_c:
        chapters_pipe = sorted(pipe_df["chapter"].unique())
        chapter_sel2 = st.selectbox("Chapter (funil e conversão)", chapters_pipe, key="chapter_pipe")

    dfp_mes = pipe_df[pipe_df["mes"] == mes_sel2]
    dfp_chapter = dfp_mes[dfp_mes["chapter"] == chapter_sel2].sort_values("ordem_etapa")

    chart_layout = dict(
        margin=dict(l=10, r=10, t=10, b=10),
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Roboto, sans-serif", color=INK, size=13),
        hoverlabel=dict(bgcolor="white", font_size=12.5, font_family="Roboto, sans-serif"),
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"##### Funil de volume — {chapter_sel2}")
        st.caption("Quantos candidatos chegam vivos em cada etapa do processo, partindo do total de currículos recebidos.")
        fig_funnel = go.Figure(
            go.Funnel(
                y=dfp_chapter["etapa"],
                x=dfp_chapter["candidatos"],
                marker={"color": ARTEFACT_BLUE},
                connector={"line": {"color": LINE, "width": 1}},
                textinfo="value+percent initial",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Candidatos: <b>%{value}</b><br>"
                    "%{percentInitial} do volume inicial de currículos<br>"
                    "%{percentPrevious} vieram da etapa anterior"
                    "<extra></extra>"
                ),
            )
        )
        fig_funnel.update_layout(height=380, **chart_layout)
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_b:
        st.markdown(f"##### Conversão etapa a etapa — {chapter_sel2}")
        st.caption("% de candidatos que avançam de uma etapa para a próxima — mostra onde a eficiência do processo é pior.")
        conv = dfp_chapter.dropna(subset=["conversao_pct"])
        fig_conv = go.Figure(
            go.Bar(
                y=conv["etapa"],
                x=conv["conversao_pct"].astype(float),
                orientation="h",
                marker_color=ARTEFACT_BLUE,
                text=conv["conversao_pct"].astype(float).map(lambda v: f"{v:.0f}%"),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Conversão: <b>%{x:.0f}%</b> vieram da etapa anterior<extra></extra>",
            )
        )
        fig_conv.update_layout(height=380, xaxis_title="% que avança da etapa anterior", **chart_layout)
        st.plotly_chart(fig_conv, use_container_width=True)

    st.markdown("##### Candidatos por etapa × chapter (heatmap)")
    st.caption("Concentração de candidatos parados em cada etapa — células mais escuras indicam mais gente aguardando ali, em qualquer chapter.")
    pivot = dfp_mes.pivot_table(index="chapter", columns="etapa", values="candidatos", aggfunc="sum")
    pivot = pivot.reindex(columns=[s for s in STAGES_ORDER if s in pivot.columns])
    fig_heat = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale=BRAND_SCALE,
        aspect="auto",
        labels=dict(color="Candidatos"),
    )
    fig_heat.update_traces(
        hovertemplate="<b>%{y}</b> · %{x}<br>Candidatos parados: <b>%{z}</b><extra></extra>"
    )
    fig_heat.update_layout(height=320, **chart_layout)
    st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("##### Gargalos e SLA")
    st.caption("Etapas com tempo médio acima da meta definida, ordenadas da mais crítica para a menos crítica.")
    sla_df = dfp_mes.dropna(subset=["excesso_dias"]).copy()
    sla_df = sla_df[
        ["chapter", "etapa", "tempo_medio_dias", "meta_sla_dias", "excesso_dias", "status_sla"]
    ].sort_values("excesso_dias", ascending=False)
    sla_df.columns = ["Chapter", "Etapa", "Tempo médio (dias)", "Meta (dias)", "Excesso (dias)", "Status"]

    STATUS_SLA_LABEL = {"critico": "🔴 CRÍTICO", "atencao": "🟡 ATENÇÃO", "ok": "🟢 OK"}
    sla_df["Status"] = sla_df["Status"].map(STATUS_SLA_LABEL).fillna(sla_df["Status"])

    st.dataframe(
        sla_df,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Tempo médio (dias)": st.column_config.NumberColumn(
                help="Tempo médio corrido que um candidato permanece nesta etapa, neste mês."
            ),
            "Meta (dias)": st.column_config.NumberColumn(help="SLA alvo definido para esta etapa."),
            "Excesso (dias)": st.column_config.NumberColumn(
                help="Tempo médio − meta. Negativo significa que a etapa está dentro do prazo."
            ),
            "Status": st.column_config.TextColumn(
                help="🔴 Crítico: excesso > 5 dias · 🟡 Atenção: até 5 dias de excesso · 🟢 OK: dentro da meta."
            ),
        },
    )

    top_gargalo = sla_df.iloc[0]
    if top_gargalo["Status"] == STATUS_SLA_LABEL["critico"]:
        st.error(
            f"🔴 Gargalo crítico: **{top_gargalo['Etapa']}** em {top_gargalo['Chapter']} — "
            f"{top_gargalo['Tempo médio (dias)']} dias vs. meta de {top_gargalo['Meta (dias)']} dias."
        )

    st.divider()
    st.markdown("##### Propostas recusadas")
    st.caption(
        "Rastreabilidade de ofertas recusadas por motivo — não só a taxa de aceite agregada, "
        "mas onde e por que o pipe está perdendo gente na reta final."
    )
    if recusas_df.empty:
        st.info("Nenhuma proposta recusada registrada na fonte de dados ainda.")
    else:
        recusas_mes = recusas_df[recusas_df["data_recusa"].str.slice(0, 7) == mes_sel2]
        if recusas_mes.empty:
            st.caption(f"Nenhuma proposta recusada registrada em {MES_LABELS[mes_sel2]}.")
        else:
            col_r1, col_r2 = st.columns([1, 1])
            with col_r1:
                por_motivo = (
                    recusas_mes.groupby("motivo_recusa", as_index=False)
                    .size()
                    .rename(columns={"size": "qtd"})
                    .sort_values("qtd", ascending=True)
                )
                fig_recusa = go.Figure(
                    go.Bar(
                        y=por_motivo["motivo_recusa"],
                        x=por_motivo["qtd"],
                        orientation="h",
                        marker_color=PINK,
                        hovertemplate="<b>%{y}</b><br>%{x} recusa(s) neste mês<extra></extra>",
                    )
                )
                fig_recusa.update_layout(
                    height=max(180, 40 * len(por_motivo)),
                    xaxis_title="Nº de recusas",
                    **chart_layout,
                )
                st.plotly_chart(fig_recusa, use_container_width=True)
            with col_r2:
                st.dataframe(
                    recusas_mes.rename(
                        columns={
                            "data_recusa": "Data",
                            "chapter": "Chapter",
                            "senioridade": "Senioridade",
                            "motivo_recusa": "Motivo",
                            "dias_para_recusa": "Dias até recusar",
                        }
                    ),
                    hide_index=True,
                    use_container_width=True,
                    column_config={
                        "Dias até recusar": st.column_config.NumberColumn(
                            help="Dias entre a oferta ser enviada e o candidato recusar — recusa rápida geralmente é oferta concorrente; recusa lenta geralmente é negociação/contraproposta."
                        ),
                    },
                )

st.markdown(
    """
    <div class="brand-footer">
        Farol de Hiring · Artefact People &amp; Talent — protótipo de discovery, dados mock
    </div>
    """,
    unsafe_allow_html=True,
)
