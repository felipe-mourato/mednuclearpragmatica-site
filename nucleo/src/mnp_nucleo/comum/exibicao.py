"""Exibição: janela (nível/largura), inversão de cinza e sobreposição de máscaras.

IMPORTANTE: estas funções servem só para desenhar a imagem na tela. Nenhuma
delas altera os valores usados nos cálculos (contagens, médias geométricas,
retenção). Há teste que garante isso (tests/test_exibicao.py).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

import numpy as np

__all__ = [
    "Janela",
    "janela_padrao",
    "faixa_valores",
    "aplicar_janela",
    "ajustar_janela_por_arraste",
    "renderizar_rgba",
]


@dataclass(frozen=True)
class Janela:
    nivel: float
    largura: float


def faixa_valores(valores: np.ndarray) -> float:
    """Amplitude (máx − mín) dos valores, no mínimo 1."""
    v = np.asarray(valores, dtype=np.float64)
    if v.size == 0 or not np.isfinite(v).any():
        return 1.0
    return float(max(np.nanmax(v) - np.nanmin(v), 1.0))


def janela_padrao(valores: np.ndarray) -> Janela:
    """Janela inicial cobrindo da contagem mínima à máxima.

    nível = (mín + máx) / 2;  largura = máx − mín (no mínimo 1).
    """
    v = np.asarray(valores, dtype=np.float64)
    if v.size == 0 or not np.isfinite(v).any():
        return Janela(0.5, 1.0)
    mn, mx = float(np.nanmin(v)), float(np.nanmax(v))
    return Janela((mn + mx) / 2.0, max(mx - mn, 1.0))


def aplicar_janela(valores: np.ndarray, nivel: float, largura: float) -> np.ndarray:
    """Mapeia valores para cinza 0–255 com janela radiológica.

    cinza = arredonda( clamp( (v − (nível − largura/2)) / largura, 0, 1 ) × 255 )

    Devolve uma cópia (uint8); a entrada não é modificada.
    """
    w = max(float(largura), 1e-6)
    baixo = float(nivel) - w / 2.0
    t = (np.asarray(valores, dtype=np.float64) - baixo) / w
    return np.rint(np.clip(t, 0.0, 1.0) * 255.0).astype(np.uint8)


def ajustar_janela_por_arraste(
    nivel_inicial: float, largura_inicial: float, dx_px: float, dy_px: float, faixa: float
) -> Janela:
    """Nova janela ao arrastar com o botão do meio.

    Sensibilidade s = faixa / 256 por pixel de tela.
    Vertical muda o nível (brilho): para cima aumenta, nível = nível₀ − dy × s.
    Horizontal muda a largura (contraste): para a direita aumenta,
    largura = máx(1, largura₀ + dx × s).
    """
    s = float(faixa) / 256.0
    return Janela(float(nivel_inicial) - float(dy_px) * s, max(1.0, float(largura_inicial) + float(dx_px) * s))


def renderizar_rgba(
    valores: np.ndarray,
    nivel: float,
    largura: float,
    invertido: bool = False,
    sobreposicoes: Sequence[tuple[np.ndarray, tuple[int, int, int], float]] = (),
) -> bytes:
    """Gera os bytes RGBA (linhas × colunas × 4) para desenhar no canvas.

    ``sobreposicoes``: lista de (máscara, (r, g, b), opacidade 0–1). A cor é
    misturada ao cinza (cinza × (1 − a) + cor × a), sem esconder a imagem.
    """
    cinza = aplicar_janela(valores, nivel, largura)
    if invertido:
        cinza = 255 - cinza
    rgb = np.repeat(cinza[:, :, np.newaxis], 3, axis=2).astype(np.float64)
    for mascara, cor, opacidade in sobreposicoes:
        m = np.asarray(mascara, dtype=bool)
        if not m.any():
            continue
        a = float(opacidade)
        rgb[m] = rgb[m] * (1.0 - a) + np.asarray(cor, dtype=np.float64) * a
    linhas, colunas = cinza.shape
    rgba = np.empty((linhas, colunas, 4), dtype=np.uint8)
    rgba[:, :, :3] = np.rint(rgb).astype(np.uint8)
    rgba[:, :, 3] = 255
    return rgba.tobytes()
