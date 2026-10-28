"""
Farol de Hiring — protótipo Streamlit (branding Artefact, light/dark)
Le as views vw_farol_base e vw_farol_demanda do BigQuery (dados reais) e
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

import auth
import bq

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
# Nomes canônicos do funil REAL do Greenhouse. O de-para dos 19 nomes que
# o Greenhouse usa de fato está em sql/passo2_seeds.sql (d_farol_etapa) — inclusive
# as três variantes da conversa final e as duas etapas do case escrito,
# que o protótipo não modelava antes.
# "Contratação" aqui é etapa; no Greenhouse é status da candidatura.
STAGES_ORDER = [
    "Avaliação de currículo", "Envio do Case Escrito", "Avaliação case escrito",
    "Entrevista Fit", "Entrevista Técnica 1", "Entrevista Técnica 2",
    "Conversa Final", "Oferta", "Contratação",
]

# Níveis que dá para deduzir do job_name do Greenhouse. O Artefactory tem
# 16 níveis; o de-para para estes três está na vw_farol_demanda.
SENIORIDADE_ORDER = ["Estagiário", "Pleno", "Senior"]

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

        /* ---- tooltip nativo do Streamlit (help="..." em botoes/inputs,
               como o botao de alternar tema) — o chrome do Streamlit fica
               sempre no tema claro (.streamlit/config.toml), entao esse
               tooltip nao pode seguir o PAL (que muda com o toggle
               claro/escuro da pagina): dependendo do tema ativo, o texto
               saia com a mesma cor do fundo do balao e sumia. Fixamos
               balao escuro + texto claro sempre, igual ao tooltip
               customizado dos cards do farol (.farol-card[data-tip]). ---- */
        div[data-baseweb="tooltip"], [data-testid="stTooltipContent"] {{
            background-color: #0B1330 !important;
            border-radius: 8px !important;
        }}
        div[data-baseweb="tooltip"] *, [data-testid="stTooltipContent"] * {{
            color: #FFFFFF !important;
        }}

        /* ---- st.dialog nativo (modais de detalhamento): mesmo problema do
               tooltip acima -- o painel do modal e renderizado pelo chrome
               nativo do Streamlit (sempre tema claro), entao o fundo fica
               branco mesmo com o app em modo escuro, enquanto o texto interno
               (paragrafos/legendas/tabelas) ja segue o PAL via as regras
               "p, span, label" abaixo -- resultado: texto claro em fundo
               branco, ilegivel. Forcamos o fundo do painel a acompanhar o
               PAL da pagina. ---- */
        [data-testid="stDialog"] > div {{
            background-color: {PAL['surface']} !important;
        }}
        [data-testid="stDialog"] [aria-label="Close"] {{
            color: {PAL['muted']} !important;
        }}
        [data-testid="stDialog"] [aria-label="Close"]:hover {{
            color: {PAL['ink']} !important;
        }}

        /* ---- "Candidatos parados por etapa" (mesmo layout do mock):
               cards de resumo, tabela de chips clicaveis (status x etapa)
               e legenda de cores ---- */
        .stage-summary-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 10px 0 16px; }}
        .stage-summary-card {{
            display: flex; align-items: center; gap: 10px;
            background: {PAL['surface']}; border: 1px solid {PAL['line']};
            border-radius: 12px; padding: 10px 16px; box-shadow: 0 2px 8px {PAL['shadow']};
        }}
        .stage-summary-card .ssc-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
        .stage-summary-card .ssc-num {{
            font-family: 'Roboto Mono', monospace; font-weight: 700; font-size: 16px; color: {PAL['ink']};
        }}
        .stage-summary-card .ssc-lbl {{ font-size: 11.5px; color: {PAL['muted']}; }}

        .stage-th {{
            font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: .03em;
            color: {PAL['muted']}; line-height: 1.3; padding-bottom: 6px; min-height: 48px;
            border-bottom: 1px solid {PAL['line']};
        }}
        .stage-th .th-note {{
            display: block; font-size: 9.5px; font-weight: 400; text-transform: none;
            letter-spacing: 0; opacity: .75; margin-top: 3px;
        }}
        .status-row-label {{
            display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 13px;
            color: {PAL['ink']}; min-height: 38px;
        }}
        .status-row-label .dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}
        .stage-chip-empty {{
            text-align: center; color: {PAL['muted']}; opacity: .45; font-size: 13px;
            min-height: 38px; line-height: 38px;
        }}

        /* o marcador so existe para o :has() abaixo achar a coluna do chip --
           ele proprio fica escondido (mesma tecnica do botao de tema) */
        div[data-testid="stMarkdown"]:has(.chip-marker) {{ display: none; }}
        div[data-testid="column"]:has(.chip-marker) .stButton > button {{
            font-family: 'Roboto Mono', monospace; font-weight: 700; font-size: 13px;
            border-radius: 8px; border: none; min-height: 32px; padding: 2px 8px;
            transition: transform .12s ease, box-shadow .12s ease;
        }}
        div[data-testid="column"]:has(.chip-atencao) .stButton > button {{
            background: {STATUS_BG_BY_THEME[THEME]['manter']};
            color: {'#966006' if THEME == 'light' else '#FFD48A'};
        }}
        div[data-testid="column"]:has(.chip-critico) .stButton > button {{
            background: {STATUS_BG_BY_THEME[THEME]['pausar']};
            color: {'#B4262A' if THEME == 'light' else '#FFA8AB'};
        }}
        div[data-testid="column"]:has(.chip-marker) .stButton > button:hover {{
            transform: scale(1.07); box-shadow: 0 0 0 3px {PAL['shadow_hover']};
        }}

        .legend-row {{ display: flex; gap: 18px; flex-wrap: wrap; margin-top: 12px; }}
        .legend-item {{ display: flex; align-items: center; gap: 7px; font-size: 11.5px; color: {PAL['muted']}; }}
        .legend-dot {{ width: 9px; height: 9px; border-radius: 50%; flex-shrink: 0; }}

        /* ---- lista de candidatos dentro do modal ---- */
        .cand-item {{
            display: flex; align-items: center; justify-content: space-between; gap: 12px;
            padding: 10px 12px; border-radius: 10px; background: {PAL['surface2']}; margin-bottom: 8px;
        }}
        .cand-left {{ display: flex; align-items: center; gap: 10px; min-width: 0; }}
        .cand-avatar {{
            width: 32px; height: 32px; border-radius: 50%; flex-shrink: 0;
            background: {GRADIENT_CSS}; color: #fff; font-size: 11px; font-weight: 700;
            display: flex; align-items: center; justify-content: center;
        }}
        .cand-name {{ font-size: 13px; font-weight: 700; color: {PAL['ink']}; }}
        .cand-role {{ font-size: 11px; color: {PAL['muted']}; }}
        .cand-right {{ text-align: right; flex-shrink: 0; }}
        .cand-days {{ font-family: 'Roboto Mono', monospace; font-weight: 700; font-size: 14px; }}
        .cand-meta {{ font-size: 10.5px; color: {PAL['muted']}; }}

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

        /* ---- kpis executivos: cards de metrica agregada (aba Visao Gerencial) ---- */
        .exec-kpi-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 22px; }}
        .exec-kpi-card {{
            flex: 1 1 200px; background: {PAL['surface']}; border: 1px solid {PAL['line']}; border-radius: 14px;
            padding: 16px 18px; box-shadow: 0 2px 10px {PAL['shadow']};
        }}
        .exec-kpi-card .exec-kpi-label {{ font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: {PAL['muted']}; font-weight: 700; }}
        .exec-kpi-card .exec-kpi-value {{ font-family: 'Roboto Mono', monospace; font-size: 25px; font-weight: 700; color: {PAL['ink']}; margin-top: 6px; }}
        .exec-kpi-card .exec-kpi-delta {{ font-size: 12px; font-weight: 600; margin-top: 5px; }}
        .exec-kpi-card .exec-kpi-note {{ font-size: 11px; color: {PAL['muted']}; margin-top: 5px; line-height: 1.4; }}

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
# Autenticação (Google OAuth) + Autorização (allowlist) — gate principal.
# Autenticação != autorização: o Google resolve "quem é você", a allowlist em
# `greenhouse_dash_access` (BigQuery) resolve "você pode acessar". Enforcement
# no servidor via st.stop() dentro de auth.py — nada do dashboard abaixo desta
# linha é montado/enviado ao navegador se o usuário não passar nos dois.
# ---------------------------------------------------------------------------
_logo_html_sm = f'<img src="data:image/png;base64,{LOGO_B64}" style="height:34px;">' if LOGO_B64 else ""
CURRENT_USER = auth.require_login_and_authorization(PAL, GRADIENT_CSS, _logo_html_sm)

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
            Dados oficiais<br>
            <b>Greenhouse + Artefactory</b> (BigQuery)
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

_user_line = f"Conectado como **{CURRENT_USER['name']}** ({CURRENT_USER['email']})"
if CURRENT_USER.get("role"):
    _user_line += f" · perfil: {CURRENT_USER['role']}"
col_user, col_logout = st.columns([10, 1.4])
with col_user:
    st.caption(_user_line)
with col_logout:
    if auth._auth_configured() and st.button("Sair", key="logout_btn", use_container_width=True):
        st.logout()


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


_MES_PT = {1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr", 5: "Mai", 6: "Jun",
           7: "Jul", 8: "Ago", 9: "Set", 10: "Out", 11: "Nov", 12: "Dez"}


def _rotulo_mes(ym: str) -> str:
    """'2026-11' -> 'Nov/2026'."""
    ano, mes = str(ym)[:7].split("-")
    return f"{_MES_PT[int(mes)]}/{ano}"


def farol_status(demanda: float, oferta: float):
    """Semáforo a partir do gap entre demanda líquida e oferta ajustada.

    Demanda líquida NEGATIVA é um caso real: no mês corrente as
    desalocações costumam superar os pedidos novos. Não dá para calcular
    gap percentual em cima de denominador negativo (o sinal inverte e o
    farol diria 'acelerar' justamente quando sobra gente), então esse
    caso vira 'pausar' direto, sem percentual."""
    if demanda is None or pd.isna(demanda):
        return "sem_dado", None
    if demanda == 0:
        return "sem_dado", None
    if demanda < 0:
        return "pausar", None
    gap_pct = round((demanda - oferta) / demanda * 100, 1)
    if gap_pct > 20:
        return "acelerar", gap_pct
    if gap_pct >= -10:
        return "manter", gap_pct
    return "pausar", gap_pct


# ---------------------------------------------------------------------------
# Dados
# ---------------------------------------------------------------------------
PROJETO_BQ = "br-in-dataplatform"
DATASET_BQ = "greenhouse_dev"

# Horizonte do farol: o "~1,5 mês" definido no discovery. Um candidato só
# conta como oferta se a projeção disser que ele chega à contratação
# dentro desse prazo.
HORIZONTE_FAROL_DIAS = 45


@st.cache_data(ttl=1800, show_spinner="Lendo as views do BigQuery…")
def load_data():
    """Lê as duas views oficiais e deriva, em pandas, os recortes que cada
    tela usa. As views são duas porque são dois grãos e dois eixos de
    tempo: a demanda é forecast mensal (até 2027-12) e o pipe é foto de
    hoje — o Greenhouse não tem data em nenhuma view."""
    base = bq.consultar(f"SELECT * FROM {bq.tabela('vw_farol_base')}")
    demanda = bq.consultar(f"SELECT * FROM {bq.tabela('vw_farol_demanda')}")

    mes_snap = str(pd.to_datetime(base["snapshot_date"].iloc[0]).strftime("%Y-%m"))
    label_snap = _rotulo_mes(mes_snap)

    # "Contratação" não é etapa viva: quem está lá entra pelo flag_contratado
    base = base.copy()
    base["conta_funil"] = base["flag_ativo"].where(
        ~base["etapa"].eq("Contratação"), base["flag_contratado"]
    )
    funil = base[base["tipo_etapa"].eq("funil") & base["chapter"].notna()]

    # ---- funil por chapter × etapa -------------------------------------
    # a média de conversão e de tempo sai PONDERADA porque o grão da view é
    # a candidatura: cada linha já é um candidato daquela vaga/etapa
    pipe = (
        funil.groupby(["chapter", "etapa", "ordem_etapa"], as_index=False)
        .agg(
            candidatos=("conta_funil", "sum"),
            conversao_pct=("conversao_etapa_pct", "mean"),
            tempo_medio_dias=("tempo_medio_etapa", "mean"),
            meta_sla_dias=("meta_sla_etapa", "max"),
        )
    )
    pipe.loc[pipe["etapa"].eq("Contratação"), ["tempo_medio_dias", "meta_sla_dias"]] = None
    pipe["mes"], pipe["mes_label"] = mes_snap, label_snap
    pipe["conversao_pct"] = pipe["conversao_pct"].round(1)
    pipe["tempo_medio_dias"] = pipe["tempo_medio_dias"].round(1)
    pipe["excesso_dias"] = (pipe["tempo_medio_dias"] - pipe["meta_sla_dias"]).round(1)

    def _status_sla(excesso):
        if pd.isna(excesso):
            return None
        return "critico" if excesso > 5 else ("atencao" if excesso > 0 else "ok")

    pipe["status_sla"] = pipe["excesso_dias"].map(_status_sla)

    # ---- volume por senioridade ----------------------------------------
    pipe_nivel = (
        funil[funil["senioridade"].notna()]
        .groupby(["chapter", "senioridade", "etapa", "ordem_etapa"], as_index=False)
        .agg(candidatos=("conta_funil", "sum"))
    )
    pipe_nivel["mes"], pipe_nivel["mes_label"] = mes_snap, label_snap

    # ---- candidatos parados --------------------------------------------
    # dias_na_etapa aqui é o tempo no PIPE INTEIRO, e meta_sla_dias é o
    # tempo esperado até esta etapa — as views oficiais não têm tempo por
    # etapa por candidato. É proxy, e as telas dizem isso.
    parados = base[
        base["flag_ativo"].eq(1)
        & base["tipo_etapa"].eq("funil")
        & base["status_parado"].isin(["atencao", "critico"])
        & base["chapter"].notna()
    ].copy()
    parados = parados.rename(
        columns={
            "status_parado": "status",
            "total_days_in_pipe": "dias_na_etapa",
            "dias_esperados_ate_etapa": "meta_sla_dias",
        }
    )
    parados["mes"], parados["mes_label"] = mes_snap, label_snap

    # ---- See You Soon ---------------------------------------------------
    # su_*_vaga vem REPETIDO em cada candidatura da vaga: dedupe antes de somar
    por_vaga = base.drop_duplicates("job_id")
    su_ofertas = (
        por_vaga[por_vaga["chapter"].notna()]
        .groupby("chapter", as_index=False)
        .agg(ofertas_sys=("su_ofertas_vaga", "sum"), aceites_sys=("su_aceites_vaga", "sum"))
    )
    su_ofertas["mes"], su_ofertas["mes_label"] = mes_snap, label_snap

    su_banco = base[base["flag_see_you_soon"].eq(1)][
        ["candidato", "chapter", "senioridade", "su_dias_no_banco_vaga"]
    ].copy()
    su_banco = su_banco.rename(columns={"su_dias_no_banco_vaga": "dias_no_banco"})
    su_banco["status"] = "aguardando"

    # ---- farol: demanda líquida × oferta ajustada -----------------------
    demanda = demanda.rename(columns={"demanda_liquida_fte": "demanda_liquida"})
    oferta = (
        base[
            base["flag_ativo"].eq(1)
            & base["dias_ate_contratacao"].le(HORIZONTE_FAROL_DIAS)
            & base["chapter"].notna()
        ]
        .groupby(["chapter", "senioridade"], as_index=False)
        .agg(oferta_ajustada=("contrib_oferta_ajustada", "sum"))
    )
    farol = demanda.merge(oferta, on=["chapter", "senioridade"], how="left")
    farol["oferta_ajustada"] = farol["oferta_ajustada"].fillna(0.0).round(1)
    farol["gap"] = (farol["demanda_liquida"] - farol["oferta_ajustada"]).round(1)
    calculado = farol.apply(
        lambda r: farol_status(r["demanda_liquida"], r["oferta_ajustada"]), axis=1
    )
    farol["farol_status"] = [c[0] for c in calculado]
    farol["gap_pct"] = [c[1] for c in calculado]
    farol["mes_label"] = farol["mes"].map(_rotulo_mes)

    return farol, pipe, pipe_nivel, su_ofertas, su_banco, parados, mes_snap


try:
    (farol_df, pipe_df, pipe_nivel_df, su_ofertas_df, su_banco_df,
     parados_df, MES_SNAPSHOT) = load_data()
except Exception as e:  # noqa: BLE001 — qualquer falha de BigQuery/credencial
    _detalhe = str(e)
    # o erro de metadata server é o jeito do google-auth dizer "não achei
    # credencial nenhuma": ele tenta o último recurso, que só existe dentro
    # do GCP, e o timeout vaza como se fosse problema de rede
    _sem_credencial = (
        "metadata.google.internal" in _detalhe
        or "could not automatically determine credentials" in _detalhe.lower()
        or "default credentials" in _detalhe.lower()
    )
    # biblioteca faltando não é problema de permissão nem de credencial, mas o
    # erro ("cannot import name 'bigquery' from 'google.cloud'") parece um:
    # google.cloud é namespace package, então importar o que não está
    # instalado dá ImportError em vez de ModuleNotFoundError
    _falta_lib = isinstance(e, ImportError) or "from 'google.cloud'" in _detalhe
    if _falta_lib:
        st.error(
            "**Falta instalar a biblioteca do BigQuery neste ambiente.**\n\n"
            "Não é permissão nem credencial: o Python não encontrou o pacote.\n\n"
            "No terminal, na pasta do projeto:\n\n"
            "```\npip install -r requirements.txt\n```\n\n"
            "Se o erro continuar, provavelmente existe um pacote chamado só "
            "`google` instalado, que quebra o namespace `google.cloud`:\n\n"
            "```\npip uninstall google\npip install --force-reinstall "
            "google-cloud-bigquery db-dtypes\n```\n\n"
            f"Detalhe técnico: {e}"
        )
    elif _sem_credencial:
        st.error(
            "**Não há credencial do Google configurada nesta máquina.**\n\n"
            "O erro de *metadata server* abaixo é o google-auth tentando o último "
            "recurso, que só existe dentro do GCP — não é problema de rede.\n\n"
            "Duas formas de resolver, qualquer uma serve:\n\n"
            "1. **Na sua máquina:** `gcloud auth application-default login` "
            "(precisa do Google Cloud SDK instalado).\n"
            "2. **Sem gcloud, ou para publicar o app:** peça uma service account "
            "com leitura no dataset e cole o JSON dela em "
            "`.streamlit/secrets.toml`, sob `[gcp_service_account]` — o modelo "
            "está em `.streamlit/secrets.toml.example`.\n\n"
            f"Detalhe técnico: {e}"
        )
    else:
        st.error(
            "Credencial encontrada, mas não consegui ler as views "
            f"`{PROJETO_BQ}.{DATASET_BQ}.vw_farol_base` e `vw_farol_demanda`.\n\n"
            "Normalmente é falta de permissão de leitura no dataset, ou as views "
            "ainda não foram criadas (ver a pasta `sql/`).\n\n"
            f"Detalhe: {e}"
        )
    st.stop()

# Dois eixos de tempo. MESES vem da DEMANDA (forecast); o pipe é sempre a
# foto de hoje (MES_SNAPSHOT), porque nenhuma view do Greenhouse tem data.
MES_LABELS = farol_df.drop_duplicates("mes").set_index("mes")["mes_label"].to_dict()
MES_LABELS.setdefault(MES_SNAPSHOT, _rotulo_mes(MES_SNAPSHOT))
MESES = sorted(m for m in MES_LABELS if m in set(farol_df["mes"]))

# Aviso de escopo calculado do próprio dado, para não envelhecer: diz de
# quando é a foto do pipe, até onde vai o forecast, e quais chapters têm
# pipe mas não têm demanda cadastrada (esses não têm farol).
_sem_demanda = sorted(set(pipe_df["chapter"].dropna()) - set(farol_df["chapter"].dropna()))
_aviso = (
    f"Dados oficiais do BigQuery. Pipe: foto de <b>{MES_LABELS[MES_SNAPSHOT]}</b> — nenhuma "
    "view do Greenhouse tem data, então o funil não tem histórico. Demanda: forecast de "
    f"<b>{MES_LABELS[MESES[0]]}</b> a <b>{MES_LABELS[MESES[-1]]}</b>."
)
if _sem_demanda:
    _aviso += (
        f" Sem demanda cadastrada no Artefactory: <b>{', '.join(_sem_demanda)}</b> — "
        "esses chapters aparecem no funil, mas não têm farol."
    )
render_note(_aviso, variant="neutral")


def gap_trend(chapter: str, senioridade: str) -> list:
    hist = farol_df[(farol_df["chapter"] == chapter) & (farol_df["senioridade"] == senioridade)].sort_values("mes")
    return hist["gap_pct"].tolist()


def pipe_trend(chapter: str, etapa: str, col: str = "tempo_medio_dias") -> list:
    hist = pipe_df[(pipe_df["chapter"] == chapter) & (pipe_df["etapa"] == etapa)].sort_values("mes")
    return hist[col].tolist()


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


# etapas do pipe que já passaram da triagem inicial mas ainda não viraram
# contratação — "pipe qualificado" no sentido usado no mock de referência
# (a partir da Entrevista Fit, até a decisão final de Oferta).
# Deliberadamente NÃO inclui as duas etapas do case: "qualificado" aqui é
# quem já passou da triagem E do case, que é o estoque com chance real de
# cobrir demanda no horizonte do farol. Se o STF quiser contar o case,
# acrescentar as duas etapas aqui.
QUALIFIED_STAGES = [
    "Entrevista Fit", "Entrevista Técnica 1", "Entrevista Técnica 2", "Conversa Final", "Oferta",
]


# NOTA: as funções abaixo recebem `mes` por compatibilidade com as telas,
# mas IGNORAM o valor e leem sempre MES_SNAPSHOT. O pipe do Greenhouse não
# tem data: é foto de hoje. Só a demanda (farol_df) varia por mês.
def pipe_qualificado(mes: str, chapter: str | None = None) -> int:
    """Quantos candidatos já passaram do currículo e ainda estão vivos no processo
    (Entrevista Fit até Oferta) — o estoque qualificado disponível para cobrir
    a demanda deste mês, sem contar quem ainda está só na triagem de currículo."""
    df = pipe_df[(pipe_df["mes"] == MES_SNAPSHOT) & (pipe_df["etapa"].isin(QUALIFIED_STAGES))]
    if chapter:
        df = df[df["chapter"] == chapter]
    return int(df["candidatos"].sum())


def taxa_aceite_oferta(mes: str, chapter: str | None = None) -> float | None:
    """% de ofertas enviadas que viraram contratação (Oferta -> Contratação)."""
    df = pipe_df[pipe_df["mes"] == MES_SNAPSHOT]
    if chapter:
        df = df[df["chapter"] == chapter]
    ofertas = df[df["etapa"] == "Oferta"]["candidatos"].sum()
    contratacoes = df[df["etapa"] == "Contratação"]["candidatos"].sum()
    if not ofertas:
        return None
    return contratacoes / ofertas * 100


def tempo_medio_contratacao(mes: str) -> float | None:
    """Soma do tempo médio (dias) de cada etapa do funil, com a média entre
    chapters em cada etapa — leitura ponta a ponta de currículo até contratação."""
    df = pipe_df[(pipe_df["mes"] == MES_SNAPSHOT) & (pipe_df["tempo_medio_dias"].notna())]
    if df.empty:
        return None
    return df.groupby("etapa")["tempo_medio_dias"].mean().sum()


def mes_anterior(mes: str) -> str | None:
    idx = MESES.index(mes)
    return MESES[idx - 1] if idx > 0 else None


def conversao_total_pipe(mes: str) -> float | None:
    """% do volume inicial de currículos que termina em contratação, somando
    todos os chapters — a eficiência ponta a ponta do funil no mês."""
    df = pipe_df[pipe_df["mes"] == MES_SNAPSHOT]
    curriculos = df[df["etapa"] == "Avaliação de currículo"]["candidatos"].sum()
    contratacoes = df[df["etapa"] == "Contratação"]["candidatos"].sum()
    if not curriculos:
        return None
    return contratacoes / curriculos * 100


def taxa_aceite_sys(mes: str, chapter: str | None = None) -> float | None:
    """% de ofertas feitas a candidatos do banco See You Soon que viraram
    contratação, neste mês (fonte: su_ofertas.csv)."""
    if su_ofertas_df.empty:
        return None
    df = su_ofertas_df[su_ofertas_df["mes"] == MES_SNAPSHOT]
    if chapter:
        df = df[df["chapter"] == chapter]
    ofertas = df["ofertas_sys"].sum()
    aceites = df["aceites_sys"].sum()
    if not ofertas:
        return None
    return aceites / ofertas * 100


def su_tempo_medio_banco() -> float | None:
    """Tempo médio (dias) que os candidatos hoje 'aguardando' no banco See You
    Soon já estão parados — foto do estoque atual (su_banco_talentos.csv não
    tem grão mensal, é um snapshot do presente)."""
    if su_banco_df.empty:
        return None
    ativos = su_banco_df[su_banco_df["status"] == "aguardando"]
    if ativos.empty:
        return None
    return float(ativos["dias_no_banco"].mean())


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


def chart_hint(text: str) -> None:
    """Mini legenda abaixo de um grafico com modal de detalhamento --
    reproduz o `.chart-hint` do mock visual (texto pequeno, cor muted,
    icone de "clique"), para deixar claro que aquele grafico e clicavel."""
    icon = (
        f"<svg width=\"13\" height=\"13\" viewBox=\"0 0 24 24\" fill=\"none\" "
        f"stroke=\"{PAL['muted']}\" stroke-width=\"2\" stroke-linecap=\"round\" "
        f"stroke-linejoin=\"round\" style=\"flex-shrink:0;\">"
        f"<path d=\"M3 3l7.07 16.97 2.51-7.39 7.39-2.51z\"/><path d=\"M13 13l6 6\"/></svg>"
    )
    st.markdown(
        f"<div style=\"font-size:11.5px;color:{PAL['muted']};margin-top:6px;"
        f"display:flex;align-items:center;gap:6px;\">{icon}{text}</div>",
        unsafe_allow_html=True,
    )


def brand_heat_scale() -> list:
    return [[0.0, PAL["heat_low"]], [0.35, "#8B93C7"], [0.65, ARTEFACT_BLUE], [1.0, PINK]]


def _clicked_category(event, axis: str = "y"):
    """Extrai a categoria (etapa) clicada num gráfico de barras do Plotly via
    st.plotly_chart(..., on_select="rerun"). Retorna None se nada foi clicado
    nesta execução do script."""
    if not event:
        return None
    points = event.get("selection", {}).get("points", [])
    if not points:
        return None
    return points[0].get(axis)


@st.dialog("Detalhamento por carreira")
def show_conv_drilldown(etapa: str, mes: str) -> None:
    st.markdown(f"#### {etapa}")
    st.caption(f"% de candidatos que avançam nesta etapa, por chapter — {MES_LABELS[mes]}.")
    df = pipe_df[(pipe_df["mes"] == MES_SNAPSHOT) & (pipe_df["etapa"] == etapa)].dropna(subset=["conversao_pct"]).copy()
    if df.empty:
        render_note("Sem dado de conversão para esta etapa neste mês.", variant="neutral")
        return
    df = df.sort_values("conversao_pct", ascending=False)
    media = df["conversao_pct"].mean()
    melhor, pior = df.iloc[0], df.iloc[-1]
    st.caption(
        f"Média entre chapters: **{media:.0f}%** · Melhor: **{melhor['chapter']}** ({melhor['conversao_pct']:.0f}%) "
        f"· Menor: **{pior['chapter']}** ({pior['conversao_pct']:.0f}%)"
    )
    tbl = df[["chapter", "conversao_pct"]].rename(columns={"chapter": "Chapter", "conversao_pct": "Conversão"})
    tbl["Conversão"] = tbl["Conversão"].map(lambda v: f"{v:.0f}%")
    render_table(tbl, numeric_cols={"Conversão"})


@st.dialog("Detalhamento por carreira")
def show_tempo_drilldown(etapa: str, mes: str) -> None:
    st.markdown(f"#### {etapa}")
    st.caption(f"Tempo médio (dias corridos) nesta etapa, por chapter — {MES_LABELS[mes]}.")
    df = pipe_df[(pipe_df["mes"] == MES_SNAPSHOT) & (pipe_df["etapa"] == etapa)].dropna(subset=["tempo_medio_dias"]).copy()
    if df.empty:
        render_note("Sem dado de tempo para esta etapa neste mês.", variant="neutral")
        return
    df = df.sort_values("tempo_medio_dias", ascending=False)
    media = df["tempo_medio_dias"].mean()
    mais_lento, mais_rapido = df.iloc[0], df.iloc[-1]
    st.caption(
        f"Média entre chapters: **{media:.1f} dias** · Mais lento: **{mais_lento['chapter']}** "
        f"({mais_lento['tempo_medio_dias']:.1f}d) · Mais rápido: **{mais_rapido['chapter']}** "
        f"({mais_rapido['tempo_medio_dias']:.1f}d)"
    )
    tbl = df[["chapter", "tempo_medio_dias"]].rename(
        columns={"chapter": "Chapter", "tempo_medio_dias": "Tempo médio (dias)"}
    )
    tbl["Tempo médio (dias)"] = tbl["Tempo médio (dias)"].map(lambda v: f"{v:.1f}")
    render_table(tbl, numeric_cols={"Tempo médio (dias)"})


def _parados_no_mes(mes: str, etapa: str = None, status_key: str = None, vaga: str = None):
    """Recorte do candidatos_parados.csv (quem está parado em cada etapa)."""
    df = parados_df[parados_df["mes"] == MES_SNAPSHOT]
    if etapa is not None:
        df = df[df["etapa"] == etapa]
    if status_key is not None:
        df = df[df["status"] == status_key]
    if vaga is not None:
        df = df[df["vaga"] == vaga]
    return df


def _abrir_parados(etapa: str, status_key: str, vaga=None) -> None:
    """Guarda o recorte escolhido e pede a reabertura do modal no próximo run
    (o Streamlit não permite abrir um dialog de dentro de outro)."""
    st.session_state["_parados_sel"] = {"etapa": etapa, "status": status_key, "vaga": vaga}
    st.session_state["_parados_reabrir"] = True


@st.dialog("Candidatos parados — por vaga")
def show_parados_vagas(etapa: str, status_key: str, mes: str) -> None:
    status_label = "Crítico" if status_key == "critico" else "Atenção"
    df = _parados_no_mes(mes, etapa, status_key)
    st.markdown(f"#### {etapa} · {status_label}")
    if df.empty:
        render_note("Nenhum candidato parado neste recorte.", variant="neutral")
        return
    st.caption(
        f"{len(df)} candidato(s) parado(s) em \"{status_label.lower()}\" nesta etapa em "
        f"{MES_LABELS[mes]}. Clique em uma vaga para ver quem são."
    )
    por_vaga = (
        df.groupby(["vaga"], as_index=False)
        .agg(qtd=("candidato", "size"), pior=("dias_na_etapa", "max"))
        .sort_values("qtd", ascending=False)
    )
    for i, row in enumerate(por_vaga.itertuples(index=False)):
        rotulo = f"{row.vaga}  —  {row.qtd} candidato(s), até {row.pior:.0f}d no pipe"
        if st.button(rotulo, key=f"parados_vaga_{status_key}_{i}", use_container_width=True):
            _abrir_parados(etapa, status_key, row.vaga)
            st.rerun()


@st.dialog("Candidatos parados — quem está parado")
def show_parados_candidatos(etapa: str, status_key: str, vaga: str, mes: str) -> None:
    status_label = "Crítico" if status_key == "critico" else "Atenção"
    df = _parados_no_mes(mes, etapa, status_key, vaga).sort_values("dias_na_etapa", ascending=False)
    st.markdown(f"#### {vaga}")
    if df.empty:
        render_note("Nenhum candidato parado nesta vaga.", variant="neutral")
        return
    st.caption(
        f"{len(df)} candidato(s) parado(s) em \"{etapa}\" · {status_label} — {MES_LABELS[mes]}."
    )
    cor = RED if status_key == "critico" else AMBER
    itens = []
    for row in df.itertuples(index=False):
        iniciais = "".join(parte[0] for parte in str(row.candidato).split()[:2]).upper()
        itens.append(
            f'<div class="cand-item">'
            f'<div class="cand-left"><div class="cand-avatar">{iniciais}</div>'
            f'<div><div class="cand-name">{row.candidato}</div>'
            f'<div class="cand-role">{row.chapter} · {row.senioridade}</div></div></div>'
            f'<div class="cand-right"><div class="cand-days" style="color:{cor}">{row.dias_na_etapa:.0f}d</div>'
            f'<div class="cand-meta">esperado {row.meta_sla_dias:.0f}d</div></div>'
            f"</div>"
        )
    st.markdown("".join(itens), unsafe_allow_html=True)
    if st.button("‹ Voltar para as vagas", key=f"parados_voltar_{status_key}"):
        _abrir_parados(etapa, status_key, None)
        st.rerun()


CHART_LAYOUT = dict(
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor=PAL["surface"],
    paper_bgcolor=PAL["surface"],
    font=dict(family="Roboto, sans-serif", color=PAL["ink"], size=13),
    hoverlabel=dict(bgcolor=PAL["surface"], font_size=12.5, font_family="Roboto, sans-serif", font_color=PAL["ink"]),
    xaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
    yaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
)

tab_exec, tab_farol, tab_pipe = st.tabs(["Visão Gerencial", "Farol Executivo", "Visão do Pipe"])

# ---------------------------------------------------------------------------
# TAB 0 — VISÃO GERENCIAL
# ---------------------------------------------------------------------------
with tab_exec:
    st.markdown("## 🧭 Visão Gerencial")
    st.caption(
        "Resumo executivo do mês: quanto falta contratar, quanto pipe qualificado já existe para "
        "cobrir essa necessidade, e quão rápido e eficiente está o funil — antes de entrar no "
        "detalhe por chapter (aba Farol Executivo) ou por etapa (aba Visão do Pipe)."
    )

    mes_sel0 = st.selectbox(
        "Mês de referência", MESES, index=len(MESES) - 1, format_func=lambda m: MES_LABELS[m], key="mes_exec"
    )
    mes_ant0 = mes_anterior(mes_sel0)

    df_mes0 = farol_df[farol_df["mes"] == mes_sel0]
    farol_chapters = sorted(farol_df["chapter"].unique())
    demanda_total = float(df_mes0["demanda_liquida"].sum())
    pipe_qual_total = sum(pipe_qualificado(mes_sel0, ch) for ch in farol_chapters)
    tempo_total = tempo_medio_contratacao(mes_sel0)
    aceite_total = taxa_aceite_oferta(mes_sel0)

    # só a demanda tem série mensal; os KPIs de pipe são foto de hoje e
    # portanto não têm "mês anterior" para comparar
    demanda_ant = float(farol_df[farol_df["mes"] == mes_ant0]["demanda_liquida"].sum()) if mes_ant0 else None
    pipe_qual_ant = None
    tempo_ant = None
    aceite_ant = None

    def _delta_html(atual, anterior, melhora_se_sobe, fmt, suffix=""):
        if atual is None or anterior is None or mes_ant0 is None:
            return ""
        diff = atual - anterior
        arrow = "↑" if diff >= 0 else "↓"
        if melhora_se_sobe is None:
            color = PAL["muted"]
        else:
            se_bom = (diff >= 0) if melhora_se_sobe else (diff <= 0)
            color = GREEN if se_bom else RED
        return f'<div class="exec-kpi-delta" style="color:{color}">{arrow} {fmt.format(abs(diff))}{suffix} vs. {MES_LABELS[mes_ant0]}</div>'

    kpi_cards = [
        (
            "Necessidade de contratação líquida",
            f"{demanda_total:.0f}",
            _delta_html(demanda_total, demanda_ant, None, "{:.0f}", " pessoas"),
            "Soma da demanda líquida (Artefactory) de todos os chapters neste mês.",
        ),
        (
            "Pipe qualificado atual",
            f"{pipe_qual_total:.0f}",
            _delta_html(pipe_qual_total, pipe_qual_ant, True, "{:.0f}", " candidatos"),
            "Candidatos da Entrevista Fit até a Oferta, somando os chapters com demanda cadastrada — quem já passou da triagem inicial.",
        ),
        (
            "Tempo médio de contratação",
            f"{tempo_total:.0f} dias" if tempo_total is not None else "—",
            _delta_html(tempo_total, tempo_ant, False, "{:.0f}", " dias"),
            "Soma do tempo médio de cada etapa do funil, do envio do currículo até a contratação.",
        ),
        (
            "Taxa de aceite de oferta",
            f"{aceite_total:.0f}%" if aceite_total is not None else "—",
            _delta_html(aceite_total, aceite_ant, True, "{:.0f}", "pp"),
            "% de ofertas enviadas que viraram contratação, somando todos os chapters.",
        ),
    ]
    st.markdown(
        '<div class="exec-kpi-row">'
        + "".join(
            f'<div class="exec-kpi-card"><div class="exec-kpi-label">{label}</div>'
            f'<div class="exec-kpi-value">{value}</div>{delta}'
            f'<div class="exec-kpi-note">{note}</div></div>'
            for label, value, delta, note in kpi_cards
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    agg0 = (
        df_mes0.groupby("chapter", as_index=False)
        .agg(demanda=("demanda_liquida", "sum"), oferta=("oferta_ajustada", "sum"))
    )
    stat0 = agg0.apply(lambda r: farol_status(r["demanda"], r["oferta"]), axis=1, result_type="expand")
    agg0["status"] = stat0[0]
    n_acel0, n_pausa0 = int((agg0["status"] == "acelerar").sum()), int((agg0["status"] == "pausar").sum())
    render_finding(
        f"Em <b>{MES_LABELS[mes_sel0]}</b>: necessidade líquida de <b>{demanda_total:.0f} pessoas</b>, "
        f"com <b>{pipe_qual_total:.0f} candidatos</b> já qualificados no pipe (a partir da Fit) — "
        f"<b>{n_acel0} chapter(s)</b> pedindo para acelerar e <b>{n_pausa0}</b> para pausar. "
        "Veja o detalhe por chapter na aba <b>Farol Executivo</b>."
    )

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
        "Passe o mouse sobre um card para o motivo do status, ou clique em **Ver detalhe** para a quebra por senioridade. "
        "\"Pipe qualificado\" soma os candidatos deste chapter da Entrevista Fit até a Oferta, neste mês."
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
                        Demanda: <b>{row['demanda']:.0f}</b> · Oferta: <b>{row['oferta']:.1f}</b><br>
                        Pipe qualificado: <b>{pipe_qualificado(mes_sel, row['chapter'])}</b>
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

    # Sem seletor de mês aqui de propósito: nenhuma view do Greenhouse tem
    # data, então o funil é sempre a foto de hoje. O seletor de mês existe
    # só nas abas que leem a demanda (Visão Gerencial e Farol Executivo).
    mes_sel2 = MES_SNAPSHOT
    chapters_pipe = sorted(pipe_df["chapter"].unique())
    chapter_sel2 = st.selectbox("Chapter (funil e conversão)", chapters_pipe, key="chapter_pipe")
    st.caption(f"📷 Foto do pipe em **{MES_LABELS[MES_SNAPSHOT]}** — o Greenhouse não guarda histórico por etapa.")

    dfp_mes = pipe_df[pipe_df["mes"] == mes_sel2]
    dfp_chapter = dfp_mes[dfp_mes["chapter"] == chapter_sel2].sort_values("ordem_etapa")

    mes_ant2 = None  # foto de hoje: não há mês anterior de pipe para comparar
    conversao_total = conversao_total_pipe(mes_sel2)
    aceite_geral_mes = taxa_aceite_oferta(mes_sel2)
    aceite_sys_mes = taxa_aceite_sys(mes_sel2)
    su_tempo_banco = su_tempo_medio_banco()
    conversao_ant = conversao_total_pipe(mes_ant2) if mes_ant2 else None
    aceite_geral_ant = taxa_aceite_oferta(mes_ant2) if mes_ant2 else None
    aceite_sys_ant = taxa_aceite_sys(mes_ant2) if mes_ant2 else None

    def _delta_pipe(atual, anterior, mes_ref):
        if atual is None or anterior is None or mes_ref is None:
            return ""
        diff = atual - anterior
        arrow = "↑" if diff >= 0 else "↓"
        color = GREEN if diff >= 0 else RED
        return f'<div class="exec-kpi-delta" style="color:{color}">{arrow} {abs(diff):.0f}pp vs. {MES_LABELS[mes_ref]}</div>'

    pipe_kpi_cards = [
        (
            "Conversão total do pipe",
            f"{conversao_total:.1f}%" if conversao_total is not None else "—",
            _delta_pipe(conversao_total, conversao_ant, mes_ant2),
            "Contratações / total de currículos recebidos, somando todos os chapters.",
        ),
        (
            "Taxa de aceite de oferta (Geral)",
            f"{aceite_geral_mes:.0f}%" if aceite_geral_mes is not None else "—",
            _delta_pipe(aceite_geral_mes, aceite_geral_ant, mes_ant2),
            "Ofertas aceitas / ofertas enviadas, somando todos os chapters.",
        ),
        (
            "Taxa de aceite — See You Soon",
            f"{aceite_sys_mes:.0f}%" if aceite_sys_mes is not None else "—",
            _delta_pipe(aceite_sys_mes, aceite_sys_ant, mes_ant2),
            "Ofertas aceitas / ofertas enviadas a candidatos do banco See You Soon.",
        ),
        (
            "See You Soon — tempo médio no banco",
            f"{su_tempo_banco:.0f} dias" if su_tempo_banco is not None else "—",
            "",
            "Média de dias que os candidatos hoje \"aguardando\" já estão no banco (foto atual do estoque).",
        ),
    ]
    st.markdown(
        '<div class="exec-kpi-row">'
        + "".join(
            f'<div class="exec-kpi-card"><div class="exec-kpi-label">{label}</div>'
            f'<div class="exec-kpi-value">{value}</div>{delta}'
            f'<div class="exec-kpi-note">{note}</div></div>'
            for label, value, delta, note in pipe_kpi_cards
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    sla_calc = dfp_mes.dropna(subset=["excesso_dias"])
    n_crit_pipe = int((sla_calc["status_sla"] == "critico").sum())
    partes_pipe = []
    if n_crit_pipe:
        top_gargalo_calc = sla_calc.sort_values("excesso_dias", ascending=False).iloc[0]
        partes_pipe.append(
            f"<b>{n_crit_pipe} etapa(s) em SLA crítico</b> — a pior é <b>{top_gargalo_calc['etapa']}</b> em {top_gargalo_calc['chapter']} "
            f"({top_gargalo_calc['tempo_medio_dias']:.0f}d vs. meta de {top_gargalo_calc['meta_sla_dias']:.0f}d)"
        )
    else:
        partes_pipe.append("Nenhuma etapa em SLA crítico neste mês")
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
        st.caption(
            "% de candidatos que avançam de uma etapa para a próxima — mostra onde a eficiência do processo é pior. "
            "A última barra (Oferta → Contratação) é a taxa de aceite de oferta."
        )
        conv = dfp_chapter.dropna(subset=["conversao_pct"])
        bar_colors = [PINK if et == "Contratação" else ARTEFACT_BLUE for et in conv["etapa"]]
        fig_conv = go.Figure(
            go.Bar(
                y=conv["etapa"],
                x=conv["conversao_pct"].astype(float),
                orientation="h",
                marker_color=bar_colors,
                text=conv["conversao_pct"].astype(float).map(lambda v: f"{v:.0f}%"),
                textposition="outside",
                hovertemplate="<b>%{y}</b><br>Conversão: <b>%{x:.0f}%</b> vieram da etapa anterior<extra></extra>",
            )
        )
        fig_conv.update_layout(
            height=380, xaxis_title="% que avança da etapa anterior", clickmode="event+select", **CHART_LAYOUT
        )
        conv_event = st.plotly_chart(
            fig_conv, use_container_width=True, on_select="rerun", selection_mode="points", key="conv_chart_sel"
        )
        chart_hint("Clique em uma barra para comparar essa etapa entre todos os chapters.")
        aceite_chapter = taxa_aceite_oferta(mes_sel2, chapter_sel2)
        if aceite_chapter is not None:
            st.caption(f"🔑 Taxa de aceite de oferta em **{chapter_sel2}** neste mês: **{aceite_chapter:.0f}%**")

        etapa_click_conv = _clicked_category(conv_event)
        guard_conv = f"{mes_sel2}|{etapa_click_conv}"
        if not etapa_click_conv:
            # seleção limpa (clique fora da barra): libera a mesma barra para
            # abrir o modal de novo no próximo clique
            st.session_state.pop("_last_conv_click", None)
        elif st.session_state.get("_last_conv_click") != guard_conv:
            st.session_state["_last_conv_click"] = guard_conv
            show_conv_drilldown(etapa_click_conv, mes_sel2)

    col_ag, col_as = st.columns(2)
    with col_ag:
        st.markdown("##### Taxa de aceite de oferta por carreira (Geral)")
        st.caption("Percentual de ofertas aceitas por chapter, neste mês.")
        chapters_aceite = sorted(farol_df["chapter"].unique())
        aceite_vals = [taxa_aceite_oferta(mes_sel2, ch) for ch in chapters_aceite]
        fig_aceite_geral = go.Figure(
            go.Bar(
                x=chapters_aceite,
                y=[v if v is not None else 0 for v in aceite_vals],
                marker_color=ARTEFACT_BLUE,
                text=[f"{v:.0f}%" if v is not None else "—" for v in aceite_vals],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Aceite geral: <b>%{y:.0f}%</b><extra></extra>",
            )
        )
        fig_aceite_geral.update_layout(
            height=300,
            yaxis=dict(range=[0, 100], **CHART_LAYOUT["yaxis"]),
            **{k: v for k, v in CHART_LAYOUT.items() if k != "yaxis"},
        )
        st.plotly_chart(fig_aceite_geral, use_container_width=True)

    with col_as:
        st.markdown("##### Taxa de aceite — See You Soon por carreira")
        st.caption("Percentual de ofertas aceitas vindas do banco See You Soon, por chapter, neste mês.")
        chapters_sys = sorted(su_ofertas_df["chapter"].unique()) if not su_ofertas_df.empty else []
        if chapters_sys:
            aceite_sys_vals = [taxa_aceite_sys(mes_sel2, ch) for ch in chapters_sys]
            fig_aceite_sys = go.Figure(
                go.Bar(
                    x=chapters_sys,
                    y=[v if v is not None else 0 for v in aceite_sys_vals],
                    marker_color=PINK,
                    text=[f"{v:.0f}%" if v is not None else "—" for v in aceite_sys_vals],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>Aceite SYS: <b>%{y:.0f}%</b><extra></extra>",
                )
            )
            fig_aceite_sys.update_layout(
                height=300,
                yaxis=dict(range=[0, 100], **CHART_LAYOUT["yaxis"]),
                **{k: v for k, v in CHART_LAYOUT.items() if k != "yaxis"},
            )
            st.plotly_chart(fig_aceite_sys, use_container_width=True)
        else:
            render_note("Sem dado de ofertas do banco See You Soon.", variant="neutral")

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

    st.markdown("##### Volume de candidatos por etapa e por nível")
    st.caption(
        "O heatmap acima cobre os 6 chapters do Greenhouse; aqui o recorte é por senioridade e limitado aos "
        "4 chapters com demanda cadastrada no Artefactory (Software Engineering e AI Engineering entram "
        "dentro de Data Engineering na Visão Gerencial e no Farol Executivo). 🔺 marca combinações com "
        "volume bem acima do normal para aquela etapa neste mês."
    )
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        carreira_filtro = st.selectbox(
            "Carreira", ["Todas"] + sorted(pipe_nivel_df["chapter"].unique()), key="filtro_carreira_nivel"
        )
    with col_f2:
        senioridade_filtro = st.selectbox(
            "Senioridade", ["Todas"] + SENIORIDADE_ORDER, key="filtro_senioridade_nivel"
        )

    nivel_mes = pipe_nivel_df[pipe_nivel_df["mes"] == mes_sel2].copy()
    if carreira_filtro != "Todas":
        nivel_mes = nivel_mes[nivel_mes["chapter"] == carreira_filtro]
    if senioridade_filtro != "Todas":
        nivel_mes = nivel_mes[nivel_mes["senioridade"] == senioridade_filtro]

    if nivel_mes.empty:
        render_note("Sem dado de volume por nível para este recorte.", variant="neutral")
    else:
        pivot_nivel = nivel_mes.pivot_table(
            index=["chapter", "senioridade"], columns="etapa", values="candidatos", aggfunc="sum"
        )
        etapa_cols = [s for s in STAGES_ORDER if s in pivot_nivel.columns]
        pivot_nivel = pivot_nivel[etapa_cols]

        thresholds = {}
        for et in etapa_cols:
            col_vals = pivot_nivel[et].dropna()
            media, desvio = col_vals.mean(), col_vals.std(ddof=0)
            thresholds[et] = media + 1.5 * desvio if desvio and pd.notna(desvio) else media * 1.5

        table_rows = []
        for (chapter, senioridade), vals in pivot_nivel.iterrows():
            row = {"Chapter": chapter, "Senioridade": senioridade}
            for et in etapa_cols:
                v = vals[et]
                if pd.isna(v):
                    row[et] = "—"
                else:
                    v = int(v)
                    flag = " 🔺" if v >= 5 and v > thresholds[et] else ""
                    row[et] = f"{v}{flag}"
            table_rows.append(row)
        tabela_nivel = pd.DataFrame(table_rows)
        render_table(tabela_nivel, numeric_cols=set(etapa_cols))

    st.markdown("##### Tempo médio por etapa (todos os chapters)")
    st.caption("Dias corridos que um candidato permanece em cada etapa — média entre os chapters, neste mês.")
    tempo_agg = (
        dfp_mes.dropna(subset=["tempo_medio_dias"])
        .groupby("etapa", as_index=False)["tempo_medio_dias"].mean()
    )
    tempo_agg["ordem_etapa"] = tempo_agg["etapa"].map(
        {s: i for i, s in enumerate(STAGES_ORDER)}
    )
    tempo_agg = tempo_agg.sort_values("ordem_etapa")
    if tempo_agg.empty:
        render_note("Sem dado de tempo médio para este mês.", variant="neutral")
    else:
        fig_tempo_agg = go.Figure(
            go.Bar(
                x=tempo_agg["etapa"],
                y=tempo_agg["tempo_medio_dias"],
                marker_color=ARTEFACT_BLUE,
                text=tempo_agg["tempo_medio_dias"].map(lambda v: f"{v:.1f}d"),
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Tempo médio: <b>%{y:.1f} dias</b><extra></extra>",
            )
        )
        fig_tempo_agg.update_layout(
            height=320, yaxis_title="Dias corridos", clickmode="event+select", **CHART_LAYOUT
        )
        tempo_event = st.plotly_chart(
            fig_tempo_agg, use_container_width=True, on_select="rerun", selection_mode="points", key="tempo_chart_sel"
        )
        chart_hint("Clique em uma barra para ver a quebra por chapter.")

        etapa_click_tempo = _clicked_category(tempo_event, axis="x")
        guard_tempo = f"{mes_sel2}|{etapa_click_tempo}"
        if not etapa_click_tempo:
            st.session_state.pop("_last_tempo_click", None)
        elif st.session_state.get("_last_tempo_click") != guard_tempo:
            st.session_state["_last_tempo_click"] = guard_tempo
            show_tempo_drilldown(etapa_click_tempo, mes_sel2)

    st.markdown("##### Candidatos parados por etapa")
    st.caption(
        "Candidatos em atenção e crítico em cada etapa do funil, somando todas as vagas abertas."
    )

    parados_mes = parados_df[parados_df["mes"] == mes_sel2] if not parados_df.empty else parados_df
    n_cand_critico = int((parados_mes["status"] == "critico").sum()) if not parados_mes.empty else 0
    n_cand_atencao = int((parados_mes["status"] == "atencao").sum()) if not parados_mes.empty else 0
    n_cand_ativos = int(dfp_mes[dfp_mes["etapa"] != "Contratação"]["candidatos"].sum())
    n_cand_ok = max(n_cand_ativos - n_cand_critico - n_cand_atencao, 0)

    st.markdown(
        '<div class="stage-summary-row">'
        + "".join(
            f'<div class="stage-summary-card"><span class="ssc-dot" style="background:{cor}"></span>'
            f'<div><div class="ssc-num">{num}</div><div class="ssc-lbl">{rotulo}</div></div></div>'
            for num, rotulo, cor in (
                (n_cand_critico, "candidatos em estado crítico", RED),
                (n_cand_atencao, "candidatos em atenção", AMBER),
                (n_cand_ok, "candidatos dentro do prazo", GREEN),
            )
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    if parados_mes.empty:
        render_note(
            "Nenhum candidato parado registrado neste mês (candidatos_parados.csv).", variant="neutral"
        )
    else:
        etapas_parados = [e for e in STAGES_ORDER if e in set(parados_df["etapa"])]
        metas_etapa = (
            dfp_mes.dropna(subset=["meta_sla_dias"]).groupby("etapa")["meta_sla_dias"].max().to_dict()
        )
        contagem_parados = parados_mes.groupby(["etapa", "status"]).size().to_dict()
        larguras = [1.45] + [1] * len(etapas_parados)

        cabecalho = st.columns(larguras)
        cabecalho[0].markdown('<div class="stage-th">Status</div>', unsafe_allow_html=True)
        for coluna, etapa_col in zip(cabecalho[1:], etapas_parados):
            meta = metas_etapa.get(etapa_col)
            nota = ""
            if meta is not None and pd.notna(meta):
                nota = (
                    f'<span class="th-note">Atenção: {int(meta) + 1}–{int(meta) + 5}d'
                    f'<br>Crítico: &gt;{int(meta) + 5}d</span>'
                )
            coluna.markdown(f'<div class="stage-th">{etapa_col}{nota}</div>', unsafe_allow_html=True)

        abrir_parados = bool(st.session_state.pop("_parados_reabrir", False))
        for status_key, status_label, cor_status in (
            ("atencao", "Atenção", AMBER),
            ("critico", "Crítico", RED),
        ):
            linha = st.columns(larguras)
            linha[0].markdown(
                f'<div class="status-row-label"><span class="dot" style="background:{cor_status}"></span>'
                f"{status_label}</div>",
                unsafe_allow_html=True,
            )
            for i, (coluna, etapa_col) in enumerate(zip(linha[1:], etapas_parados)):
                qtd = int(contagem_parados.get((etapa_col, status_key), 0))
                with coluna:
                    if qtd == 0:
                        st.markdown('<div class="stage-chip-empty">–</div>', unsafe_allow_html=True)
                        continue
                    st.markdown(
                        f'<span class="chip-marker chip-{status_key}"></span>', unsafe_allow_html=True
                    )
                    if st.button(str(qtd), key=f"chip_{status_key}_{i}", use_container_width=True):
                        _abrir_parados(etapa_col, status_key, None)
                        abrir_parados = True

        chart_hint("Clique em um número para ver o detalhamento por vaga e quem está parado.")
        st.markdown(
            f'<div class="legend-row">'
            f'<div class="legend-item"><span class="legend-dot" style="background:{AMBER}"></span>'
            f"Atenção — passou da meta de SLA da etapa</div>"
            f'<div class="legend-item"><span class="legend-dot" style="background:{RED}"></span>'
            f"Crítico — mais de 5 dias acima da meta</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if abrir_parados and st.session_state.get("_parados_sel"):
            _sel = st.session_state["_parados_sel"]
            if _sel.get("vaga"):
                show_parados_candidatos(_sel["etapa"], _sel["status"], _sel["vaga"], mes_sel2)
            else:
                show_parados_vagas(_sel["etapa"], _sel["status"], mes_sel2)

    st.divider()
    st.markdown("##### Gargalos e SLA")
    st.caption("Etapas com tempo médio acima da meta definida, ordenadas da mais crítica para a menos crítica.")

    status_counts = sla_calc["status_sla"].value_counts()
    resumo_status = [
        ("🔴 Crítico", int(status_counts.get("critico", 0)), RED),
        ("🟡 Atenção", int(status_counts.get("atencao", 0)), AMBER),
        ("🟢 OK", int(status_counts.get("ok", 0)), GREEN),
    ]
    st.markdown(
        '<div class="exec-kpi-row" style="margin-bottom:10px;">'
        + "".join(
            f'<div class="exec-kpi-card" style="text-align:center;">'
            f'<div class="exec-kpi-label" style="color:{color}">{label}</div>'
            f'<div class="exec-kpi-value" style="color:{color}">{count}</div>'
            f'<div class="exec-kpi-note">combinações chapter × etapa neste mês</div></div>'
            for label, count, color in resumo_status
        )
        + "</div>",
        unsafe_allow_html=True,
    )

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

st.markdown(
    f"""
    <div class="brand-footer">
        Farol de Hiring · Artefact People &amp; Talent — Greenhouse (pipe) + Artefactory (demanda)
    </div>
    """,
    unsafe_allow_html=True,
)
