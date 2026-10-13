"""Incidências da cintilografia renal estática e a sugestão automática pela descrição da série."""

from __future__ import annotations

import re

__all__ = ["INCIDENCIAS", "ROTULOS", "OBLIQUAS", "IGNORAR", "adivinhar_incidencia", "rotulo"]

#: Ordem de exibição (grade do laudo e seletores).
INCIDENCIAS = ("POST", "ANT", "OPD", "OPE", "OAD", "OAE")
OBLIQUAS = ("OPD", "OPE", "OAD", "OAE")
#: Valor do seletor para um quadro que não entra no exame.
IGNORAR = "IGNORAR"

ROTULOS = {
    "POST": "Posterior",
    "ANT": "Anterior",
    "OPD": "Oblíqua posterior direita",
    "OPE": "Oblíqua posterior esquerda",
    "OAD": "Oblíqua anterior direita",
    "OAE": "Oblíqua anterior esquerda",
    IGNORAR: "Não usar",
}

# Siglas em português e em inglês (estações de trabalho costumam usar as inglesas).
_OBLIQUAS = (
    ("OPD", r"\bOPD\b|\bRPO\b"),
    ("OPE", r"\bOPE\b|\bLPO\b"),
    ("OAD", r"\bOAD\b|\bRAO\b"),
    ("OAE", r"\bOAE\b|\bLAO\b"),
)


def rotulo(incidencia: str) -> str:
    return ROTULOS.get(incidencia, incidencia)


def adivinhar_incidencia(descricao: str | None) -> tuple[str, str | None]:
    """Sugere a incidência pela descrição da série ou da imagem.

    Procura, nesta ordem: as siglas das oblíquas (OPD, OPE, OAD, OAE e as
    inglesas RPO, LPO, RAO, LAO); "OBL" sem lado (vira OPD, com aviso para
    conferir); "POST", "PÓS" ou "POS"; "ANT". Sem pista, ou com as duas
    vistas citadas (ex.: "ANT/POST"), sugere POSTERIOR, a vista obrigatória.

    Devolve ``(incidência, aviso ou None)``. O usuário sempre pode corrigir.
    """
    texto = (descricao or "").upper()
    for sigla, padrao in _OBLIQUAS:
        if re.search(padrao, texto):
            return sigla, None
    if re.search(r"OBL", texto):
        return "OPD", "Oblíqua sem lado na descrição da série: confira se é OPD, OPE, OAD ou OAE."
    tem_post = re.search(r"POST|P[OÓ]S\b|\bPA\b", texto) is not None
    tem_ant = re.search(r"\bANT|\bAP\b", texto) is not None
    if tem_ant and not tem_post:
        return "ANT", None
    return "POST", None
