"""
Farol de Hiring — protótipo Streamlit (branding Artefact, light/dark)
Le farol_executivo.csv, funil_pipe.csv e propostas_recusadas.csv (mock) e
reproduz as duas paginas definidas no discovery: Farol Executivo e Visao do Pipe.

Rodar:
    pip install -r requirements.txt
    streamlit run app.py
(os CSVs, a pasta assets/ e a pasta .streamlit/ precisam estar na mesma pasta
que este arquivo)
"""

import base64
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
from PIL import Image

# ---------------------------------------------------------------------------
# Paleta de marca — extraída do "NEW Branding Guide Artefact - Nov 2024.pptx".
# Essas cores NÃO mudam entre claro/escuro (gradiente do header, azuis e rosa
# usados nos gráficos) — só o "fundo/superfície/texto" da página muda de tema.
# ---------------------------------------------------------------------------
DARK_BLUE = "#002244"
MEDIUM_BLUE = "#0D1634"
ARTEFACT_BLUE = "#273275"
PURPLE = "#752E7D"
PINK = "#FF0066"
GRADIENT_CSS = f"linear-gradient(120deg, {DARK_BLUE} 0%, {ARTEFACT_BLUE} 38%, {PURPLE} 70%, {PINK} 100%)"

# cores semânticas do farol (não são cores de marca — são o próprio semáforo,
# iguais nos dois temas; só o "fundo" do badge muda)
GREEN, AMBER, RED, GRAY = "#12B76A", "#F5A623", "#E5484D", "#B7BECF"

STATUS_COLOR = {"acelerar": GREEN, "manter": AMBER, "pausar": RED, "sem_dado": GRAY}
STATUS_ICON = {"acelerar": "🟢", "manter": "🟡", "pausar": "🔴", "sem_dado": "⚪"}
STATUS_LABEL = {"acelerar": "ACELERAR", "manter": "MANTER", "pausar": "PAUSAR", "sem_dado": "SEM DADO"}

STATUS_BG_BY_THEME = {
    "light": {"acelerar": "#E7F9F1", "manter": "#FFF6E5", "pausar": "#FDECEC", "sem_dado": "#F1F3F8"},
    "dark": {
        "acelerar": "rgba(18,183,106,.20)",
        "manter": "rgba(245,166,35,.22)",
        "pausar": "rgba(229,72,77,.22)",
        "sem_dado": "rgba(255,255,255,.10)",
    },
}

# cores de fundo/texto das "notes" (callouts) por variante, só usadas no tema
# claro — no escuro cai tudo pra superfície do card, só o accent muda
NOTE_BG_LIGHT = {"info": "#FDF2F6", "neutral": "#F0F3F7", "warn": "#FFF8E8", "critical": "#FDECEC"}
NOTE_TEXT_LIGHT = {"info": "#6B2338", "neutral": "#1F2733", "warn": "#6B5111", "critical": "#6B1620"}

# paletas de "canvas" (fundo/superficie/texto/borda) por tema
PALETTES = {
    "light": {
        "bg": "#F5F7FB",
        "surface": "#FFFFFF",
        "surface2": "#F5F7FB",
        "ink": "#0B1330",
        "muted": "#66708A",
        "line": "#E4E8F2",
        "shadow": "rgba(11,19,48,.04)",
        "shadow_hover": "rgba(11,19,48,.09)",
        "heat_low": "#F1F3F8",
        "tooltip_bg": "#0B1330",
        "tooltip_text": "#FFFFFF",
    },
    "dark": {
        "bg": MEDIUM_BLUE,
        "surface": "#152246",
        "surface2": "#1B2B57",
        "ink": "#F2F4FA",
        "muted": "#9AA5C7",
        "line": "rgba(255,255,255,.12)",
        "shadow": "rgba(0,0,0,.25)",
        "shadow_hover": "rgba(0,0,0,.45)",
        "heat_low": "#1B2B57",
        "tooltip_bg": "#F2F4FA",
        "tooltip_text": "#0B1330",
    },
}

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
# Tema ativo (claro/escuro) — guardado em session_state, alternado pelo botão
# logo abaixo do header. Precisa ser resolvido antes do bloco de CSS.
# ---------------------------------------------------------------------------
if "theme" not in st.session_state:
    st.session_state["theme"] = "light"

THEME = st.session_state["theme"]
PAL = PALETTES[THEME]
STATUS_BG = STATUS_BG_BY_THEME[THEME]

# ---------------------------------------------------------------------------
# CSS — tipografia Roboto (fonte oficial p/ ativos digitais), esconde o chrome
# padrão do Streamlit e estiliza componentes no padrão do branding Artefact,
# já considerando o tema ativo (PAL).
# ---------------------------------------------------------------------------
st.markdown(
    f"""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700;900&family=Roboto+Mono:wght@500;700&display=swap');

        * {{ box-sizing: border-box; }}
        html, body, [class*="css"] {{ font-family: 'Roboto', sans-serif; }}
        .stApp {{ background: {PAL['bg']}; }}

        /* remove o chrome padrao do Streamlit por completo (display:none, nao
           visibility:hidden, senao o espaco reservado fica como uma faixa
           em branco no topo da pagina) */
        #MainMenu, footer, header[data-testid="stHeader"] {{ display: none !important; }}

        .block-container {{
            padding: 1.5rem 1.25rem 3rem !important;
            max-width: 1180px;
        }}

        /* ---- header de marca: banner contido dentro do container, nunca
               "sangrando" pra fora dele (evita cortes/gaps em telas menores).
               O gradiente é igual nos dois temas — é a marca, não muda. ---- */
        .brand-header {{
            background: {GRADIENT_CSS};
            width: 100%;
            padding: 24px 28px;
            display: flex; align-items: center; justify-content: space-between;
            flex-wrap: wrap; gap: 14px;
            border-radius: 18px;
            box-shadow: 0 10px 28px rgba(0,34,68,.25);
            margin-bottom: 10px;
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

        /* ---- botão de tema: pequeno, circular, alinhado à direita logo
               abaixo do header ---- */
        div[data-testid="column"]:has(.theme-toggle-marker) {{
            display: flex; justify-content: flex-end;
        }}
        div[data-testid="column"]:has(.theme-toggle-marker) .stButton > button {{
            width: 42px; height: 42px; border-radius: 50%; padding: 0;
            font-size: 18px; line-height: 1; border: 1px solid {PAL['line']};
            background: {PAL['surface']}; color: {PAL['ink']};
            box-shadow: 0 2px 8px {PAL['shadow']};
        }}
        div[data-testid="column"]:has(.theme-toggle-marker) .stButton > button:hover {{
            border-color: {PINK}; color: {PINK};
        }}

        h1, h2, h3 {{ color: {PAL['ink']}; font-weight: 700; }}
        h3 {{ font-size: 16px; margin: 4px 0 2px; }}
        p, span, label, .stMarkdown, [data-testid="stCaptionContainer"] {{ color: {PAL['ink']}; }}
        [data-testid="stCaptionContainer"] {{ color: {PAL['muted']} !important; }}

        /* ---- tabs como nav de site (quebra linha em telas estreitas) ---- */
        .stTabs [data-baseweb="tab-list"] {{ gap: 4px; border-bottom: 1px solid {PAL['line']}; flex-wrap: wrap; }}
        .stTabs [data-baseweb="tab"] {{
            height: auto; padding: 10px 16px; background: transparent; border-radius: 10px 10px 0 0;
            color: {PAL['muted']}; font-weight: 600; font-size: 14px;
        }}
        .stTabs [aria-selected="true"] {{ color: {ARTEFACT_BLUE if THEME == 'light' else '#8FA3FF'}; border-bottom: 3px solid {PINK}; }}

        /* ---- cards do farol: altura e alinhamento consistentes mesmo com
               nomes de chapter de tamanhos diferentes ---- */
        .farol-card {{
            position: relative;
            border: 1px solid {PAL['line']}; border-radius: 16px; padding: 18px 14px;
            text-align: center; background: {PAL['surface']};
            box-shadow: 0 2px 10px {PAL['shadow']};
            transition: transform .15s ease, box-shadow .15s ease;
            display: flex; flex-direction: column; justify-content: space-between;
            min-height: 190px; width: 100%;
        }}
        .farol-card:hover {{ transform: translateY(-3px); box-shadow: 0 10px 22px {PAL['shadow_hover']}; }}

        /* ---- tooltip de insight ao passar o mouse no card ---- */
        .farol-card[data-tip]:hover::after {{
            content: attr(data-tip);
            position: absolute; left: 50%; bottom: calc(100% + 10px);
            transform: translateX(-50%);
            background: {PAL['tooltip_bg']}; color: {PAL['tooltip_text']}; font-family: 'Roboto', sans-serif;
            font-size: 12px; font-weight: 400; line-height: 1.5; text-align: left;
            padding: 10px 13px; border-radius: 10px; width: 220px;
            box-shadow: 0 10px 24px rgba(0,0,0,.28); z-index: 30; pointer-events: none;
        }}
        .farol-card[data-tip]:hover::before {{
            content: ""; position: absolute; left: 50%; bottom: 100%;
            transform: translateX(-50%); margin-bottom: 4px;
            border: 6px solid transparent; border-top-color: {PAL['tooltip_bg']}; z-index: 30;
        }}
        .farol-card .chapter {{
            font-weight: 700; font-size: 13px; color: {PAL['ink']}; line-height: 1.3;
            min-height: 34px; display: flex; align-items: center; justify-content: center;
        }}
        .farol-card .light {{ font-size: 28px; margin: 6px 0; }}
        .farol-card .badge {{
            display: inline-block; font-weight: 800; letter-spacing: .04em; font-size: 11px;
            padding: 4px 12px; border-radius: 20px; text-transform: uppercase;
        }}
        .farol-card .kpis {{ font-size: 12px; color: {PAL['muted']}; margin-top: 10px; line-height: 1.7; font-family: 'Roboto Mono', monospace; }}
        .farol-card .kpis b {{ color: {PAL['ink']}; }}

        /* ---- botao padrao ---- */
        .stButton > button {{
            border-radius: 8px; border: 1px solid {PAL['line']}; color: {ARTEFACT_BLUE if THEME == 'light' else '#8FA3FF'};
            font-weight: 600; font-size: 12.5px; padding: 4px 0; width: 100%;
            background: {PAL['surface']};
        }}
        .stButton > button:hover {{ border-color: {PINK}; color: {PINK}; }}

        /* ---- inputs (selectbox etc) ---- */
        [data-testid="stSelectbox"] div[data-baseweb="select"] > div {{
            background: {PAL['surface']}; border-color: {PAL['line']}; color: {PAL['ink']};
        }}

        /* ---- tabela custom (substitui st.dataframe p/ garantir legibilidade
               em qualquer tema — cada célula respeita a paleta ativa) ---- */
        .table-wrap {{
            border: 1px solid {PAL['line']}; border-radius: 12px; overflow: hidden;
            margin-bottom: 8px;
        }}
        table.app-table {{ width: 100%; border-collapse: collapse; font-size: 13px; }}
        table.app-table th {{
            text-align: left; background: {PAL['surface2']}; color: {PAL['muted']};
            font-size: 11px; text-transform: uppercase; letter-spacing: .04em;
            padding: 9px 12px; border-bottom: 1px solid {PAL['line']}; font-weight: 700;
        }}
        table.app-table td {{
            padding: 9px 12px; border-bottom: 1px solid {PAL['line']};
            color: {PAL['ink']}; background: {PAL['surface']};
        }}
        table.app-table tr:last-child td {{ border-bottom: none; }}
        table.app-table .th-help {{ color: {PAL['muted']}; cursor: help; font-size: 10.5px; }}
        table.app-table th.num, table.app-table td.num {{
            text-align: right; font-family: 'Roboto Mono', monospace; font-variant-numeric: tabular-nums;
        }}
        table.app-table th.center, table.app-table td.center {{ text-align: center; }}
        .spark {{ display: block; margin: 0 auto; }}
        .spark-empty {{ color: {PAL['muted']}; font-size: 11px; }}

        /* ---- banner de insight: frase-achado calculada a partir dos dados,
               não texto estático ---- */
        .finding {{
            background: {GRADIENT_CSS}; border-radius: 12px; padding: 14px 18px; margin: 2px 0 18px;
            display: flex; gap: 14px; align-items: flex-start; box-shadow: 0 6px 18px rgba(0,34,68,.18);
        }}
        .finding .finding-eyebrow {{
            flex: 0 0 auto; background: rgba(255,255,255,.16); color: #fff; border-radius: 5px;
            font-size: 9.5px; font-weight: 700; letter-spacing: .06em; padding: 4px 8px;
            margin-top: 1px; text-transform: uppercase; white-space: nowrap;
        }}
        .finding p {{ color: #fff; font-size: 13px; line-height: 1.6; margin: 0; }}
        .finding p b {{ color: #FFB3D3; }}

        /* ---- notes: callouts discretos, cor por severidade (substitui os
               st.info/st.warning/st.error nativos, com visual mais sóbrio) ---- */
        .app-note {{
            border-radius: 8px; border-left: 3px solid transparent; padding: 10px 14px;
            font-size: 12.5px; line-height: 1.6; margin: 10px 0;
        }}
        .app-note b {{ font-weight: 700; }}

        /* ---- caixas de alerta nativas (fallback, quando ainda usadas) ---- */
        div[data-testid="stAlertContainer"] {{ background: {PAL['surface']}; border: 1px solid {PAL['line']}; }}

        /* ---- footer custom ---- */
        .brand-footer {{
            margin-top: 36px; padding-top: 16px; border-top: 1px solid {PAL['line']};
            color: {PAL['muted']}; font-size: 11.5px; text-align: center;
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

# botão de alternância de tema — canto direito, logo abaixo do header
_, col_toggle = st.columns([14, 1])
with col_toggle:
    st.markdown('<span class="theme-toggle-marker"></span>', unsafe_allow_html=True)
    toggle_icon = "🌙" if THEME == "light" else "☀️"
    if st.button(toggle_icon, key="theme_toggle", help="Alternar tema claro/escuro"):
        st.session_state["theme"] = "dark" if THEME == "light" else "light"
        st.rerun()

def render_note(html_text: str, variant: str = "info") -> None:
    """Callout discreto (substitui st.info/st.warning/st.error) — cor de accent
    por severidade, respeitando o tema ativo."""
    accent = {"info": PINK, "neutral": ARTEFACT_BLUE, "warn": AMBER, "critical": RED}[variant]
    if THEME == "light":
        bg, text_color = NOTE_BG_LIGHT[variant], NOTE_TEXT_LIGHT[variant]
    else:
        bg, text_color = PAL["surface2"], PAL["ink"]
    st.markdown(
        f'<div class="app-note" style="border-left-color:{accent};background:{bg};color:{text_color}">{html_text}</div>',
        unsafe_allow_html=True,
    )


render_note(
    "Dados mock para prototipagem — ainda não conectado ao pipeline real (BigQuery). "
    "Estrutura das colunas já reflete o modelo de dados planejado.",
    variant="neutral",
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


def gap_trend(chapter: str, senioridade: str) -> list:
    hist = farol_df[(farol_df["chapter"] == chapter) & (farol_df["senioridade"] == senioridade)].sort_values("mes")
    return hist["gap_pct"].tolist()


def pipe_trend(chapter: str, etapa: str, col: str = "tempo_medio_dias") -> list:
    hist = pipe_df[(pipe_df["chapter"] == chapter) & (pipe_df["etapa"] == etapa)].sort_values("mes")
    return hist[col].tolist()


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


def render_table(
    df: pd.DataFrame,
    help_map: dict | None = None,
    numeric_cols: set | None = None,
    center_cols: set | None = None,
) -> None:
    """Tabela HTML própria (em vez de st.dataframe) para garantir legibilidade
    idêntica nos dois temas — o widget nativo do Streamlit não re-tematiza em
    tempo real sem reiniciar o servidor. numeric_cols usa fonte monoespaçada
    alinhada à direita (tabular nums); center_cols centraliza (ex: sparkline)."""
    help_map = help_map or {}
    numeric_cols = numeric_cols or set()
    center_cols = center_cols or set()

    def _cls(col: str) -> str:
        if col in numeric_cols:
            return ' class="num"'
        if col in center_cols:
            return ' class="center"'
        return ""

    thead_cells = "".join(
        (
            f'<th{_cls(c)} title="{_html_attr(help_map[c])}">{c} <span class="th-help">(?)</span></th>'
            if c in help_map
            else f"<th{_cls(c)}>{c}</th>"
        )
        for c in df.columns
    )
    body_rows = "".join(
        "<tr>"
        + "".join(f"<td{_cls(col)}>{'' if pd.isna(v) else v}</td>" for col, v in zip(df.columns, row))
        + "</tr>"
        for row in df.itertuples(index=False)
    )
    st.markdown(
        f"""
        <div class="table-wrap">
        <table class="app-table">
          <thead><tr>{thead_cells}</tr></thead>
          <tbody>{body_rows}</tbody>
        </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def sparkline_svg(values: list, color: str, w: int = 60, h: int = 20) -> str:
    """Mini gráfico de tendência inline para células de tabela."""
    vals = [v for v in values if pd.notna(v)]
    if len(vals) < 2:
        return '<span class="spark-empty">—</span>'
    mn, mx = min(vals), max(vals)
    rng = (mx - mn) or 1
    n = len(vals)
    pts = " ".join(
        f"{i * w / (n - 1):.1f},{h - 2 - (v - mn) / rng * (h - 4):.1f}" for i, v in enumerate(vals)
    )
    return (
        f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" class="spark">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linejoin="round" stroke-linecap="round"/></svg>'
    )


def render_finding(html_text: str) -> None:
    """Banner de 'frase-achado' — insight já calculado, em destaque no topo
    da página, no lugar de deixar o usuário garimpar a tabela."""
    st.markdown(
        f'<div class="finding"><span class="finding-eyebrow">Achado</span><p>{html_text}</p></div>',
        unsafe_allow_html=True,
    )


def brand_heat_scale() -> list:
    return [[0.0, PAL["heat_low"]], [0.35, "#8B93C7"], [0.65, ARTEFACT_BLUE], [1.0, PINK]]


CHART_LAYOUT = dict(
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor=PAL["surface"],
    paper_bgcolor=PAL["surface"],
    font=dict(family="Roboto, sans-serif", color=PAL["ink"], size=13),
    hoverlabel=dict(bgcolor=PAL["surface"], font_size=12.5, font_family="Roboto, sans-serif", font_color=PAL["ink"]),
    xaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
    yaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
)

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

    n_acelerar = int((agg["status"] == "acelerar").sum())
    n_pausar = int((agg["status"] == "pausar").sum())
    mes_label_sel = MES_LABELS[mes_sel]
    if n_acelerar == 0 and n_pausar == 0:
        finding_txt = f"Em <b>{mes_label_sel}</b>, todos os {len(agg)} chapters estão em 🟡 manter — ritmo de contratação equilibrado com a demanda."
    else:
        partes = []
        if n_acelerar:
            top_acel = agg[agg["status"] == "acelerar"].sort_values("gap_pct", ascending=False).iloc[0]
            partes.append(
                f"<b>{n_acelerar} chapter(s) em 🟢 acelerar</b> — destaque para <b>{top_acel['chapter']}</b> (gap {top_acel['gap_pct']:+.0f}%)"
            )
        if n_pausar:
            top_pausa = agg[agg["status"] == "pausar"].sort_values("gap_pct").iloc[0]
            partes.append(
                f"<b>{n_pausar} chapter(s) em 🔴 pausar</b> — o mais crítico é <b>{top_pausa['chapter']}</b> (gap {top_pausa['gap_pct']:+.0f}%)"
            )
        finding_txt = f"Em <b>{mes_label_sel}</b>: " + " · ".join(partes) + "."
    render_finding(finding_txt)

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
        "Cada linha liga a oferta ajustada (círculo) à demanda líquida de referência (losango rosa) — "
        "a distância entre os dois é o gap. A cor da linha segue o farol daquela senioridade."
    )

    detail = df_mes[df_mes["chapter"] == chapter_sel].copy()
    detail_ok = detail[detail["farol_status"] != "sem_dado"]
    detail_semdado = detail[detail["farol_status"] == "sem_dado"]

    if detail_ok.empty:
        render_note("Sem dado suficiente para nenhuma senioridade deste chapter neste mês.", variant="warn")
    else:
        status_labels = detail_ok["farol_status"].map(STATUS_LABEL)
        max_val = float(max(detail_ok["oferta_ajustada"].max(), detail_ok["demanda_liquida"].max()))

        fig = go.Figure()
        for _, r in detail_ok.iterrows():
            fig.add_trace(
                go.Scatter(
                    x=[r["oferta_ajustada"], r["demanda_liquida"]],
                    y=[r["senioridade"], r["senioridade"]],
                    mode="lines",
                    line=dict(color=STATUS_COLOR[r["farol_status"]], width=3),
                    hoverinfo="skip",
                    showlegend=False,
                )
            )
        fig.add_trace(
            go.Scatter(
                y=detail_ok["senioridade"],
                x=detail_ok["oferta_ajustada"],
                mode="markers",
                marker=dict(
                    size=15,
                    color=[STATUS_COLOR[s] for s in detail_ok["farol_status"]],
                    line=dict(width=2, color=PAL["surface"]),
                ),
                name="Oferta ajustada",
                customdata=list(zip(detail_ok["demanda_liquida"], detail_ok["gap_pct"], status_labels)),
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
                marker=dict(size=13, symbol="diamond", color=PINK, line=dict(width=2, color=PAL["surface"])),
                name="Demanda líquida (referência)",
                hovertemplate="<b>%{y}</b><br>Demanda líquida de referência: <b>%{x:.0f}</b> pessoas<extra></extra>",
            )
        )
        for _, r in detail_ok.iterrows():
            fig.add_annotation(
                x=max(r["oferta_ajustada"], r["demanda_liquida"]),
                y=r["senioridade"],
                text=f"{r['gap_pct']:+.0f}%",
                showarrow=False,
                xanchor="left",
                xshift=12,
                font=dict(size=11.5, color=STATUS_COLOR[r["farol_status"]], family="Roboto Mono, monospace"),
            )
        fig.update_xaxes(range=[0, max_val * 1.32 if max_val > 0 else 1])
        fig.update_layout(
            height=max(220, 70 * len(detail_ok)),
            xaxis_title="Pessoas",
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            **CHART_LAYOUT,
        )
        st.plotly_chart(fig, use_container_width=True)

    if not detail_semdado.empty:
        st.caption(
            "⚪ Sem dado suficiente para calcular farol: "
            + ", ".join(detail_semdado["senioridade"].tolist())
        )

    with st.expander("Ver tabela detalhada por senioridade"):
        tbl = detail[
            ["senioridade", "demanda_liquida", "oferta_ajustada", "gap", "gap_pct", "farol_status"]
        ].copy()
        tendencias = [
            sparkline_svg(gap_trend(chapter_sel, s), STATUS_COLOR[st_])
            for s, st_ in zip(detail["senioridade"], detail["farol_status"])
        ]
        tbl["demanda_liquida"] = tbl["demanda_liquida"].map(lambda v: f"{v:.0f}")
        tbl["oferta_ajustada"] = tbl["oferta_ajustada"].map(lambda v: f"{v:.1f}")
        tbl["gap"] = tbl["gap"].map(lambda v: f"{v:+.1f}")
        tbl["gap_pct"] = tbl["gap_pct"].map(lambda v: f"{v:+.1f}%" if pd.notna(v) else "—")
        tbl["farol_status"] = tbl["farol_status"].map(lambda s: f"{STATUS_ICON[s]} {STATUS_LABEL[s]}")
        tbl["tendencia"] = tendencias
        tbl.columns = ["Senioridade", "Demanda líquida", "Oferta ajustada", "Gap", "Gap %", "Status", "Tendência (gap)"]
        render_table(
            tbl,
            numeric_cols={"Demanda líquida", "Oferta ajustada", "Gap", "Gap %"},
            center_cols={"Tendência (gap)"},
            help_map={
                "Demanda líquida": "Pessoas necessárias no período (Artefactory): ongoing + forecast ponderado − alocações previstas.",
                "Oferta ajustada": "Candidatos do pipe (ponderados pela conversão esperada) + SU ponderado pela taxa de reativação.",
                "Gap %": "(Demanda − Oferta) / Demanda. Acima de 20% = acelerar; entre -10% e 20% = manter; abaixo de -10% = pausar.",
                "Status": "Farol calculado a partir do Gap %.",
                "Tendência (gap)": "Evolução do Gap % ao longo dos meses disponíveis, para esta senioridade.",
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

    sla_calc = dfp_mes.dropna(subset=["excesso_dias"])
    n_crit_pipe = int((sla_calc["status_sla"] == "critico").sum())
    recusas_calc = recusas_df[recusas_df["data_recusa"].str.slice(0, 7) == mes_sel2] if not recusas_df.empty else recusas_df
    partes_pipe = []
    if n_crit_pipe:
        top_gargalo_calc = sla_calc.sort_values("excesso_dias", ascending=False).iloc[0]
        partes_pipe.append(
            f"<b>{n_crit_pipe} etapa(s) em SLA crítico</b> — a pior é <b>{top_gargalo_calc['etapa']}</b> em {top_gargalo_calc['chapter']} "
            f"({top_gargalo_calc['tempo_medio_dias']:.0f}d vs. meta de {top_gargalo_calc['meta_sla_dias']:.0f}d)"
        )
    else:
        partes_pipe.append("Nenhuma etapa em SLA crítico neste mês")
    if not recusas_calc.empty:
        partes_pipe.append(f"<b>{len(recusas_calc)} proposta(s) recusada(s)</b> registrada(s)")
    render_finding(f"Em <b>{MES_LABELS[mes_sel2]}</b>: " + " · ".join(partes_pipe) + ".")

    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown(f"##### Funil de volume — {chapter_sel2}")
        st.caption("Quantos candidatos chegam vivos em cada etapa do processo, partindo do total de currículos recebidos.")
        fig_funnel = go.Figure(
            go.Funnel(
                y=dfp_chapter["etapa"],
                x=dfp_chapter["candidatos"],
                marker={"color": ARTEFACT_BLUE},
                connector={"line": {"color": PAL["line"], "width": 1}},
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
        fig_funnel.update_layout(height=380, **CHART_LAYOUT)
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
        fig_conv.update_layout(height=380, xaxis_title="% que avança da etapa anterior", **CHART_LAYOUT)
        st.plotly_chart(fig_conv, use_container_width=True)

    st.markdown("##### Candidatos por etapa × chapter (heatmap)")
    st.caption("Concentração de candidatos parados em cada etapa — células mais escuras indicam mais gente aguardando ali, em qualquer chapter.")
    pivot = dfp_mes.pivot_table(index="chapter", columns="etapa", values="candidatos", aggfunc="sum")
    pivot = pivot.reindex(columns=[s for s in STAGES_ORDER if s in pivot.columns])
    fig_heat = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale=brand_heat_scale(),
        aspect="auto",
        labels=dict(color="Candidatos"),
    )
    fig_heat.update_traces(
        hovertemplate="<b>%{y}</b> · %{x}<br>Candidatos parados: <b>%{z}</b><extra></extra>"
    )
    fig_heat.update_layout(height=320, **CHART_LAYOUT)
    st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("##### Gargalos e SLA")
    st.caption("Etapas com tempo médio acima da meta definida, ordenadas da mais crítica para a menos crítica.")
    sla_df = dfp_mes.dropna(subset=["excesso_dias"]).copy()
    sla_df = sla_df[
        ["chapter", "etapa", "tempo_medio_dias", "meta_sla_dias", "excesso_dias", "status_sla"]
    ].sort_values("excesso_dias", ascending=False)
    sla_df.columns = ["Chapter", "Etapa", "Tempo médio (dias)", "Meta (dias)", "Excesso (dias)", "Status"]

    STATUS_SLA_LABEL = {"critico": "🔴 CRÍTICO", "atencao": "🟡 ATENÇÃO", "ok": "🟢 OK"}
    sla_df["Tendência"] = [
        sparkline_svg(pipe_trend(ch, et), RED if exc > 0 else GREEN)
        for ch, et, exc in zip(sla_df["Chapter"], sla_df["Etapa"], sla_df["Excesso (dias)"])
    ]
    sla_df["Tempo médio (dias)"] = sla_df["Tempo médio (dias)"].map(lambda v: f"{v:.1f}")
    sla_df["Meta (dias)"] = sla_df["Meta (dias)"].map(lambda v: f"{v:.0f}")
    sla_df["Excesso (dias)"] = sla_df["Excesso (dias)"].map(lambda v: f"{v:+.1f}")
    sla_df["Status"] = sla_df["Status"].map(STATUS_SLA_LABEL).fillna(sla_df["Status"])

    render_table(
        sla_df,
        numeric_cols={"Tempo médio (dias)", "Meta (dias)", "Excesso (dias)"},
        center_cols={"Tendência"},
        help_map={
            "Tempo médio (dias)": "Tempo médio corrido que um candidato permanece nesta etapa, neste mês.",
            "Meta (dias)": "SLA alvo definido para esta etapa.",
            "Excesso (dias)": "Tempo médio − meta. Negativo significa que a etapa está dentro do prazo.",
            "Status": "🔴 Crítico: excesso > 5 dias · 🟡 Atenção: até 5 dias de excesso · 🟢 OK: dentro da meta.",
            "Tendência": "Evolução do tempo médio nesta etapa ao longo dos meses disponíveis.",
        },
    )

    top_gargalo = sla_df.iloc[0]
    if top_gargalo["Status"] == STATUS_SLA_LABEL["critico"]:
        render_note(
            f"🔴 <b>Gargalo crítico:</b> {top_gargalo['Etapa']} em {top_gargalo['Chapter']} — "
            f"{top_gargalo['Tempo médio (dias)']} dias vs. meta de {top_gargalo['Meta (dias)']} dias.",
            variant="critical",
        )

    st.divider()
    st.markdown("##### Propostas recusadas")
    st.caption(
        "Rastreabilidade de ofertas recusadas por motivo — não só a taxa de aceite agregada, "
        "mas onde e por que o pipe está perdendo gente na reta final."
    )
    if recusas_df.empty:
        render_note("Nenhuma proposta recusada registrada na fonte de dados ainda.", variant="neutral")
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
                    **CHART_LAYOUT,
                )
                st.plotly_chart(fig_recusa, use_container_width=True)
            with col_r2:
                recusas_tbl = recusas_mes.rename(
                    columns={
                        "data_recusa": "Data",
                        "chapter": "Chapter",
                        "senioridade": "Senioridade",
                        "motivo_recusa": "Motivo",
                        "dias_para_recusa": "Dias até recusar",
                    }
                )
                render_table(
                    recusas_tbl,
                    numeric_cols={"Dias até recusar"},
                    help_map={
                        "Dias até recusar": "Dias entre a oferta ser enviada e o candidato recusar — recusa rápida geralmente é oferta concorrente; recusa lenta geralmente é negociação/contraproposta.",
                    },
                )

st.markdown(
    f"""
    <div class="brand-footer">
        Farol de Hiring · Artefact People &amp; Talent — protótipo de discovery, dados mock
    </div>
    """,
    unsafe_allow_html=True,
)
