"""
Autenticação (Google OAuth, via st.login nativo do Streamlit) + Autorização
(allowlist de e-mails) do Farol de Hiring.

Authentication != Authorization:
- Authentication ("quem é você?") é resolvida pelo Google. O Streamlit cuida
  do fluxo OIDC completo (redirect, callback, cookie de sessão) via st.login()
  e expõe a identidade em st.user.
- Authorization ("você pode acessar este dashboard?") é resolvida aqui, no
  servidor, consultando authorized_users.csv — hoje um mock local, com a
  mesma estrutura de colunas de uma futura tabela BigQuery `authorized_users`
  mantida pelo Data Eng. Ter conta Google válida NÃO dá acesso automático.

Enforcement é sempre no backend: como o Streamlit reexecuta o script inteiro
no servidor a cada sessão/interação, um st.stop() aqui impede que o HTML e os
dados do dashboard sequer sejam montados e enviados ao navegador. Não existe
um "if (authorized) showDashboard()" no cliente — o cliente nunca recebe o
dashboard se a autorização falhar.
"""

from pathlib import Path

import pandas as pd
import streamlit as st

BASE_DIR = Path(__file__).resolve().parent
AUTHORIZED_USERS_PATH = BASE_DIR / "authorized_users.csv"


def normalize_email(email: str | None) -> str:
    """Normaliza para comparação: remove espaços nas pontas e força lowercase.
    'User@Company.com' e 'user@company.com ' devem ser equivalentes."""
    return (email or "").strip().lower()


def _auth_configured() -> bool:
    """Verdadeiro só quando .streamlit/secrets.toml existe e tem a seção
    [auth] preenchida (client_id/client_secret reais do Google Cloud). Sem
    isso, st.login() nem pode funcionar — então caímos em 'modo aberto' com
    aviso bem visível, em vez de quebrar o app (essencial para rodar local/
    dev e para os testes automatizados, que não têm credenciais reais)."""
    try:
        return bool(st.secrets.get("auth", {}).get("client_id"))
    except Exception:
        return False


@st.cache_data(ttl=60)
def _load_authorized_users() -> pd.DataFrame:
    if not AUTHORIZED_USERS_PATH.exists():
        return pd.DataFrame(columns=["email", "name", "active", "role", "created_at", "updated_at"])
    df = pd.read_csv(AUTHORIZED_USERS_PATH, dtype=str)
    df["email"] = df["email"].map(normalize_email)
    df["active"] = df["active"].astype(str).str.strip().str.lower().isin(["true", "1", "yes"])
    return df


def check_authorization(email: str):
    """(autorizado: bool, role: str|None). Regra: e-mail presente na
    allowlist (case-insensitive) E active == true. Nome não é usado para
    autorizar — só o e-mail."""
    users = _load_authorized_users()
    match = users[users["email"] == normalize_email(email)]
    if match.empty:
        return False, None
    row = match.iloc[0]
    if not bool(row["active"]):
        return False, None
    role = row.get("role")
    return True, (role if pd.notna(role) and role else None)


def _auth_shell(pal: dict, gradient_css: str, logo_html: str, body_html: str) -> None:
    st.markdown(
        f"""
        <div style="max-width:440px;margin:8vh auto 0;">
            <div style="background:{gradient_css};border-radius:18px;padding:32px 28px;
                        text-align:center;box-shadow:0 10px 28px rgba(0,34,68,.25);margin-bottom:20px;">
                {logo_html}
                <div style="color:#fff;font-weight:900;font-size:22px;margin-top:10px;">Farol de Hiring</div>
                <div style="color:rgba(255,255,255,.7);font-size:11px;letter-spacing:.06em;
                            text-transform:uppercase;margin-top:4px;">
                    Artefact · People &amp; Talent
                </div>
            </div>
            {body_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_login_screen(pal: dict, gradient_css: str, logo_html: str) -> None:
    body = f"""
        <p style="color:{pal['muted']};font-size:13.5px;line-height:1.7;text-align:center;margin-bottom:4px;">
            Leitura do ritmo de contratação por chapter e senioridade — acesso restrito ao time de
            People &amp; Talent da Artefact. Faça login com sua conta Google corporativa.
        </p>
    """
    _auth_shell(pal, gradient_css, logo_html, body)
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.button(
            "Continue with Google",
            key="login_google",
            use_container_width=True,
            on_click=st.login,
        )
        st.caption("Você será redirecionado para o login do Google e voltará automaticamente para cá.")


def render_access_denied(pal: dict, gradient_css: str, logo_html: str, email: str) -> None:
    body = f"""
        <div style="background:{pal['surface']};border:1px solid {pal['line']};border-radius:14px;
                    padding:20px 22px;">
            <div style="font-weight:700;color:{pal['ink']};font-size:15px;margin-bottom:8px;">
                🚫 Acesso não autorizado
            </div>
            <p style="color:{pal['muted']};font-size:13px;line-height:1.7;margin:0;">
                A conta <b style="color:{pal['ink']}">{email}</b> foi autenticada com sucesso pelo Google,
                mas não está na lista de usuários autorizados do Farol de Hiring.<br><br>
                Se você acredita que deveria ter acesso, peça ao time de People &amp; Talent para adicionar
                seu e-mail corporativo à allowlist (<code>authorized_users</code>).
            </p>
        </div>
    """
    _auth_shell(pal, gradient_css, logo_html, body)
    _, col_mid, _ = st.columns([1, 2, 1])
    with col_mid:
        st.button(
            "Sair e tentar com outra conta",
            key="logout_denied",
            use_container_width=True,
            on_click=st.logout,
        )


def require_login_and_authorization(pal: dict, gradient_css: str, logo_html: str) -> dict:
    """Gate principal — chame logo após o CSS ser injetado e antes de
    renderizar qualquer conteúdo do dashboard. Interrompe o script (st.stop)
    se o usuário não estiver autenticado ou não estiver na allowlist; só
    retorna quando os dois passam."""
    if not _auth_configured():
        st.warning(
            "🔓 Autenticação Google não configurada neste ambiente "
            "(.streamlit/secrets.toml ausente ou sem `[auth]`) — rodando em modo aberto, "
            "sem checagem de login. Configure antes de usar com dados reais (ver README).",
            icon="⚠️",
        )
        return {"email": "dev@local (modo aberto)", "name": "Modo dev — sem autenticação", "role": None}

    if not st.user.is_logged_in:
        render_login_screen(pal, gradient_css, logo_html)
        st.stop()

    with st.spinner("Verificando autorização..."):
        authorized, role = check_authorization(st.user.email)

    if not authorized:
        render_access_denied(pal, gradient_css, logo_html, st.user.email)
        st.stop()

    return {"email": normalize_email(st.user.email), "name": st.user.name, "role": role}
