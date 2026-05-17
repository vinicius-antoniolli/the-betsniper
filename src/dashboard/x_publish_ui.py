from __future__ import annotations

import hmac

import streamlit as st

from config import settings


X_PUBLISH_UNLOCKED_KEY = "x_publish_unlocked"
X_PUBLISH_UNLOCK_REQUESTED_KEY = "x_publish_unlock_requested"
X_PUBLISH_PASSWORD_INPUT_KEY = "x_publish_password_input"


def is_x_publish_unlocked() -> bool:
    return bool(st.session_state.get(X_PUBLISH_UNLOCKED_KEY))


def ensure_x_publish_unlocked() -> bool:
    if is_x_publish_unlocked():
        return True
    st.error("Publicacao no X bloqueada. Libere com a senha antes de publicar.")
    return False


def render_x_publish_unlock_control() -> None:
    if is_x_publish_unlocked():
        return

    with st.container(key="x_publish_unlock_slot"):
        if st.button("Login", key="x_publish_unlock_button"):
            st.session_state[X_PUBLISH_UNLOCK_REQUESTED_KEY] = True

    if not st.session_state.get(X_PUBLISH_UNLOCK_REQUESTED_KEY):
        return

    with st.form("x_publish_unlock_form", clear_on_submit=False):
        password = st.text_input(
            "Senha para liberar publicacao no X",
            type="password",
            key=X_PUBLISH_PASSWORD_INPUT_KEY,
        )
        submitted = st.form_submit_button("Liberar X")

    if not submitted:
        return

    configured_password = settings.x_publish_password or ""
    if not configured_password:
        st.error("Configure X_PUBLISH_PASSWORD no .env para liberar publicacao no X.")
        return
    if hmac.compare_digest(password or "", configured_password):
        st.session_state[X_PUBLISH_UNLOCKED_KEY] = True
        st.session_state[X_PUBLISH_UNLOCK_REQUESTED_KEY] = False
        st.rerun()
        return

    st.error("Senha incorreta.")


def render_x_publish_auth_css() -> None:
    toolbar_display = "flex" if is_x_publish_unlocked() else "none"
    st.markdown(
        f"""
        <style>
        [data-testid="stToolbar"] {{
          display: {toolbar_display} !important;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )
