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
import math
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st
import streamlit.components.v1 as components
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
SENIORIDADE_ORDER = ["Estagiário", "Entry", "Senior"]
# Vaga cujo nome não diz o nível: entra nos totais do pipe, nunca no farol.
SEM_SENIORIDADE = "Não informada"
# Senioridades que o farol trata como decisão de contratação. Estagiário
# aparece só para acompanhamento: o programa de estágio tem outro ritmo
# (turmas), e misturá-lo com Entry e Senior confundia a leitura na reunião.
SENIORIDADES_FAROL = ["Entry", "Senior"]


def resumo_pipe(df: pd.DataFrame, por: list) -> pd.DataFrame:
    """Agrega o pipe (grão chapter × senioridade × etapa, com somas e
    contagens) no nível pedido e refaz as médias ponderadas e o SLA."""
    g = df.groupby(por, as_index=False).agg(
        candidatos=("candidatos", "sum"),
        conv_soma=("conv_soma", "sum"),
        conv_n=("conv_n", "sum"),
        tempo_soma=("tempo_soma", "sum"),
        tempo_n=("tempo_n", "sum"),
        meta_sla_dias=("meta_sla_dias", "max"),
    )
    g["conversao_pct"] = (g["conv_soma"] / g["conv_n"].where(g["conv_n"] > 0)).round(1)
    g["tempo_medio_dias"] = (g["tempo_soma"] / g["tempo_n"].where(g["tempo_n"] > 0)).round(1)
    if "etapa" in g:
        g.loc[g["etapa"].eq("Contratação"), ["tempo_medio_dias", "meta_sla_dias"]] = None
    g["excesso_dias"] = (g["tempo_medio_dias"] - g["meta_sla_dias"]).round(1)
    g["status_sla"] = g["excesso_dias"].map(
        lambda e: None if pd.isna(e) else ("critico" if e > 5 else ("atencao" if e > 0 else "ok"))
    )
    return g.drop(columns=["conv_soma", "conv_n", "tempo_soma", "tempo_n"])

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
        .farol-card .aviso {{ font-size: 11.5px; font-weight: 700; margin-top: 8px; min-height: 18px; line-height: 1.5; }}

        /* ---- matriz do farol: chapter × senioridade ---- */
        .fm-wrap {{ overflow-x: auto; margin: 10px 0 8px; padding-bottom: 4px; }}
        .fm-grid {{
            display: grid; gap: 10px; align-items: stretch; min-width: 760px;
            grid-template-columns: minmax(150px, 1.1fr) repeat(var(--fm-n), minmax(150px, 1fr)) minmax(140px, .9fr);
        }}
        .fm-th {{
            font-size: 11.5px; font-weight: 700; color: {PAL['muted']}; text-transform: uppercase;
            letter-spacing: .06em; text-align: center; align-self: end; padding-bottom: 2px;
        }}
        .fm-th span {{ display: block; font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 11px; margin-top: 2px; }}
        .fm-th-apagada {{ opacity: .6; }}
        .fm-chapter {{
            display: flex; align-items: center; font-weight: 700; font-size: 14px; color: {PAL['ink']};
            line-height: 1.3; padding-right: 8px;
        }}
        .fm-card {{
            position: relative; overflow: hidden;
            background: linear-gradient(180deg, var(--fm-bg, transparent), transparent 140%), {PAL['surface']};
            border: 1px solid {PAL['line']}; border-radius: 14px; padding: 12px 14px 12px 18px;
            box-shadow: 0 2px 10px {PAL['shadow']};
            transition: transform .15s ease, box-shadow .15s ease;
        }}
        .fm-card::before {{
            content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 4px; background: var(--fm-cor, transparent);
        }}
        .fm-card:hover {{ transform: translateY(-2px); box-shadow: 0 8px 18px {PAL['shadow_hover']}; }}
        .fm-pill {{
            display: inline-flex; align-items: center; gap: 6px; font-size: 10.5px; font-weight: 800;
            letter-spacing: .08em; color: var(--fm-cor); text-transform: uppercase;
        }}
        .fm-dot {{ width: 8px; height: 8px; border-radius: 50%; display: inline-block; flex: none; }}
        .fm-gap {{ font-size: 19px; font-weight: 700; color: {PAL['ink']}; margin: 6px 0 2px; line-height: 1.2; }}
        .fm-num {{ display: flex; flex-wrap: wrap; column-gap: 10px; font-size: 11.5px; color: {PAL['muted']}; }}
        .fm-num span {{ white-space: nowrap; }}
        .fm-orig {{ font-size: 10.5px; color: {PAL['muted']}; opacity: .8; margin-top: 3px; white-space: nowrap; }}
        .fm-total-liq {{ border-top: 1px solid {PAL['line']}; padding-top: 3px; margin-top: 1px; }}
        .fm-num b {{ color: {PAL['ink']}; font-weight: 600; font-family: 'Roboto Mono', monospace; }}
        .fm-apagada {{ background: transparent; box-shadow: none; border-style: dashed; opacity: .7; }}
        .fm-apagada .fm-mini {{
            display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 600;
            color: {PAL['muted']}; margin-bottom: 4px;
        }}
        .fm-vazia {{ background: transparent; box-shadow: none; border-style: dashed; display: flex; align-items: center; justify-content: center; }}
        .fm-vazia-txt {{ font-size: 11.5px; color: {PAL['muted']}; }}
        .fm-total {{
            display: flex; flex-direction: column; justify-content: center; gap: 3px;
            padding: 10px 4px 10px 14px; border-left: 1px solid {PAL['line']};
        }}
        .fm-total div {{ display: flex; justify-content: space-between; gap: 8px; font-size: 12px; }}
        .fm-total span {{ color: {PAL['muted']}; }}
        .fm-total b {{ color: {PAL['ink']}; font-family: 'Roboto Mono', monospace; font-weight: 600; }}

        /* ---- kpis executivos: cards de metrica agregada (aba Visao Gerencial) ---- */
        .exec-kpi-row {{ display: flex; gap: 14px; flex-wrap: wrap; margin: 4px 0 22px; }}
        .exec-kpi-scope {{ font-size: 12.5px; color: {PAL['muted']}; margin: 6px 0 2px; }}
        .pipe-sec {{
            display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; margin: 34px 0 6px;
            padding-top: 16px; border-top: 1px solid {PAL['line']};
        }}
        .pipe-sec span {{ font-size: 12px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase; color: {PINK}; }}
        /* ---- aba Como ler ---- */
        .cl-hero {{
            background: linear-gradient(120deg, {MEDIUM_BLUE} 0%, #2B2F7A 55%, {PINK} 140%);
            border-radius: 18px; padding: 26px 28px; margin: 4px 0 26px; color: #FFFFFF;
        }}
        .cl-hero-tit {{ font-size: 26px; font-weight: 800; margin-bottom: 8px; }}
        .cl-hero-txt {{ font-size: 14px; line-height: 1.6; opacity: .88; max-width: 760px; }}
        .cl-secao {{ display: flex; align-items: center; gap: 12px; margin: 30px 0 12px; }}
        .cl-secao-ico {{
            width: 38px; height: 38px; border-radius: 11px; display: flex; align-items: center; justify-content: center;
            font-size: 19px; background: {PAL['surface2']}; border: 1px solid {PAL['line']}; flex: none;
        }}
        .cl-secao-tit {{ font-size: 19px; font-weight: 800; color: {PAL['ink']}; line-height: 1.2; }}
        .cl-secao-sub {{ font-size: 12.5px; color: {PAL['muted']}; margin-top: 2px; }}
        .cl-abas {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }}
        .cl-aba {{
            background: {PAL['surface']}; border: 1px solid {PAL['line']}; border-radius: 16px; padding: 18px;
            box-shadow: 0 2px 10px {PAL['shadow']};
        }}
        .cl-aba-ico {{ font-size: 24px; margin-bottom: 8px; }}
        .cl-aba-nome {{ font-size: 15px; font-weight: 800; color: {PAL['ink']}; }}
        .cl-aba-perg {{ font-size: 13.5px; font-weight: 600; color: {PINK}; margin: 6px 0 8px; line-height: 1.45; }}
        .cl-aba-txt {{ font-size: 12.5px; color: {PAL['muted']}; line-height: 1.55; margin-top: 4px; }}
        .cl-aba-txt b {{ color: {PAL['ink']}; }}
        .cl-fonte-tag {{
            display: inline-block; font-size: 10.5px; font-weight: 800; letter-spacing: .08em; text-transform: uppercase;
            color: {PAL['muted']}; border: 1px solid {PAL['line']}; border-radius: 20px; padding: 2px 9px; margin-bottom: 8px;
        }}
        .cl-regras {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 10px; margin-bottom: 14px; }}
        .cl-regra {{
            position: relative; border-radius: 14px; padding: 14px 14px 12px; border: 1px solid {PAL['line']};
            background: linear-gradient(180deg, var(--cl-bg), transparent 160%), {PAL['surface']};
        }}
        .cl-regra-n {{
            font-size: 11px; font-weight: 800; color: {PAL['muted']}; width: 22px; height: 22px; border-radius: 50%;
            border: 1px solid {PAL['line']}; display: flex; align-items: center; justify-content: center; margin-bottom: 8px;
        }}
        .cl-regra-cond {{ font-size: 13px; color: {PAL['ink']}; line-height: 1.4; min-height: 36px; }}
        .cl-regra-res {{
            display: flex; align-items: center; gap: 6px; margin-top: 10px; font-size: 11.5px; font-weight: 800;
            letter-spacing: .08em; text-transform: uppercase; color: var(--cl-cor);
        }}
        .cl-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--cl-cor); display: inline-block; }}
        .cl-lista {{
            background: {PAL['surface']}; border: 1px solid {PAL['line']}; border-radius: 16px; overflow: hidden;
            box-shadow: 0 2px 10px {PAL['shadow']};
        }}
        .cl-termo {{ display: grid; grid-template-columns: 230px 1fr; gap: 18px; padding: 14px 20px; }}
        .cl-termo + .cl-termo {{ border-top: 1px solid {PAL['line']}; }}
        .cl-termo-nome {{ font-size: 13.5px; font-weight: 700; color: {PAL['ink']}; }}
        .cl-termo-def {{ font-size: 13px; color: {PAL['muted']}; line-height: 1.6; }}
        .cl-termo-def b {{ color: {PAL['ink']}; }}
        @media (max-width: 700px) {{ .cl-termo {{ grid-template-columns: 1fr; gap: 4px; }} }}
        .cl-metas {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 4px; margin-bottom: 14px; }}
        .cl-meta {{
            flex: 1 0 96px; text-align: center; background: {PAL['surface']}; border: 1px solid {PAL['line']};
            border-radius: 12px; padding: 10px 8px; position: relative;
        }}
        .cl-meta-d {{ font-family: 'Roboto Mono', monospace; font-weight: 700; font-size: 18px; color: {PAL['ink']}; }}
        .cl-meta-e {{ font-size: 11px; color: {PAL['muted']}; margin-top: 2px; line-height: 1.3; }}
        .cl-limites {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; margin-bottom: 8px; }}
        @media (max-width: 700px) {{ .cl-limites {{ grid-template-columns: 1fr; }} }}
        .cl-limite {{
            border-radius: 14px; padding: 16px 18px; border: 1px solid {PAL['line']}; border-left: 4px solid {AMBER};
            background: {STATUS_BG['manter']};
        }}
        .cl-limite-tit {{ font-size: 14px; font-weight: 800; color: {PAL['ink']}; margin-bottom: 6px; }}
        .cl-limite-txt {{ font-size: 12.5px; color: {PAL['muted']}; line-height: 1.55; }}
        .triagem-row {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin: 2px 0 10px; }}
        .triagem-lbl {{ font-size: 11.5px; font-weight: 700; color: {PAL['muted']}; text-transform: uppercase; letter-spacing: .05em; margin-right: 4px; }}
        .triagem-chip {{
            font-size: 12px; color: {PAL['muted']}; border: 1px dashed {PAL['line']}; border-radius: 20px; padding: 3px 10px;
        }}
        .triagem-chip b {{ color: {PAL['ink']}; font-family: 'Roboto Mono', monospace; font-weight: 600; margin-left: 4px; }}
        .exec-kpi-scope b {{ color: {PAL['ink']}; }}
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


# Gap abaixo de 1 pessoa não move o farol, qualquer que seja o percentual.
# Sem isso, demanda de 0,5 FTE com oferta zero dava gap de +100% e o card
# mandava "acelerar" para abrir meia vaga.
GAP_MINIMO_PESSOAS = 1.0


def farol_status(demanda: float, oferta: float):
    """Semáforo a partir do gap entre demanda líquida e oferta ajustada.

    Ordem das regras:
    1. Sem demanda cadastrada (NaN) -> sem dado.
    2. Gap absoluto menor que GAP_MINIMO_PESSOAS -> manter: falta ou sobra
       menos de uma pessoa, não há o que abrir nem pausar. Cobre demanda e
       oferta zeradas.
    3. Demanda líquida <= 0 (com oferta sobrando) -> pausar, sem percentual:
       no mês corrente as desalocações costumam superar os pedidos, e
       percentual sobre denominador negativo inverte o sinal.
    4. Senão, o gap percentual decide: > +20% acelerar, < -10% pausar."""
    if demanda is None or pd.isna(demanda):
        return "sem_dado", None
    oferta = 0.0 if oferta is None or pd.isna(oferta) else oferta
    if abs(demanda - oferta) < GAP_MINIMO_PESSOAS:
        gap_pct = round((demanda - oferta) / demanda * 100, 1) if demanda > 0 else None
        return "manter", gap_pct
    if demanda <= 0:
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

# Só as colunas que load_data() usa, em vez de SELECT * (37 colunas).
# Nome do candidato e da vaga só vêm para quem aparece numa lista: em
# processo (candidatos parados) e See You Soon. Para as ~55 mil
# candidaturas encerradas eles não servem para nada — e menos nome de
# candidato trafegando é melhor também por privacidade.
# Ao usar uma coluna nova da vw_farol_base no app, acrescente-a aqui.
_COLUNAS_BASE = """
    application_id, snapshot_date, job_id, chapter, senioridade,
    etapa, ordem_etapa, tipo_etapa, application_status,
    flag_ativo, flag_contratado, flag_see_you_soon,
    conversao_etapa_pct, tempo_medio_etapa, meta_sla_etapa,
    status_parado, total_days_in_pipe, dias_esperados_ate_etapa,
    dias_ate_contratacao, contrib_oferta_ajustada,
    su_candidaturas_vaga, su_aceites_vaga, su_dias_no_banco_vaga,
    IF(flag_ativo = 1 OR flag_see_you_soon = 1, candidato, NULL) AS candidato,
    IF(flag_ativo = 1 OR flag_see_you_soon = 1, vaga, NULL)      AS vaga
"""


@st.cache_data(ttl=1800, show_spinner="Lendo as views do BigQuery…")
def load_data():
    """Lê as duas views oficiais e deriva, em pandas, os recortes que cada
    tela usa. As views são duas porque são dois grãos e dois eixos de
    tempo: a demanda é forecast mensal (até 2027-12) e o pipe é foto de
    hoje — o Greenhouse não tem data em nenhuma view."""
    # Vaga sem chapter não entra em nenhuma tela por chapter; só o See You
    # Soon (tempo médio no banco) olha também quem não tem chapter.
    base, demanda = bq.consultar_varias(
        f"SELECT {_COLUNAS_BASE} FROM {bq.tabela('vw_farol_base')} "
        "WHERE chapter IS NOT NULL OR flag_see_you_soon = 1",
        f"SELECT * FROM {bq.tabela('vw_farol_demanda')}",
    )

    data_snap = pd.to_datetime(base["snapshot_date"].iloc[0])
    mes_snap = data_snap.strftime("%Y-%m")
    label_snap = _rotulo_mes(mes_snap)

    # "Contratação" não é etapa viva: quem está lá entra pelo flag_contratado
    base = base.copy()
    base["conta_funil"] = base["flag_ativo"].where(
        ~base["etapa"].eq("Contratação"), base["flag_contratado"]
    )
    # vaga sem senioridade no nome continua contando, num grupo próprio, para
    # o total com "Todas" bater com o total sem filtro
    # "Pleno" virou "Entry" (nov/2026). O replace deixa o app certo mesmo
    # antes de as views serem recriadas com o nome novo.
    base["senioridade"] = base["senioridade"].replace({"Pleno": "Entry"}).fillna(SEM_SENIORIDADE)
    demanda["senioridade"] = demanda["senioridade"].replace({"Pleno": "Entry"})
    funil = base[base["tipo_etapa"].eq("funil") & base["chapter"].notna()].copy()
    funil["conv_n"] = funil["conversao_etapa_pct"].notna().astype(int)
    funil["tempo_n"] = funil["tempo_medio_etapa"].notna().astype(int)

    # ---- funil por chapter × senioridade × etapa ----------------------
    # Guarda SOMA e CONTAGEM em vez da média: assim qualquer recorte (um
    # chapter, uma senioridade, tudo) refaz a média ponderada certa em
    # resumo_pipe(). O grão da view é a candidatura, então a média já sai
    # ponderada pelo número de candidaturas de cada vaga.
    pipe_nivel = (
        funil.groupby(["chapter", "senioridade", "etapa", "ordem_etapa"], as_index=False)
        .agg(
            candidatos=("conta_funil", "sum"),
            conv_soma=("conversao_etapa_pct", "sum"),
            conv_n=("conv_n", "sum"),
            tempo_soma=("tempo_medio_etapa", "sum"),
            tempo_n=("tempo_n", "sum"),
            meta_sla_dias=("meta_sla_etapa", "max"),
        )
    )
    pipe_nivel["mes"], pipe_nivel["mes_label"] = mes_snap, label_snap
    pipe = resumo_pipe(pipe_nivel, ["chapter", "etapa", "ordem_etapa"])
    pipe["mes"], pipe["mes_label"] = mes_snap, label_snap

    # ---- taxas de oferta e conversão ------------------------------------
    # Saem dos flags, não da contagem por etapa: "Oferta" no funil é quem
    # está lá HOJE, e "Contratação" é todo mundo já contratado. Dividir um
    # pelo outro mistura estoque com histórico e passa de 100%.
    #
    # Recusa de oferta não sai do offer_status: o Greenhouse só preenche
    # 'Accepted' (contratados); quem saiu na etapa Oferta fica 'N/A'. Por
    # isso a recusa é medida pela etapa: reprovado ESTANDO em Oferta.
    base["flag_recusa_oferta"] = (
        base["application_status"].str.lower().eq("rejected") & base["etapa"].eq("Oferta")
    ).astype(int)
    # dias no pipe só de quem foi contratado: é o tempo real de contratação
    base["dias_contratacao"] = base["total_days_in_pipe"].where(base["flag_contratado"].eq(1))
    # Quem CHEGOU a uma etapa: a linha guarda a etapa onde a candidatura
    # está ou onde foi reprovada, e o contratado fica na ordem 9. Então
    # ordem_etapa >= N é "passou por N". Serve para a conversão começar
    # numa etapa escolhida, sem o volume da triagem de currículo.
    base["chegou_case"] = base["ordem_etapa"].ge(2).fillna(False).astype(int)
    base["chegou_fit"] = base["ordem_etapa"].ge(4).fillna(False).astype(int)
    taxas = (
        base[base["chapter"].notna()]
        .groupby(["chapter", "senioridade"], as_index=False)
        .agg(
            candidaturas=("application_id", "count"),
            chegaram_case=("chegou_case", "sum"),
            chegaram_fit=("chegou_fit", "sum"),
            contratados=("flag_contratado", "sum"),
            recusas_oferta=("flag_recusa_oferta", "sum"),
            dias_contratacao=("dias_contratacao", "sum"),
            contratados_com_dias=("dias_contratacao", "count"),
        )
    )

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
        .groupby(["chapter", "senioridade"], as_index=False)
        .agg(candidaturas_sys=("su_candidaturas_vaga", "sum"), aceites_sys=("su_aceites_vaga", "sum"))
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
            # sem senioridade não casa com nenhuma linha de demanda
            & base["senioridade"].ne(SEM_SENIORIDADE)
        ]
        .groupby(["chapter", "senioridade"], as_index=False)
        .agg(oferta_ajustada=("contrib_oferta_ajustada", "sum"))
    )
    # Grade mês × chapter × senioridade: o forecast não tem linha quando não
    # há demanda, e um merge direto faria a oferta dessa senioridade sumir
    # do mês, mudando a oferta do chapter sem o pipe ter mudado. Sem linha
    # vale demanda zero. Chapter sem demanda em mês nenhum continua fora.
    combinacoes = pd.concat(
        [
            demanda[["chapter", "senioridade"]],
            oferta.loc[oferta["chapter"].isin(demanda["chapter"]), ["chapter", "senioridade"]],
        ]
    ).drop_duplicates()
    grade = demanda[["mes"]].drop_duplicates().merge(combinacoes, how="cross")
    farol = grade.merge(demanda, on=["mes", "chapter", "senioridade"], how="left").merge(
        oferta, on=["chapter", "senioridade"], how="left"
    )
    farol["demanda_liquida"] = farol["demanda_liquida"].fillna(0.0)
    # Source Request e desalocações ficam visíveis na tela: a demanda
    # líquida já desconta quem sai de projeto e pode ser realocado, e quem
    # decide precisa ver de onde veio o número antes de abrir vaga.
    for col in ("demanda_bruta_fte", "desalocado_fte"):
        farol[col] = farol[col].fillna(0.0) if col in farol else 0.0
    farol["oferta_ajustada"] = farol["oferta_ajustada"].fillna(0.0)
    # Estagiário fica fora do farol: segue o ritmo das turmas de estágio, não
    # a demanda dos projetos. Continua na Visão do Pipe.
    farol = farol[farol["senioridade"].isin(SENIORIDADES_FAROL)].copy()
    # Números inteiros: não se contrata fração de pessoa (1 FTE = 1
    # contratação, confirmado). Arredonda meio para cima (2,5 vira 3) e
    # recalcula a líquida a partir das partes já arredondadas, para a conta
    # da tela fechar: Source Request - desalocados = demanda líquida.
    for col in ("demanda_bruta_fte", "desalocado_fte", "oferta_ajustada"):
        farol[col] = (farol[col] + 0.5).apply(math.floor).astype(int)
    farol["demanda_liquida"] = farol["demanda_bruta_fte"] - farol["desalocado_fte"]
    farol["gap"] = farol["demanda_liquida"] - farol["oferta_ajustada"]
    calculado = farol.apply(
        lambda r: farol_status(r["demanda_liquida"], r["oferta_ajustada"]), axis=1
    )
    farol["farol_status"] = [c[0] for c in calculado]
    farol["gap_pct"] = [c[1] for c in calculado]
    farol["mes_label"] = farol["mes"].map(_rotulo_mes)

    return farol, pipe, pipe_nivel, su_ofertas, su_banco, parados, taxas, mes_snap, data_snap.strftime("%d/%m/%Y")


try:
    (farol_df, pipe_df, pipe_nivel_df, su_ofertas_df, su_banco_df,
     parados_df, taxas_df, MES_SNAPSHOT, DATA_SNAPSHOT) = load_data()
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
            "recurso, que só existe dentro do GCP. Não é problema de rede.\n\n"
            "Duas formas de resolver, qualquer uma serve:\n\n"
            "1. **Na sua máquina:** `gcloud auth application-default login` "
            "(precisa do Google Cloud SDK instalado).\n"
            "2. **Sem gcloud, ou para publicar o app:** peça uma service account "
            "com leitura no dataset e cole o JSON dela em "
            "`.streamlit/secrets.toml`, sob `[gcp_service_account]`. O modelo "
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
#
# O forecast do Artefactory vai até 2027-12, mas a oferta é o pipe de HOJE
# projetado em ~45 dias: comparar essa oferta com a demanda de um ano à
# frente não diz nada. Por isso o farol só mostra o mês corrente e os
# próximos JANELA_MESES.
JANELA_MESES = 3
_FIM_FORECAST = str(farol_df["mes"].max())
_fim_janela = (pd.Period(MES_SNAPSHOT, "M") + JANELA_MESES).strftime("%Y-%m")
_na_janela = farol_df["mes"].astype(str).between(MES_SNAPSHOT, _fim_janela)
if _na_janela.any():  # se o forecast for todo antigo, melhor mostrar tudo que nada
    farol_df = farol_df[_na_janela]

MES_LABELS = farol_df.drop_duplicates("mes").set_index("mes")["mes_label"].to_dict()
MES_LABELS.setdefault(MES_SNAPSHOT, _rotulo_mes(MES_SNAPSHOT))
MESES = sorted(m for m in MES_LABELS if m in set(farol_df["mes"]))

# Abre no PRÓXIMO mês, não no último da lista: o mês corrente já está no
# fim (desalocações superam pedidos e a demanda líquida sai negativa), e
# o último da janela é o mais especulativo.
_proximo = (pd.Period(MES_SNAPSHOT, "M") + 1).strftime("%Y-%m")
IDX_MES_PADRAO = MESES.index(_proximo) if _proximo in MESES else 0

# Aviso de escopo calculado do próprio dado, para não envelhecer: diz de
# quando é a foto do pipe, até onde vai o forecast, e quais chapters têm
# pipe mas não têm demanda cadastrada (esses não têm farol).
_sem_demanda = sorted(set(pipe_df["chapter"].dropna()) - set(farol_df["chapter"].dropna()))
_aviso = (
    f"Dados oficiais do BigQuery. Pipe: foto de <b>{MES_LABELS[MES_SNAPSHOT]}</b>. Nenhuma "
    "view do Greenhouse tem data, então o funil não tem histórico. Demanda: forecast de "
    f"<b>{MES_LABELS[MESES[0]]}</b> a <b>{MES_LABELS[MESES[-1]]}</b> (mês atual + {JANELA_MESES}; "
    f"o Artefactory projeta até {_rotulo_mes(_FIM_FORECAST)}, mas comparar o pipe de hoje com "
    "demanda tão distante não ajuda a decidir agora)."
)
if _sem_demanda:
    _aviso += (
        f" Sem demanda cadastrada no Artefactory: <b>{', '.join(_sem_demanda)}</b>: "
        "esses chapters aparecem no funil, mas não têm farol."
    )
render_note(_aviso, variant="neutral")


def gap_trend(chapter: str, senioridade: str) -> list:
    hist = farol_df[(farol_df["chapter"] == chapter) & (farol_df["senioridade"] == senioridade)].sort_values("mes")
    return hist["gap_pct"].tolist()


def pipe_trend(chapter: str, etapa: str, col: str = "tempo_medio_dias") -> list:
    hist = pipe_df[(pipe_df["chapter"] == chapter) & (pipe_df["etapa"] == etapa)].sort_values("mes")
    return hist[col].tolist()


def gap_texto(gap_pct, demanda: float, oferta: float, curto: bool = False) -> str:
    """Gap para exibir, em pessoas, com o % como complemento. O % só aparece
    com demanda de pelo menos 1 pessoa: sobre 0,5 FTE ele vira -720% e
    parece mais grave do que um gap de 11 pessoas. `curto` é para rótulo
    de gráfico, onde não cabe a frase inteira."""
    falta = demanda - oferta
    if abs(falta) < 0.05:
        return "equilibrado"
    if curto:
        return f"falta {falta:.0f}" if falta > 0 else f"sobra {-falta:.0f}"
    texto = f"faltam {falta:.0f} pessoas" if falta > 0 else f"sobram {-falta:.0f} pessoas"
    if gap_pct is not None and pd.notna(gap_pct) and demanda >= 1:
        texto += f" ({gap_pct:+.0f}%)"
    return texto


def farol_insight(status: str, gap_pct, demanda: float, oferta: float) -> str:
    """Frase curta de leitura/ação por trás do status — a 'inteligência' por
    trás do número puro, mostrada no hover do card."""
    if status == "sem_dado":
        return "Sem demanda registrada neste período, então não dá para calcular o farol."
    if status == "acelerar":
        return (
            f"Oferta cobre {oferta / demanda * 100:.0f}% da demanda "
            f"(gap {gap_pct:+.0f}%). Priorize abrir vagas neste chapter."
        )
    if status == "manter":
        if abs(demanda - oferta) < GAP_MINIMO_PESSOAS:
            return (
                f"Demanda e oferta empatadas em {demanda:.0f} pessoas. "
                "Mantenha o ritmo atual de contratação."
            )
        return (
            f"Oferta e demanda estão equilibradas (gap {gap_pct:+.0f}%). "
            "Mantenha o ritmo atual de contratação."
        )
    if gap_pct is None:
        return (
            f"Demanda líquida de {demanda:.0f} pessoas: as desalocações cobrem o Source Request deste mês. "
            "Considere pausar novas aberturas ou redirecionar candidatos para outro chapter."
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


TODOS = "Todos"


def recorte(df: pd.DataFrame, chapter: str | None = None, senioridade: str | None = None) -> pd.DataFrame:
    """Filtra por chapter e senioridade; None ou "Todos" não filtra."""
    if chapter and chapter != TODOS:
        df = df[df["chapter"] == chapter]
    if senioridade and senioridade != TODOS:
        df = df[df["senioridade"] == senioridade]
    return df


# NOTA: as funções abaixo recebem `mes` por compatibilidade com as telas,
# mas IGNORAM o valor e leem sempre MES_SNAPSHOT. O pipe do Greenhouse não
# tem data: é foto de hoje. Só a demanda (farol_df) varia por mês.
def pipe_qualificado(mes: str, chapter: str | None = None) -> int:
    """Quantos candidatos já passaram do currículo e ainda estão vivos no processo
    (Entrevista Fit até Oferta) — o estoque qualificado disponível para cobrir
    a demanda deste mês, sem contar quem ainda está só na triagem de currículo."""
    # mesmo recorte do farol: só Entry e Senior (sem Estagiário)
    df = pipe_nivel_df[
        (pipe_nivel_df["mes"] == MES_SNAPSHOT)
        & pipe_nivel_df["etapa"].isin(QUALIFIED_STAGES)
        & pipe_nivel_df["senioridade"].isin(SENIORIDADES_FAROL)
    ]
    if chapter:
        df = df[df["chapter"] == chapter]
    return int(df["candidatos"].sum())


def taxa_aceite_oferta(mes: str, chapter: str | None = None, senioridade: str | None = None) -> float | None:
    """% das ofertas já decididas que viraram contratação:
    contratados / (contratados + reprovados na etapa Oferta). Quem ainda
    está em Oferta fica fora — não decidiu. Premissa: todo contratado
    passou pela Oferta (o Greenhouse não guarda a etapa do contratado)."""
    df = recorte(taxas_df, chapter, senioridade)
    decididas = df["contratados"].sum() + df["recusas_oferta"].sum()
    if not decididas:
        return None
    return df["contratados"].sum() / decididas * 100


def tempo_medio_contratacao(mes: str) -> float | None:
    """Média de dias no pipe de quem foi contratado, somando todos os
    chapters. Não soma o tempo médio de cada etapa: essas médias incluem
    quem ficou parado e foi reprovado, e somadas davam ~410 dias, contra
    ~260 dos contratados de verdade."""
    n = taxas_df["contratados_com_dias"].sum()
    if not n:
        return None
    return taxas_df["dias_contratacao"].sum() / n


def mes_anterior(mes: str) -> str | None:
    idx = MESES.index(mes)
    return MESES[idx - 1] if idx > 0 else None


# Etapa inicial de cada conversão "até a contratação": a coluna de taxas_df
# que conta quem chegou a ela. O currículo infla o denominador (a maioria
# é descartada na triagem), por isso a conversão principal parte da Fit.
INICIO_CONVERSAO = {
    "Avaliação de currículo": "candidaturas",
    "Envio do Case Escrito": "chegaram_case",
    "Entrevista Fit": "chegaram_fit",
}


def conversao_ate_contratacao(inicio: str, chapter: str | None = None, senioridade: str | None = None):
    """(contratados, quem chegou à etapa `inicio`, %) no histórico inteiro.
    Numerador e denominador são o mesmo universo, não a foto de hoje."""
    df = recorte(taxas_df, chapter, senioridade)
    base_n = int(df[INICIO_CONVERSAO[inicio]].sum())
    contratados = int(df["contratados"].sum())
    return contratados, base_n, (contratados / base_n * 100 if base_n else None)


def conversao_total_pipe(mes: str) -> float | None:
    """% de todas as candidaturas (de qualquer status) que terminaram em
    contratação, somando todos os chapters."""
    return conversao_ate_contratacao("Avaliação de currículo")[2]


def taxa_aceite_sys(mes: str, chapter: str | None = None, senioridade: str | None = None) -> float | None:
    """Conversão do banco See You Soon: % das pessoas que passaram pelo
    banco e aceitaram oferta. Não é taxa de aceite de oferta porque a view
    de SU não registra oferta recusada (só 'Accepted' e 'N/A') — por
    oferta, daria 100% sempre."""
    if su_ofertas_df.empty:
        return None
    df = recorte(su_ofertas_df[su_ofertas_df["mes"] == MES_SNAPSHOT], chapter, senioridade)
    candidaturas = df["candidaturas_sys"].sum()
    if not candidaturas:
        return None
    return df["aceites_sys"].sum() / candidaturas * 100


def su_tempo_medio_banco(chapter: str | None = None, senioridade: str | None = None) -> float | None:
    """Tempo médio (dias) que os candidatos hoje 'aguardando' no banco See You
    Soon já estão lá — foto do estoque atual. O Greenhouse só dá a média por
    vaga, então cada pessoa leva o valor da sua vaga."""
    if su_banco_df.empty:
        return None
    ativos = recorte(su_banco_df[su_banco_df["status"] == "aguardando"], chapter, senioridade)
    if ativos.empty or ativos["dias_no_banco"].isna().all():
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


def _pipe_por_chapter(etapa: str, senioridade: str | None) -> pd.DataFrame:
    """Uma etapa, todos os chapters, no recorte de senioridade da página."""
    df = recorte(pipe_nivel_df[pipe_nivel_df["etapa"] == etapa], None, senioridade)
    return resumo_pipe(df, ["chapter"]) if not df.empty else df


def _sufixo_sen(senioridade: str | None) -> str:
    return "" if not senioridade or senioridade == TODOS else f" · senioridade {senioridade}"


@st.dialog("Detalhamento por carreira")
def show_conv_drilldown(etapa: str, mes: str, senioridade: str | None = None) -> None:
    st.markdown(f"#### {etapa}")
    st.caption(
        f"% que chegou a esta etapa vindo da anterior, por chapter{_sufixo_sen(senioridade)}. "
        "Cada vaga conta no máximo 100%."
    )
    df = _pipe_por_chapter(etapa, senioridade)
    df = df.dropna(subset=["conversao_pct"]).copy() if not df.empty else df
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
def show_tempo_drilldown(etapa: str, mes: str, senioridade: str | None = None) -> None:
    st.markdown(f"#### {etapa}")
    st.caption(f"Tempo médio (dias corridos) nesta etapa, por chapter{_sufixo_sen(senioridade)}.")
    df = _pipe_por_chapter(etapa, senioridade)
    df = df.dropna(subset=["tempo_medio_dias"]).copy() if not df.empty else df
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
    """Quem está parado em cada etapa, no recorte de chapter e senioridade
    escolhido no topo da Visão do Pipe (o modal abre fora da aba, então lê
    os filtros do session_state)."""
    df = recorte(
        parados_df[parados_df["mes"] == MES_SNAPSHOT],
        st.session_state.get("chapter_pipe"),
        st.session_state.get("senioridade_pipe"),
    )
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


@st.dialog("Candidatos parados por vaga")
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
        rotulo = f"{row.vaga} · {row.qtd} candidato(s), até {row.pior:.0f}d no pipe"
        if st.button(rotulo, key=f"parados_vaga_{status_key}_{i}", use_container_width=True):
            _abrir_parados(etapa, status_key, row.vaga)
            st.rerun()


@st.dialog("Quem está parado")
def show_parados_candidatos(etapa: str, status_key: str, vaga: str, mes: str) -> None:
    status_label = "Crítico" if status_key == "critico" else "Atenção"
    df = _parados_no_mes(mes, etapa, status_key, vaga).sort_values("dias_na_etapa", ascending=False)
    st.markdown(f"#### {vaga}")
    if df.empty:
        render_note("Nenhum candidato parado nesta vaga.", variant="neutral")
        return
    st.caption(
        f"{len(df)} candidato(s) parado(s) em \"{etapa}\" · {status_label} · {MES_LABELS[mes]}."
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


ETAPA_SU = "See You Soon (banco)"


@st.dialog("Banco See You Soon")
def show_su_drilldown(chapter: str | None, senioridade: str | None) -> None:
    """Quem está aguardando no banco, de quem espera há mais tempo para
    quem espera há menos. Abre ao clicar na barra rosa do tempo por etapa."""
    df = recorte(su_banco_df[su_banco_df["status"] == "aguardando"], chapter, senioridade)
    df = df.sort_values("dias_no_banco", ascending=False, na_position="last")
    if df.empty:
        render_note("Ninguém aguardando no banco neste recorte.", variant="neutral")
        return
    media = df["dias_no_banco"].mean()
    por_chapter = (
        df.assign(chapter=df["chapter"].fillna("Sem chapter"))
        .groupby("chapter")["dias_no_banco"].agg(["size", "mean"])
        .sort_values("mean", ascending=False)
    )
    st.caption(
        f"{len(df)} pessoa(s) aguardando"
        + (f" · média de **{media:.0f} dias** no banco. " if pd.notna(media) else ". ")
        + " · ".join(
            f"{ch}: {int(r['size'])} ({r['mean']:.0f}d)" if pd.notna(r["mean"]) else f"{ch}: {int(r['size'])} (sem dias)"
            for ch, r in por_chapter.iterrows()
        )
    )
    render_note(
        "O Greenhouse só informa a média de dias por <b>vaga</b>: pessoas da mesma vaga aparecem com o "
        "mesmo número. Use para achar as vagas com banco parado há mais tempo.",
        variant="neutral",
    )
    itens = []
    for row in df.itertuples(index=False):
        iniciais = "".join(parte[0] for parte in str(row.candidato).split()[:2]).upper()
        dias = f"{row.dias_no_banco:.0f}d" if pd.notna(row.dias_no_banco) else "—"
        cor = RED if pd.notna(row.dias_no_banco) and row.dias_no_banco > 90 else (
            AMBER if pd.notna(row.dias_no_banco) and row.dias_no_banco > 45 else PAL["muted"]
        )
        chapter_txt = row.chapter if isinstance(row.chapter, str) else "Sem chapter"
        itens.append(
            f'<div class="cand-item">'
            f'<div class="cand-left"><div class="cand-avatar">{iniciais}</div>'
            f'<div><div class="cand-name">{row.candidato}</div>'
            f'<div class="cand-role">{chapter_txt} · {row.senioridade}</div></div></div>'
            f'<div class="cand-right"><div class="cand-days" style="color:{cor}">{dias}</div>'
            f'<div class="cand-meta">no banco (média da vaga)</div></div>'
            f"</div>"
        )
    st.markdown("".join(itens), unsafe_allow_html=True)


CHART_LAYOUT = dict(
    margin=dict(l=10, r=10, t=10, b=10),
    plot_bgcolor=PAL["surface"],
    paper_bgcolor=PAL["surface"],
    font=dict(family="Roboto, sans-serif", color=PAL["ink"], size=13),
    hoverlabel=dict(bgcolor=PAL["surface"], font_size=12.5, font_family="Roboto, sans-serif", font_color=PAL["ink"]),
    xaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
    yaxis=dict(gridcolor=PAL["line"], zerolinecolor=PAL["line"]),
)

# Mês da demanda compartilhado: a Visão Gerencial e o Farol têm cada uma o
# seu seletor (Streamlit não deixa o mesmo widget em duas abas), mas trocar
# um troca o outro, para os números das duas abas sempre baterem.
_MES_KEYS = ("mes_exec", "mes_farol")
for _k in _MES_KEYS:
    if st.session_state.get(_k) not in MESES:
        st.session_state[_k] = st.session_state.get("mes_ref", MESES[IDX_MES_PADRAO])


def _sincroniza_mes(origem: str) -> None:
    st.session_state["mes_ref"] = st.session_state[origem]
    for k in _MES_KEYS:
        st.session_state[k] = st.session_state[origem]


def _ir_para_pipe(chapter: str, senioridade: str) -> None:
    """Clique numa célula do farol: leva o recorte para os filtros da Visão
    do Pipe e para o detalhe por senioridade do próprio Farol."""
    st.session_state["chapter_pipe"] = chapter
    st.session_state["senioridade_pipe"] = senioridade
    st.session_state["chapter_sel"] = chapter
    st.session_state["_ir_pipe"] = f"{chapter} · {senioridade}"


tab_exec, tab_farol, tab_pipe, tab_ajuda = st.tabs(
    ["Visão Gerencial", "Farol Executivo", "Visão do Pipe", "Como ler"]
)

# ---------------------------------------------------------------------------
# TAB 0 — VISÃO GERENCIAL
# ---------------------------------------------------------------------------
with tab_exec:
    st.markdown("## 🧭 Visão Gerencial")
    st.caption(
        "Resumo executivo do mês: quanto falta contratar, quanto Pipeline Qualificado já existe para "
        "cobrir essa necessidade, e quão rápido e eficiente está o funil. O detalhe por chapter fica "
        "na aba Farol Executivo, e o detalhe por etapa, na Visão do Pipe."
    )

    mes_sel0 = st.selectbox(
        "Mês da demanda", MESES, format_func=lambda m: MES_LABELS[m], key="mes_exec",
        on_change=_sincroniza_mes, args=("mes_exec",),
    )
    st.caption(f"📷 Pipe: foto de **{DATA_SNAPSHOT}**. Ele não muda com o mês, só a demanda muda.")
    mes_ant0 = mes_anterior(mes_sel0)

    df_mes0 = farol_df[farol_df["mes"] == mes_sel0]
    farol_chapters = sorted(farol_df["chapter"].unique())
    demanda_total = float(df_mes0["demanda_liquida"].sum())
    pedido_total = float(df_mes0["demanda_bruta_fte"].sum())
    desalocado_total = float(df_mes0["desalocado_fte"].sum())
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
            f"Source Request de {pedido_total:.0f} menos {desalocado_total:.0f} pessoas que saem de "
            "projeto e podem ser realocadas (Artefactory), somando todos os chapters.",
        ),
        (
            "Pipeline Qualificado atual",
            f"{pipe_qual_total:.0f}",
            _delta_html(pipe_qual_total, pipe_qual_ant, True, "{:.0f}", " candidatos"),
            "Candidatos Entry e Senior da Entrevista Fit até a Oferta, somando os chapters com demanda cadastrada: quem já passou da triagem e do case.",
        ),
        (
            "Tempo médio de contratação",
            f"{tempo_total:.0f} dias" if tempo_total is not None else "—",
            _delta_html(tempo_total, tempo_ant, False, "{:.0f}", " dias"),
            "Média de dias no pipe das pessoas contratadas (Greenhouse), somando todos os chapters.",
        ),
        (
            "Taxa de aceite de oferta",
            f"{aceite_total:.0f}%" if aceite_total is not None else "—",
            _delta_html(aceite_total, aceite_ant, True, "{:.0f}", "pp"),
            "Contratados / (contratados + reprovados na etapa Oferta), somando todos os chapters.",
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

    # mesma leitura do Farol Executivo: decisão por chapter × senioridade
    # (Entry e Senior), não pela soma do chapter, que esconde senioridades
    dec0 = df_mes0[df_mes0["senioridade"].isin(SENIORIDADES_FAROL)]
    acel0 = dec0[dec0["farol_status"] == "acelerar"]
    n_pausa0 = int((dec0["farol_status"] == "pausar").sum())
    lista_acel0 = ", ".join(f"{r['chapter']} {r['senioridade']}" for _, r in acel0.iterrows())
    render_finding(
        f"Em <b>{MES_LABELS[mes_sel0]}</b>: o Source Request é de <b>{pedido_total:.0f} pessoas</b>, "
        f"<b>{desalocado_total:.0f}</b> saem de projeto e podem ser realocadas, e a necessidade líquida "
        f"de contratação fica em <b>{demanda_total:.0f} pessoas</b>, "
        f"com <b>{pipe_qual_total:.0f} candidatos</b> no Pipeline Qualificado (da Entrevista Fit em diante). "
        f"Entre {' e '.join(SENIORIDADES_FAROL)}: <b>{len(acel0)} combinação(ões)</b> pedindo para acelerar"
        + (f" ({lista_acel0})" if lista_acel0 else "")
        + f" e <b>{n_pausa0}</b> para pausar. "
        "Veja a matriz carreira × senioridade na aba <b>Farol Executivo</b>."
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
        "Mês da demanda", MESES, format_func=lambda m: MES_LABELS[m], key="mes_farol",
        on_change=_sincroniza_mes, args=("mes_farol",),
    )
    st.caption(
        f"📷 Pipe: foto de **{DATA_SNAPSHOT}**. Ele não muda com o mês, só a demanda muda. "
        "O mês é o mesmo da Visão Gerencial: trocar aqui troca lá."
    )

    df_mes = farol_df[farol_df["mes"] == mes_sel]
    mes_label_sel = MES_LABELS[mes_sel]
    chapters_farol = sorted(df_mes["chapter"].unique())
    sens_matriz = SENIORIDADES_FAROL

    # O status agora é por chapter × senioridade. O status do chapter
    # inteiro foi removido de propósito: somar as senioridades escondia, por
    # exemplo, Data Engineering em "pausar" precisando contratar Senior.
    decisao = df_mes[df_mes["senioridade"].isin(SENIORIDADES_FAROL)].copy()
    decisao["falta"] = decisao["demanda_liquida"] - decisao["oferta_ajustada"]
    acel = decisao[decisao["farol_status"] == "acelerar"].sort_values("falta", ascending=False)
    paus = decisao[decisao["farol_status"] == "pausar"].sort_values("falta")

    def _lista(df):
        return ", ".join(
            f"<b>{r['chapter']} {r['senioridade']}</b> ({gap_texto(r['gap_pct'], r['demanda_liquida'], r['oferta_ajustada'], curto=True)})"
            for _, r in df.iterrows()
        )

    if acel.empty and paus.empty:
        finding_txt = (
            f"Em <b>{mes_label_sel}</b>, todas as combinações de {' e '.join(SENIORIDADES_FAROL)} "
            "estão em 🟡 manter."
        )
    else:
        partes = []
        if not acel.empty:
            partes.append(f"🟢 <b>acelerar</b>: {_lista(acel)}")
        if not paus.empty:
            partes.append(f"🔴 <b>pausar</b>: {_lista(paus)}")
        finding_txt = f"Em <b>{mes_label_sel}</b>: " + " · ".join(partes) + "."
    render_finding(finding_txt)

    st.markdown("### Farol por carreira × senioridade")
    st.caption(
        "Cada célula é uma decisão: 🟢 acelerar = abrir vagas · 🟡 manter · 🔴 pausar = oferta acima da demanda. "
        f"O farol olha só {' e '.join(SENIORIDADES_FAROL)}: Estagiário segue o ritmo das turmas de estágio e "
        "fica só na Visão do Pipe. Números inteiros, em pessoas. Passe o mouse numa célula para o motivo; "
        "**Ver no pipe ↗** abre a Visão do Pipe já filtrada naquela carreira e senioridade."
    )

    # Grid de divs, não <table>: o Streamlit aplica o estilo dele em
    # tabelas de markdown (bordas retas, fundo) e a matriz ficava "planilha".
    def _celula(r) -> str:
        if r is None:
            return '<div class="fm-card fm-vazia"><div class="fm-vazia-txt">sem demanda nem pipe</div></div>'
        s = r["farol_status"]
        cor = STATUS_COLOR[s]
        tip = _html_attr(farol_insight(s, r["gap_pct"], r["demanda_liquida"], r["oferta_ajustada"]))
        gap = gap_texto(r["gap_pct"], r["demanda_liquida"], r["oferta_ajustada"], curto=True)
        gap = gap[:1].upper() + gap[1:]
        nums = (
            f'<span>Demanda <b>{r["demanda_liquida"]:.0f}</b></span>'
            f'<span>Oferta <b>{r["oferta_ajustada"]:.0f}</b></span>'
        )
        # de onde vem a demanda: Source Request menos quem sai de projeto.
        # Sempre presente, mesmo com zero, para todos os cards terem a mesma altura.
        origem = (
            f'<div class="fm-orig">Source Request {r["demanda_bruta_fte"]:.0f} − desalocados {r["desalocado_fte"]:.0f}</div>'
        )
        return (
            f'<div class="fm-card" style="--fm-cor:{cor}; --fm-bg:{STATUS_BG[s]}" title="{tip}">'
            f'<span class="fm-pill"><span class="fm-dot" style="background:{cor}"></span>{STATUS_LABEL[s]}</span>'
            f'<div class="fm-gap">{gap}</div>'
            f'<div class="fm-num">{nums}</div>{origem}</div>'
        )

    # Matriz em colunas do Streamlit (e não um único bloco HTML) para cada
    # célula ter um botão: clicar leva o recorte para a Visão do Pipe e para
    # o detalhe abaixo. É a ponte do "onde contratar" para o "por que trava".
    larguras = [1.1] + [1] * len(sens_matriz) + [0.95]
    cab = st.columns(larguras, vertical_alignment="bottom")
    for col, s in zip(cab[1:-1], sens_matriz):
        col.markdown(
            f'<div class="fm-th">{s}</div>',
            unsafe_allow_html=True,
        )
    cab[-1].markdown('<div class="fm-th">Total do chapter<span>sem status</span></div>', unsafe_allow_html=True)

    for ch in chapters_farol:
        do_ch = df_mes[df_mes["chapter"] == ch].set_index("senioridade")
        linha = st.columns(larguras, vertical_alignment="top")
        linha[0].markdown(f'<div class="fm-chapter">{ch}</div>', unsafe_allow_html=True)
        for col, s in zip(linha[1:-1], sens_matriz):
            r = do_ch.loc[s] if s in do_ch.index else None
            with col:
                st.markdown(_celula(r), unsafe_allow_html=True)
                if r is not None:
                    st.button(
                        "Ver no pipe ↗", key=f"pipe_{ch}_{s}", type="tertiary",
                        on_click=_ir_para_pipe, args=(ch, s),
                        help=f"Abre a Visão do Pipe filtrada em {ch} · {s}",
                    )
        linha[-1].markdown(
            f'<div class="fm-total">'
            f'<div><span>Source Request</span><b>{do_ch["demanda_bruta_fte"].sum():.0f}</b></div>'
            f'<div><span>− Desalocados</span><b>{do_ch["desalocado_fte"].sum():.0f}</b></div>'
            f'<div class="fm-total-liq"><span>Demanda líquida</span><b>{do_ch["demanda_liquida"].sum():.0f}</b></div>'
            f'<div><span>Oferta</span><b>{do_ch["oferta_ajustada"].sum():.0f}</b></div>'
            f'<div><span>Pipeline Qualificado</span><b>{pipe_qualificado(mes_sel, ch)}</b></div></div>',
            unsafe_allow_html=True,
        )

    # depois do clique: troca para a aba Visão do Pipe. O Streamlit não tem
    # API para trocar de aba, então um script clica no botão da aba.
    destino = st.session_state.pop("_ir_pipe", None)
    if destino:
        st.toast(f"Visão do Pipe filtrada em {destino}.", icon="📈")
        # o destino entra no script para cada clique gerar um iframe novo
        components.html(
            f"""<script>
            // {destino}
            const doc = window.parent.document;
            const alvo = [...doc.querySelectorAll('[role="tab"]')]
                .find(t => t.innerText.includes('Visão do Pipe'));
            if (alvo) {{
                alvo.click();
                doc.querySelectorAll('[data-testid="stMain"], [data-testid="stAppViewContainer"], section.main')
                    .forEach(el => el.scrollTo({{top: 0}}));
                window.parent.scrollTo({{top: 0}});
            }}
            </script>""",
            height=0,
        )
    st.caption(
        "A demanda de cada célula já é líquida: o que os projetos pedem menos as pessoas que saem de projeto "
        "no mês e podem ser realocadas (as duas do Artefactory). Só o que sobra precisa de contratação. "
        "\"Total do chapter\" não tem status de propósito: a soma das senioridades pode dizer pausar "
        "enquanto uma delas precisa de contratação. \"Pipeline Qualificado\" = candidatos Entry e Senior do "
        "chapter da Entrevista Fit até a Oferta, na foto do pipe."
    )

    st.divider()

    chapter_sel = st.selectbox("Chapter para ver o detalhe por senioridade", chapters_farol, key="chapter_sel")
    st.markdown(f"### Demanda × oferta por senioridade em {chapter_sel}")
    st.caption(
        f"{mes_label_sel}. Para cada senioridade, a barra rosa é a demanda líquida (o Source Request menos "
        "quem sai de projeto e pode ser realocado) e a azul é a oferta ajustada do pipe. À direita, quanto falta "
        "ou sobra e o farol. Passe o mouse na barra rosa para ver o Source Request e os desalocados."
    )

    detail = df_mes[df_mes["chapter"] == chapter_sel].copy()
    ordem_sen = {s: i for i, s in enumerate(sens_matriz)}
    detail["_ordem"] = detail["senioridade"].map(ordem_sen).fillna(len(ordem_sen))
    detail = detail.sort_values("_ordem")

    if detail.empty:
        render_note("Sem dado para este chapter neste mês.", variant="warn")
    else:
        # Barras agrupadas em vez do gráfico de halteres: demanda e oferta
        # lado a lado se leem sem legenda de símbolo, e o veredito fica
        # escrito ao lado, na cor do farol.
        rotulos_y = list(detail["senioridade"])
        gaps_txt = [
            gap_texto(g, d, o, curto=True)
            for g, d, o in zip(detail["gap_pct"], detail["demanda_liquida"], detail["oferta_ajustada"])
        ]
        max_val = float(max(detail["oferta_ajustada"].max(), detail["demanda_liquida"].max(), 0.5))

        fig = go.Figure()
        fig.add_trace(
            go.Bar(
                y=rotulos_y,
                x=detail["demanda_liquida"].clip(lower=0),
                name="Demanda líquida",
                orientation="h",
                marker=dict(color=PINK, cornerradius=4),
                text=[f"{v:.0f}" for v in detail["demanda_liquida"]],
                textposition="outside",
                cliponaxis=False,
                customdata=list(zip(detail["demanda_bruta_fte"], detail["desalocado_fte"])),
                hovertemplate=(
                    "<b>%{y}</b><br>Source Request: <b>%{customdata[0]:.0f}</b><br>"
                    "− Desalocados (realocáveis): <b>%{customdata[1]:.0f}</b><br>"
                    "= Demanda líquida: <b>%{text}</b> pessoas<extra></extra>"
                ),
            )
        )
        fig.add_trace(
            go.Bar(
                y=rotulos_y,
                x=detail["oferta_ajustada"],
                name="Oferta ajustada",
                orientation="h",
                marker=dict(color=ARTEFACT_BLUE if THEME == "light" else "#6F86FF", cornerradius=4),
                text=[f"{v:.0f}" for v in detail["oferta_ajustada"]],
                textposition="outside",
                cliponaxis=False,
                hovertemplate="<b>%{y}</b><br>Oferta ajustada: <b>%{text}</b> pessoas<extra></extra>",
            )
        )
        for y, s, gap in zip(rotulos_y, detail["farol_status"], gaps_txt):
            fig.add_annotation(
                x=1.0, xref="paper", xanchor="left", xshift=12,
                y=y, yref="y",
                text=f"<b>{STATUS_LABEL[s].capitalize()}</b> · {gap}",
                showarrow=False,
                font=dict(size=12.5, color=STATUS_COLOR[s]),
            )
        layout = {k: v for k, v in CHART_LAYOUT.items() if k not in ("margin", "yaxis")}
        fig.update_layout(
            barmode="group",
            bargap=0.35,
            bargroupgap=0.08,
            height=max(240, 95 * len(detail)),
            margin=dict(l=10, r=170, t=40, b=10),
            xaxis_title="Pessoas",
            xaxis_range=[0, max_val * 1.18],
            yaxis=dict(autorange="reversed", gridcolor=PAL["line"], tickfont=dict(size=13, color=PAL["ink"])),
            legend=dict(
                orientation="h", yanchor="bottom", y=1.02, x=0,
                font=dict(color=PAL["ink"], size=12.5), traceorder="normal",
            ),
            uniformtext=dict(minsize=10, mode="show"),
            **layout,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("##### Tabela por senioridade")
        tbl = detail[
            ["senioridade", "demanda_bruta_fte", "desalocado_fte", "demanda_liquida", "oferta_ajustada", "gap_pct", "farol_status"]
        ].copy()
        tbl["falta_sobra"] = gaps_txt
        # Gap % só com demanda de pelo menos 1 pessoa: com demanda 0,1 o %
        # explode (-2.536%) e não ajuda a decidir nada
        tbl["gap_pct"] = [
            f"{g:+.0f}%" if pd.notna(g) and d >= 1 else "—"
            for g, d in zip(tbl["gap_pct"], tbl["demanda_liquida"])
        ]
        tbl["demanda_bruta_fte"] = tbl["demanda_bruta_fte"].map(lambda v: f"{v:.0f}")
        tbl["desalocado_fte"] = tbl["desalocado_fte"].map(lambda v: f"−{v:.0f}" if v else "0")
        tbl["demanda_liquida"] = tbl["demanda_liquida"].map(lambda v: f"{v:.0f}")
        tbl["oferta_ajustada"] = tbl["oferta_ajustada"].map(lambda v: f"{v:.0f}")
        tbl["farol_status"] = tbl["farol_status"].map(lambda s: f"{STATUS_ICON[s]} {STATUS_LABEL[s]}")
        tbl = tbl[
            ["senioridade", "demanda_bruta_fte", "desalocado_fte", "demanda_liquida", "oferta_ajustada",
             "falta_sobra", "gap_pct", "farol_status"]
        ]
        tbl.columns = [
            "Senioridade", "Source Request", "Desalocados", "Demanda líquida", "Oferta ajustada",
            "Falta / sobra", "Gap %", "Status",
        ]
        render_table(
            tbl,
            numeric_cols={"Source Request", "Desalocados", "Demanda líquida", "Oferta ajustada", "Gap %"},
            help_map={
                "Source Request": "Quanto os projetos pedem de gente no mês (Artefactory, em FTE; 1 FTE = 1 contratação).",
                "Desalocados": "Pessoas que saem de projeto no mês e podem ser realocadas, em vez de contratar (Artefactory).",
                "Demanda líquida": "Source Request menos desalocados: o que sobra para contratar.",
                "Oferta ajustada": "Candidatos vivos do Envio do Case em diante, cada um pesado pela chance de virar contratação em até 45 dias.",
                "Gap %": "(Demanda − Oferta) / Demanda. Só aparece com demanda de 1 pessoa ou mais.",
                "Status": "Diferença menor que 1 pessoa = manter. Demanda zero ou negativa = pausar. Senão: acima de +20% acelerar, abaixo de −10% pausar.",
            },
        )

# ---------------------------------------------------------------------------
# TAB 2 — VISÃO DO PIPE
# ---------------------------------------------------------------------------
with tab_pipe:
    st.markdown("## 📈 Visão Completa do Pipe")
    st.caption(
        "Conversão, tempo por etapa, distribuição de candidatos e alertas de gargalo do funil de "
        "contratação no Greenhouse."
    )

    # Sem seletor de mês aqui de propósito: nenhuma view do Greenhouse tem
    # data, então o funil é sempre a foto de hoje. O seletor de mês existe
    # só nas abas que leem a demanda (Visão Gerencial e Farol Executivo).
    mes_sel2 = MES_SNAPSHOT
    chapters_pipe = sorted(pipe_df["chapter"].unique())
    sens_presentes = set(pipe_nivel_df["senioridade"])
    sens_pipe = [s for s in SENIORIDADE_ORDER if s in sens_presentes] + sorted(
        sens_presentes - set(SENIORIDADE_ORDER)
    )
    col_fc, col_fs = st.columns(2)
    with col_fc:
        chapter_sel2 = st.selectbox("Chapter", [TODOS] + chapters_pipe, key="chapter_pipe")
    with col_fs:
        sen_sel2 = st.selectbox("Senioridade", [TODOS] + sens_pipe, key="senioridade_pipe")
    rotulo_recorte = (
        ("todos os chapters" if chapter_sel2 == TODOS else chapter_sel2)
        + " · "
        + ("todas as senioridades" if sen_sel2 == TODOS else sen_sel2)
    )
    st.caption(
        f"📷 Pipe: foto de **{DATA_SNAPSHOT}**. O Greenhouse não guarda histórico por etapa. "
        f"**Os dois filtros valem para a aba inteira** (recorte atual: {rotulo_recorte}). A exceção são "
        "os dois gráficos \"por carreira\", que comparam chapters: eles seguem só a senioridade."
    )

    # o azul da marca some no fundo escuro: no tema escuro, um azul mais claro
    azul_barra = ARTEFACT_BLUE if THEME == "light" else "#6F86FF"

    # pipe no recorte escolhido: por etapa, e por chapter × etapa
    nivel_rec = recorte(pipe_nivel_df[pipe_nivel_df["mes"] == mes_sel2], chapter_sel2, sen_sel2)
    if nivel_rec.empty:
        render_note(f"Sem candidaturas no recorte {rotulo_recorte}.", variant="neutral")
        st.stop()
    dfp_rec = resumo_pipe(nivel_rec, ["etapa", "ordem_etapa"]).sort_values("ordem_etapa")
    dfp_mes = resumo_pipe(nivel_rec, ["chapter", "etapa", "ordem_etapa"])

    def _n(valor) -> str:
        """Inteiro no formato brasileiro: 57312 -> 57.312."""
        return f"{int(round(valor)):,}".replace(",", ".")

    # ---- KPIs: cada título diz a etapa onde a conta começa ---------------
    contr_fit, base_fit, conv_fit = conversao_ate_contratacao("Entrevista Fit", chapter_sel2, sen_sel2)
    _, base_case, conv_case = conversao_ate_contratacao("Envio do Case Escrito", chapter_sel2, sen_sel2)
    _, base_cv, _ = conversao_ate_contratacao("Avaliação de currículo", chapter_sel2, sen_sel2)
    aceite_rec = taxa_aceite_oferta(mes_sel2, chapter_sel2, sen_sel2)
    tx_rec = recorte(taxas_df, chapter_sel2, sen_sel2)
    n_decididas = tx_rec["contratados"].sum() + tx_rec["recusas_oferta"].sum()
    aceite_sys_rec = taxa_aceite_sys(mes_sel2, chapter_sel2, sen_sel2)
    su_rec = recorte(su_ofertas_df, chapter_sel2, sen_sel2) if not su_ofertas_df.empty else su_ofertas_df
    n_su = su_rec["candidaturas_sys"].sum() if not su_rec.empty else 0
    n_su_aceites = su_rec["aceites_sys"].sum() if not su_rec.empty else 0
    su_tempo_banco = su_tempo_medio_banco(chapter_sel2, sen_sel2)

    if conv_fit is not None:
        nota_fit = f"{_n(contr_fit)} contratações de {_n(base_fit)} candidaturas que chegaram à Entrevista Fit."
        if conv_case is not None:
            nota_fit += f" Desde o Envio do Case: {conv_case:.1f}%."
        if contr_fit:
            nota_fit += f" Desde o currículo: 1 a cada {_n(base_cv / contr_fit)}."
    else:
        nota_fit = "Ninguém chegou à Entrevista Fit neste recorte."

    pipe_kpi_cards = [
        (
            "Entrevista Fit → contratação",
            f"{conv_fit:.1f}%" if conv_fit is not None else "—",
            nota_fit,
        ),
        (
            "Oferta → contratação (aceite)",
            f"{aceite_rec:.0f}%" if aceite_rec is not None else "—",
            f"{_n(tx_rec['contratados'].sum())} contratados de {_n(n_decididas)} pessoas com a oferta já "
            "decidida (contratadas + reprovadas na Oferta). Quem ainda está em Oferta fica fora.",
        ),
        (
            "See You Soon → contratação",
            f"{aceite_sys_rec:.0f}%" if aceite_sys_rec is not None else "—",
            f"{_n(n_su_aceites)} de {_n(n_su)} pessoas que passaram pelo banco aceitaram uma oferta.",
        ),
        (
            "Espera média no banco See You Soon",
            f"{su_tempo_banco:.0f} dias" if su_tempo_banco is not None else "—",
            "Média entre as pessoas hoje aguardando no banco. O Greenhouse só informa o tempo "
            "médio por vaga, então cada pessoa recebe o valor da sua vaga.",
        ),
    ]
    st.markdown(
        f'<div class="exec-kpi-scope">Recorte: <b>{rotulo_recorte}</b> · conversões no histórico inteiro do Greenhouse</div>'
        '<div class="exec-kpi-row">'
        + "".join(
            f'<div class="exec-kpi-card"><div class="exec-kpi-label">{label}</div>'
            f'<div class="exec-kpi-value">{value}</div>'
            f'<div class="exec-kpi-note">{note}</div></div>'
            for label, value, note in pipe_kpi_cards
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    sla_calc = dfp_mes.dropna(subset=["excesso_dias"])
    n_crit_pipe = int((sla_calc["status_sla"] == "critico").sum())
    if n_crit_pipe:
        top_gargalo_calc = sla_calc.sort_values("excesso_dias", ascending=False).iloc[0]
        texto_sla = (
            f"<b>{n_crit_pipe} etapa(s) em SLA crítico</b>. A pior é <b>{top_gargalo_calc['etapa']}</b> em "
            f"{top_gargalo_calc['chapter']} ({top_gargalo_calc['tempo_medio_dias']:.0f}d vs. meta de "
            f"{top_gargalo_calc['meta_sla_dias']:.0f}d)"
        )
    else:
        texto_sla = "Nenhuma etapa em SLA crítico"
    render_finding(f"{rotulo_recorte[0].upper()}{rotulo_recorte[1:]}: {texto_sla}.")

    st.markdown('<div class="pipe-sec"><span>1 · Onde trava</span>etapas acima da meta</div>', unsafe_allow_html=True)
    st.markdown("##### Gargalos e SLA")
    st.caption(
        f"Tempo médio de cada etapa contra a meta, por chapter, no recorte escolhido ({rotulo_recorte}). "
        "Na ordem do funil, chapter por chapter; o pior gargalo aparece destacado abaixo da tabela."
    )

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
            f'<div class="exec-kpi-note">combinações chapter × etapa no recorte</div></div>'
            for label, count, color in resumo_status
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    sla_df = dfp_mes.dropna(subset=["excesso_dias"]).copy()
    # ordem do funil, não do excesso: lida etapa a etapa, a tabela mostra
    # onde o processo trava; o pior caso vai para o alerta logo abaixo
    pior_sla = sla_df.sort_values("excesso_dias", ascending=False).head(1)
    sla_df = sla_df.sort_values(["chapter", "ordem_etapa"])[
        ["chapter", "etapa", "tempo_medio_dias", "meta_sla_dias", "excesso_dias", "status_sla"]
    ]
    sla_df.columns = ["Chapter", "Etapa", "Tempo médio (dias)", "Meta (dias)", "Excesso (dias)", "Status"]

    STATUS_SLA_LABEL = {"critico": "🔴 CRÍTICO", "atencao": "🟡 ATENÇÃO", "ok": "🟢 OK"}
    sla_df["Tempo médio (dias)"] = sla_df["Tempo médio (dias)"].map(lambda v: f"{v:.1f}")
    sla_df["Meta (dias)"] = sla_df["Meta (dias)"].map(lambda v: f"{v:.0f}")
    sla_df["Excesso (dias)"] = sla_df["Excesso (dias)"].map(lambda v: f"{v:+.1f}")
    sla_df["Status"] = sla_df["Status"].map(STATUS_SLA_LABEL).fillna(sla_df["Status"])

    render_table(
        sla_df,
        numeric_cols={"Tempo médio (dias)", "Meta (dias)", "Excesso (dias)"},
        help_map={
            "Tempo médio (dias)": "Tempo médio corrido que um candidato permanece nesta etapa (média do Greenhouse por vaga).",
            "Meta (dias)": "SLA alvo definido para esta etapa.",
            "Excesso (dias)": "Tempo médio − meta. Negativo significa que a etapa está dentro do prazo.",
            "Status": "🔴 Crítico: excesso > 5 dias · 🟡 Atenção: até 5 dias de excesso · 🟢 OK: dentro da meta.",
        },
    )

    top_gargalo = pior_sla.iloc[0] if not pior_sla.empty else None
    if top_gargalo is not None and top_gargalo["status_sla"] == "critico":
        render_note(
            f"🔴 <b>Pior gargalo:</b> {top_gargalo['etapa']} em {top_gargalo['chapter']}: "
            f"{top_gargalo['tempo_medio_dias']:.1f} dias vs. meta de {top_gargalo['meta_sla_dias']:.0f} dias.",
            variant="critical",
        )

    st.markdown('<div class="pipe-sec"><span>2 · Por que trava</span>conversão e tempo em cada etapa</div>', unsafe_allow_html=True)
    col_a, col_b = st.columns(2)
    with col_a:
        st.markdown("##### Funil de volume a partir do Envio do Case")
        # Contratação fica fora: é o total histórico de contratados, e no
        # meio do estoque de hoje aparecia como "116% do Envio do Case"
        funil_vis = dfp_rec[(dfp_rec["ordem_etapa"] >= 2) & (dfp_rec["etapa"] != "Contratação")]
        n_cv = int(dfp_rec.loc[dfp_rec["etapa"] == "Avaliação de currículo", "candidatos"].sum())
        n_case_vis = funil_vis["candidatos"].iloc[0] if not funil_vis.empty else 0
        st.caption(
            "Candidatos vivos hoje em cada etapa; o % é sobre o Envio do Case. "
            f"A triagem de currículo ({_n(n_cv)} hoje) fica fora para não achatar as outras etapas, e as "
            f"contratações ({_n(contr_fit)} no histórico) estão no card Entrevista Fit → contratação."
        )
        fig_funnel = go.Figure(
            go.Funnel(
                y=funil_vis["etapa"],
                x=funil_vis["candidatos"],
                marker={"color": azul_barra},
                connector={"line": {"color": PAL["line"], "width": 1}},
                # com zero no Envio do Case o % vira "Infinity%": mostra só o número
                textinfo="value+percent initial" if n_case_vis > 0 else "value",
                hovertemplate=(
                    "<b>%{label}</b><br>"
                    "Candidatos: <b>%{value}</b>"
                    + ("<br>%{percentInitial} do volume no Envio do Case" if n_case_vis > 0 else "")
                    + "<extra></extra>"
                ),
            )
        )
        fig_funnel.update_layout(height=380, **CHART_LAYOUT)
        st.plotly_chart(fig_funnel, use_container_width=True)

    with col_b:
        st.markdown("##### Conversão etapa a etapa, a partir do currículo")
        st.caption(
            "Cada barra: % que chegou a esta etapa vindo da anterior (a primeira, Envio do Case, vem do "
            "currículo). Taxa do Greenhouse, com teto de 100% por vaga."
        )
        conv = dfp_rec.dropna(subset=["conversao_pct"])
        bar_colors = [PINK if et == "Contratação" else azul_barra for et in conv["etapa"]]
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

        etapa_click_conv = _clicked_category(conv_event)
        guard_conv = f"{mes_sel2}|{sen_sel2}|{etapa_click_conv}"
        if not etapa_click_conv:
            # seleção limpa (clique fora da barra): libera a mesma barra para
            # abrir o modal de novo no próximo clique
            st.session_state.pop("_last_conv_click", None)
        elif st.session_state.get("_last_conv_click") != guard_conv:
            st.session_state["_last_conv_click"] = guard_conv
            show_conv_drilldown(etapa_click_conv, mes_sel2, sen_sel2)

    st.markdown("##### Tempo médio por etapa")
    st.caption(
        "Dias corridos que um candidato fica em cada etapa, no recorte escolhido (média do Greenhouse por vaga, "
        "ponderada pelas candidaturas). **Oferta e See You Soon ficam separadas**: a barra rosa é o tempo no "
        "banco See You Soon e não entra na média da Oferta. Uma Oferta longa pode ser negociação demorada ou "
        "registro não atualizado no Greenhouse."
    )
    tempo_agg = dfp_rec.dropna(subset=["tempo_medio_dias"])[["etapa", "tempo_medio_dias"]].copy()
    tempo_agg["cor"] = azul_barra
    if su_tempo_banco is not None:
        linha_su = pd.DataFrame(
            [{"etapa": ETAPA_SU, "tempo_medio_dias": round(su_tempo_banco, 1), "cor": PINK}]
        )
        tempo_agg = pd.concat([tempo_agg, linha_su], ignore_index=True)
    if tempo_agg.empty:
        render_note("Sem dado de tempo médio para este recorte.", variant="neutral")
    else:
        fig_tempo_agg = go.Figure(
            go.Bar(
                x=tempo_agg["etapa"],
                y=tempo_agg["tempo_medio_dias"],
                marker_color=list(tempo_agg["cor"]),
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
        chart_hint(
            "Clique em uma barra azul para ver a quebra por chapter, ou na rosa para ver quem está no banco."
        )

        etapa_click_tempo = _clicked_category(tempo_event, axis="x")
        guard_tempo = f"{mes_sel2}|{sen_sel2}|{etapa_click_tempo}"
        if not etapa_click_tempo:
            st.session_state.pop("_last_tempo_click", None)
        elif st.session_state.get("_last_tempo_click") != f"{guard_tempo}|{chapter_sel2}":
            st.session_state["_last_tempo_click"] = f"{guard_tempo}|{chapter_sel2}"
            if etapa_click_tempo == ETAPA_SU:
                show_su_drilldown(chapter_sel2, sen_sel2)
            else:
                show_tempo_drilldown(etapa_click_tempo, mes_sel2, sen_sel2)

    st.markdown('<div class="pipe-sec"><span>3 · Onde está o volume</span>candidatos vivos por etapa</div>', unsafe_allow_html=True)
    st.markdown("##### Candidatos por etapa × chapter (heatmap)")
    st.caption(
        "Candidatos vivos hoje em cada etapa, do Envio do Case até a Oferta, no recorte escolhido. Células "
        "mais escuras indicam mais gente aguardando ali. A triagem de currículo fica na faixa abaixo, só para "
        "monitoramento: com milhares de currículos, ela dominava a escala e apagava as outras etapas. "
        "Contratação também fica fora, porque é histórico, não gente aguardando."
    )
    # Triagem de currículo: só monitoramento, fora da escala de cor
    triagem = (
        dfp_mes[dfp_mes["etapa"] == "Avaliação de currículo"]
        .groupby("chapter")["candidatos"].sum()
        .sort_values(ascending=False)
    )
    if not triagem.empty:
        st.markdown(
            '<div class="triagem-row"><span class="triagem-lbl">Triagem de currículo · monitoramento</span>'
            + "".join(
                f'<span class="triagem-chip">{ch} <b>{_n(v)}</b></span>' for ch, v in triagem.items()
            )
            + "</div>",
            unsafe_allow_html=True,
        )
    etapas_heat = [
        s for s in STAGES_ORDER if s not in ("Avaliação de currículo", "Contratação")
    ]
    pivot = dfp_mes[dfp_mes["etapa"].isin(etapas_heat)].pivot_table(
        index="chapter", columns="etapa", values="candidatos", aggfunc="sum"
    )
    pivot = pivot.reindex(columns=[s for s in etapas_heat if s in pivot.columns])
    if pivot.empty:
        render_note("Ninguém do Envio do Case em diante neste recorte.", variant="neutral")
    else:
        fig_heat = px.imshow(
            pivot,
            text_auto=True,
            color_continuous_scale=brand_heat_scale(),
            aspect="auto",
            labels=dict(color="Candidatos", x="", y=""),
        )
        fig_heat.update_traces(
            hovertemplate="<b>%{y}</b> · %{x}<br>Candidatos: <b>%{z}</b><extra></extra>"
        )
        fig_heat.update_layout(height=max(160, 55 * len(pivot) + 60), **CHART_LAYOUT)
        st.plotly_chart(fig_heat, use_container_width=True)

    st.markdown("##### Volume de candidatos por etapa e por nível")
    st.caption(
        "Mesmo recorte dos filtros do topo, aberto por chapter × senioridade. 🔺 marca combinações com "
        "volume bem acima do normal para aquela etapa."
    )
    nivel_mes = nivel_rec

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

    st.markdown('<div class="pipe-sec"><span>4 · Quem está travado</span>candidatos acima da meta</div>', unsafe_allow_html=True)
    st.markdown("##### Candidatos parados por etapa")
    st.caption(
        "Candidatos em atenção e crítico em cada etapa do funil, no recorte escolhido. Antes de agir, confira "
        "no Greenhouse: etapa desatualizada (ex.: pessoa já contratada ainda em Conversa Final) aparece aqui como parada."
    )

    parados_mes = (
        recorte(parados_df[parados_df["mes"] == mes_sel2], chapter_sel2, sen_sel2)
        if not parados_df.empty
        else parados_df
    )
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
        # meta_sla_dias aqui é o prazo ACUMULADO até a etapa (ver load_data):
        # é contra ele que os dias no pipe são comparados
        prazos_etapa = parados_df.groupby("etapa")["meta_sla_dias"].max().to_dict()
        contagem_parados = parados_mes.groupby(["etapa", "status"]).size().to_dict()
        larguras = [1.45] + [1] * len(etapas_parados)

        cabecalho = st.columns(larguras)
        cabecalho[0].markdown('<div class="stage-th">Status</div>', unsafe_allow_html=True)
        for coluna, etapa_col in zip(cabecalho[1:], etapas_parados):
            prazo = prazos_etapa.get(etapa_col)
            nota = ""
            if prazo is not None and pd.notna(prazo):
                nota = (
                    f'<span class="th-note">Atenção: {int(prazo) + 1}–{int(prazo) + 5}d no pipe'
                    f'<br>Crítico: &gt;{int(prazo) + 5}d no pipe</span>'
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
            f"Atenção: dias no pipe acima da soma das metas até a etapa</div>"
            f'<div class="legend-item"><span class="legend-dot" style="background:{RED}"></span>'
            f"Crítico: mais de 5 dias acima dessa soma</div>"
            f"</div>",
            unsafe_allow_html=True,
        )

        if abrir_parados and st.session_state.get("_parados_sel"):
            _sel = st.session_state["_parados_sel"]
            if _sel.get("vaga"):
                show_parados_candidatos(_sel["etapa"], _sel["status"], _sel["vaga"], mes_sel2)
            else:
                show_parados_vagas(_sel["etapa"], _sel["status"], mes_sel2)

    st.markdown('<div class="pipe-sec"><span>5 · Comparação entre carreiras</span>não segue o filtro de chapter, só o de senioridade</div>', unsafe_allow_html=True)
    def _cores_destaque(chapters, cor):
        """Destaca o chapter do filtro; os outros ficam apagados."""
        if chapter_sel2 == TODOS:
            return cor
        return [cor if ch == chapter_sel2 else PAL["line"] for ch in chapters]

    rotulo_sen = "todas as senioridades" if sen_sel2 == TODOS else sen_sel2
    col_ag, col_as = st.columns(2)
    with col_ag:
        st.markdown("##### Oferta → contratação, por carreira")
        st.caption(
            f"Compara chapters ({rotulo_sen}). "
            "Contratados / (contratados + reprovados na etapa Oferta), no histórico do Greenhouse."
        )
        chapters_aceite = sorted(taxas_df["chapter"].unique())
        aceite_vals = [taxa_aceite_oferta(mes_sel2, ch, sen_sel2) for ch in chapters_aceite]
        fig_aceite_geral = go.Figure(
            go.Bar(
                x=chapters_aceite,
                y=[v if v is not None else 0 for v in aceite_vals],
                marker_color=_cores_destaque(chapters_aceite, azul_barra),
                text=[f"{v:.0f}%" if v is not None else "—" for v in aceite_vals],
                textposition="outside",
                hovertemplate="<b>%{x}</b><br>Aceite: <b>%{y:.0f}%</b><extra></extra>",
            )
        )
        fig_aceite_geral.update_layout(
            height=300,
            yaxis=dict(range=[0, 110], **CHART_LAYOUT["yaxis"]),
            **{k: v for k, v in CHART_LAYOUT.items() if k != "yaxis"},
        )
        st.plotly_chart(fig_aceite_geral, use_container_width=True)

    with col_as:
        st.markdown("##### See You Soon → contratação, por carreira")
        st.caption(
            f"Compara chapters ({rotulo_sen}). "
            "% das pessoas que passaram pelo banco e aceitaram oferta."
        )
        chapters_sys = sorted(su_ofertas_df["chapter"].unique()) if not su_ofertas_df.empty else []
        if chapters_sys:
            aceite_sys_vals = [taxa_aceite_sys(mes_sel2, ch, sen_sel2) for ch in chapters_sys]
            fig_aceite_sys = go.Figure(
                go.Bar(
                    x=chapters_sys,
                    y=[v if v is not None else 0 for v in aceite_sys_vals],
                    marker_color=_cores_destaque(chapters_sys, PINK),
                    text=[f"{v:.0f}%" if v is not None else "—" for v in aceite_sys_vals],
                    textposition="outside",
                    hovertemplate="<b>%{x}</b><br>Conversão do banco: <b>%{y:.0f}%</b><extra></extra>",
                )
            )
            fig_aceite_sys.update_layout(
                height=300,
                yaxis=dict(range=[0, 110], **CHART_LAYOUT["yaxis"]),
                **{k: v for k, v in CHART_LAYOUT.items() if k != "yaxis"},
            )
            st.plotly_chart(fig_aceite_sys, use_container_width=True)
        else:
            render_note("Sem dado do banco See You Soon.", variant="neutral")


# ---------------------------------------------------------------------------
# TAB 3 · COMO LER
# Glossário escrito a partir das regras do código. Quando uma regra mudar
# (farol_status, oferta, SLA), atualizar o texto aqui junto.
# ---------------------------------------------------------------------------
def _secao(icone: str, titulo: str, subtitulo: str = "") -> None:
    st.markdown(
        f'<div class="cl-secao"><span class="cl-secao-ico">{icone}</span>'
        f'<div><div class="cl-secao-tit">{titulo}</div>'
        + (f'<div class="cl-secao-sub">{subtitulo}</div>' if subtitulo else "")
        + "</div></div>",
        unsafe_allow_html=True,
    )


def _termos(itens: list) -> None:
    """Lista de termos: nome à esquerda, explicação à direita."""
    st.markdown(
        '<div class="cl-lista">'
        + "".join(
            f'<div class="cl-termo"><div class="cl-termo-nome">{nome}</div>'
            f'<div class="cl-termo-def">{definicao}</div></div>'
            for nome, definicao in itens
        )
        + "</div>",
        unsafe_allow_html=True,
    )


with tab_ajuda:
    st.markdown(
        '<div class="cl-hero">'
        '<div class="cl-hero-tit">📖 Como ler o Farol</div>'
        '<div class="cl-hero-txt">O que cada aba responde, como cada número é calculado, de onde vêm os '
        "dados e o que eles ainda não conseguem dizer. As explicações curtas continuam nos (?) das tabelas "
        "e nas legendas dos gráficos. Aqui está tudo junto.</div></div>",
        unsafe_allow_html=True,
    )

    # ---- as abas ----------------------------------------------------------
    _secao("🗂️", "As abas", "Cada uma responde a uma pergunta.")
    abas = [
        ("🧭", "Visão Gerencial", "Quanto falta contratar no mês e com que velocidade o funil entrega?",
         "Necessidade líquida, Pipeline Qualificado, tempo médio de contratação e aceite de oferta. "
         "O mês escolhido aqui é o mesmo do Farol Executivo."),
        ("🚦", "Farol Executivo", "Devo abrir, manter ou pausar vagas? Em qual carreira e senioridade?",
         "Matriz carreira × senioridade e o detalhe de demanda × oferta de cada chapter. "
         "<b>Ver no pipe ↗</b> em uma célula leva aquele recorte para a Visão do Pipe."),
        ("📈", "Visão do Pipe", "Onde o processo trava?",
         "Lida do macro para o micro: onde trava, por que trava, onde está o volume, quem está parado "
         "e, por último, a comparação entre carreiras. Os filtros do topo valem para a aba inteira."),
    ]
    st.markdown(
        '<div class="cl-abas">'
        + "".join(
            f'<div class="cl-aba"><div class="cl-aba-ico">{ico}</div>'
            f'<div class="cl-aba-nome">{nome}</div><div class="cl-aba-perg">{perg}</div>'
            f'<div class="cl-aba-txt">{txt}</div></div>'
            for ico, nome, perg, txt in abas
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # ---- o farol ----------------------------------------------------------
    _secao("🚦", "Como o farol decide", "As regras são testadas nesta ordem, por carreira × senioridade.")
    passos = [
        ("manter", "1", f"Diferença menor que {GAP_MINIMO_PESSOAS:.0f} pessoa", "Manter"),
        ("pausar", "2", "Demanda zero ou negativa", "Pausar"),
        ("acelerar", "3", "Gap % acima de +20%", "Acelerar"),
        ("manter", "3", "Gap % entre −10% e +20%", "Manter"),
        ("pausar", "3", "Gap % abaixo de −10%", "Pausar"),
    ]
    st.markdown(
        '<div class="cl-regras">'
        + "".join(
            f'<div class="cl-regra" style="--cl-cor:{STATUS_COLOR[s]}; --cl-bg:{STATUS_BG[s]}">'
            f'<div class="cl-regra-n">{n}</div><div class="cl-regra-cond">{cond}</div>'
            f'<div class="cl-regra-res"><span class="cl-dot"></span>{res}</div></div>'
            for s, n, cond, res in passos
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    _termos([
        ("Source Request",
         "Quanto os projetos pedem de gente no mês, segundo o Artefactory. Vem em FTE: 1 FTE é uma pessoa "
         "em tempo integral. Confirmado: <b>1 FTE = 1 contratação</b>. O farol mostra tudo em números "
         "inteiros, arredondando meio para cima."),
        ("Desalocados",
         "Pessoas que saem de projeto no mês, na mesma carreira e nível, e podem ser realocadas em vez de "
         "contratar alguém. Também vêm do Artefactory."),
        ("Demanda líquida",
         "Source Request menos desalocados: o que sobra para contratar. É ela que o farol compara com a "
         "oferta. Fica negativa quando sai mais gente de projeto do que "
         "entra. A matriz, o detalhe e a Visão Gerencial mostram as três partes."),
        ("Oferta ajustada",
         f"Quantas contratações o pipe de hoje deve entregar em até {HORIZONTE_FAROL_DIAS} dias. Soma os "
         "candidatos vivos do <b>Envio do Case em diante</b>, cada um pesado pela chance de chegar à "
         "contratação. A triagem de currículo e o banco See You Soon não entram."),
        ("Gap",
         "Demanda líquida menos oferta ajustada. Positivo quer dizer que <b>falta</b> gente; negativo, que "
         "<b>sobra</b>. O Gap % divide o gap pela demanda e só aparece com demanda de 1 pessoa ou mais."),
        ("Status por senioridade",
         "Somar as senioridades esconde decisões opostas: um chapter pode sobrar Entry e faltar Senior ao "
         "mesmo tempo. Por isso o \"Total do chapter\" mostra só os números, sem status."),
        ("Entry e Senior",
         "O farol olha só Entry e Senior. Estagiário fica fora, porque segue o ritmo das turmas de estágio, "
         "e aparece só na Visão do Pipe. Entry inclui os níveis Entry e Associate do Artefactory "
         "e as vagas do Greenhouse sem nível no nome."),
        ("Mês da demanda",
         f"Só a demanda muda com o mês. O app mostra o mês atual e os {JANELA_MESES} seguintes. O pipe é "
         "sempre a foto de hoje, então a oferta é a mesma em todos os meses."),
        ("Pipeline Qualificado",
         "Candidatos Entry e Senior vivos hoje da <b>Entrevista Fit</b> até a Oferta (Entrevista Fit, Técnica 1, "
         "Técnica 2, Conversa Final e Oferta), ou seja, quem já passou da triagem e do case. É contagem de "
         "pessoas. A Oferta é outra conta: começa no Envio do Case e pesa cada candidato pela chance de "
         f"contratar em até {HORIZONTE_FAROL_DIAS} dias, por isso sai menor."),
    ])

    # ---- conversões e tempos ---------------------------------------------
    _secao("🔁", "Conversões e tempos", "Toda conversão diz em que etapa começa a conta.")
    _termos([
        ("Entrevista Fit → contratação",
         "Contratados divididos pelas candidaturas que chegaram à Entrevista Fit, no histórico inteiro do "
         "Greenhouse. É a conversão principal porque começa depois da triagem. O card também mostra a conta "
         "desde o Envio do Case e desde o currículo."),
        ("Conversão etapa a etapa",
         "Quantos % chegaram a uma etapa vindos da anterior, segundo o Greenhouse. Quando candidatos pulam "
         "etapas o número do Greenhouse passa de 100%, então o app limita cada vaga a 100%."),
        ("Oferta → contratação",
         "Contratados divididos por contratados mais reprovados na etapa Oferta. Quem ainda está em Oferta "
         "fica fora, porque não decidiu. O Greenhouse não registra oferta recusada, então a recusa é quem "
         "saiu do processo estando na Oferta."),
        ("See You Soon → contratação",
         "Pessoas que passaram pelo banco See You Soon e aceitaram uma oferta, divididas por todas que "
         "passaram pelo banco. Não é taxa de aceite: o banco não registra oferta recusada."),
        ("Espera no See You Soon",
         "Dias que quem está aguardando hoje já passou no banco. O Greenhouse só dá a média por vaga, então "
         "pessoas da mesma vaga têm o mesmo número. Clique na barra rosa do tempo por etapa para ver a lista."),
        ("Tempo médio por etapa",
         "Dias corridos que um candidato fica em cada etapa, pela média do Greenhouse por vaga, ponderada "
         "pelas candidaturas. O See You Soon tem barra própria e não entra na média da Oferta."),
        ("Tempo médio de contratação",
         "Média de dias no pipe das pessoas contratadas. Não é a soma dos tempos de cada etapa, que inclui "
         "quem ficou parado e foi reprovado."),
    ])

    # ---- metas -------------------------------------------------------------
    _secao("⏱️", "Metas, parados e gargalos", "Meta de dias em cada etapa do funil.")
    metas = [
        ("Avaliação de currículo", 30), ("Envio do Case", 3), ("Avaliação do case", 3),
        ("Entrevista Fit", 20), ("Técnica 1", 10), ("Técnica 2", 7), ("Conversa Final", 7), ("Oferta", 7),
    ]
    st.markdown(
        '<div class="cl-metas">'
        + "".join(
            f'<div class="cl-meta"><div class="cl-meta-d">{d}d</div><div class="cl-meta-e">{e}</div></div>'
            for e, d in metas
        )
        + "</div>",
        unsafe_allow_html=True,
    )
    _termos([
        ("Candidato parado",
         "Compara os dias no pipe com a soma das metas até a etapa em que a pessoa está. Acima da soma, "
         "<b>atenção</b>. Mais de 5 dias acima, <b>crítico</b>. O Greenhouse não dá o tempo por etapa de cada "
         "pessoa, por isso a conta usa o tempo no pipe inteiro."),
        ("Gargalos e SLA",
         "Tempo médio de cada etapa contra a meta, por chapter. Acima da meta, atenção. Mais de 5 dias acima, "
         "crítico. A tabela segue a ordem do funil, e o pior caso aparece no alerta logo abaixo dela."),
    ])

    # ---- dados ---------------------------------------------------------------
    _secao("🗄️", "De onde vêm os dados")
    fontes = [
        ("Demanda", "Artefactory",
         "Source Request (pedidos dos projetos) e desalocações, carregados por upload manual no BigQuery. O farol fica tão "
         "atual quanto o último upload."),
        ("Pipe", "Greenhouse",
         f"Foto do dia (hoje: <b>{DATA_SNAPSHOT}</b>). O Greenhouse não guarda histórico por etapa, então não "
         "há evolução mês a mês do funil."),
        ("Acesso", "Google + BigQuery",
         "Login com Google e lista de e-mails autorizados, mantida no BigQuery pelo time de Dados."),
    ]
    st.markdown(
        '<div class="cl-abas">'
        + "".join(
            f'<div class="cl-aba"><div class="cl-fonte-tag">{tag}</div>'
            f'<div class="cl-aba-nome">{nome}</div><div class="cl-aba-txt">{txt}</div></div>'
            for tag, nome, txt in fontes
        )
        + "</div>",
        unsafe_allow_html=True,
    )

    # ---- limites -------------------------------------------------------------
    _secao("⚠️", "O que os números ainda não dizem", "Leve isto em conta antes de decidir.")
    limites = [
        ("Realocações que o farol não vê",
         "O desconto de desalocados vale só dentro da mesma carreira e nível, e só para saídas lançadas no "
         "Artefactory. Quem muda de carreira ou nível, ou sai de projeto sem estar lançado, não entra. Os "
         "meses mais distantes costumam ter poucas desalocações lançadas, então a demanda líquida deles tende "
         "a vir alta."),
        ("Carreiras sem farol",
         "AI Engineering e Software Engineering têm pipe no Greenhouse, mas nenhuma demanda no Artefactory. "
         "Aparecem na Visão do Pipe, não no Farol."),
        ("Etapas desatualizadas",
         "Quem avançou ou foi contratado sem a etapa atualizada no Greenhouse aparece como parado e distorce "
         "tempos e gargalos. Confira no Greenhouse antes de agir."),
        ("Senioridade pelo nome da vaga",
         "O Greenhouse não tem campo de senioridade, então ela sai do nome da vaga. Vaga sem nível no nome "
         f"aparece como \"{SEM_SENIORIDADE}\" e fica fora do farol."),
    ]
    st.markdown(
        '<div class="cl-limites">'
        + "".join(
            f'<div class="cl-limite"><div class="cl-limite-tit">{tit}</div>'
            f'<div class="cl-limite-txt">{txt}</div></div>'
            for tit, txt in limites
        )
        + "</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"""
    <div class="brand-footer">
        Farol de Hiring · Artefact People &amp; Talent · Greenhouse (pipe) + Artefactory (demanda)
    </div>
    """,
    unsafe_allow_html=True,
)
