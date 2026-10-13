"""Figuras do laudo: quadros de mesmo tamanho com as ROIs renais e o fundo desenhados.

Só exibição: usam a janela e a escala de cinza escolhidas, sem tocar nos
valores usados nos cálculos.
"""

from __future__ import annotations

import math
from typing import Sequence

import numpy as np

from ..comum import exibicao
from ..comum.morfologia import contorno
from ..comum.png import codificar_png
from ..comum.roi import mascara_roi

__all__ = ["COR_RIM", "COR_HALO", "TAMANHO_QUADRO", "fator_ampliacao", "quadro_rgba", "quadro_png"]

#: Cores fixas dos rins (âmbar = direito, verde-azulado = esquerdo), distinguíveis com daltonismo.
COR_RIM = {"D": (240, 160, 40), "E": (40, 190, 190)}
COR_HALO = (8, 16, 25)
TAMANHO_QUADRO = 384
OPACIDADE_FUNDO = 0.38


def fator_ampliacao(linhas: int, colunas: int, alvo: int = TAMANHO_QUADRO) -> int:
    """Fator inteiro de ampliação (vizinho mais próximo) para o lado maior chegar perto de ``alvo``."""
    return max(1, math.ceil(alvo / max(linhas, colunas)))


def _pintar(rgb: np.ndarray, mascara: np.ndarray, cor, opacidade: float = 1.0) -> None:
    if not mascara.any():
        return
    rgb[mascara] = rgb[mascara] * (1.0 - opacidade) + np.asarray(cor, dtype=np.float64) * opacidade


def quadro_rgba(
    valores: np.ndarray,
    nivel: float,
    largura: float,
    invertido: bool = False,
    rois: Sequence[tuple[str, Sequence]] = (),
    fundos: Sequence[tuple[str, np.ndarray]] = (),
) -> np.ndarray:
    """Quadro quadrado, ampliado, com contornos das ROIs e fundo translúcido.

    ``rois``: (rim, polígono em coordenadas da imagem); ``fundos``: (rim,
    máscara na grade da imagem). A imagem é centralizada num quadrado de
    lado = máx(linhas, colunas) × fator, completado com a cor do valor
    mínimo da janela.
    """
    linhas, colunas = valores.shape
    f = fator_ampliacao(linhas, colunas)
    cinza = exibicao.aplicar_janela(valores, nivel, largura).astype(np.float64)
    if invertido:
        cinza = 255.0 - cinza
    grande = np.kron(cinza, np.ones((f, f)))
    rgb = np.repeat(grande[:, :, np.newaxis], 3, axis=2)
    for rim, m in fundos:
        _pintar(rgb, np.kron(np.asarray(m, dtype=bool), np.ones((f, f), dtype=bool)), COR_RIM[rim], OPACIDADE_FUNDO)
    espessura = max(2, f // 2 + 1)
    for rim, poligono in rois:
        if not poligono or len(poligono) < 3:
            continue
        ampliado = [(x * f, y * f) for x, y in poligono]
        m = mascara_roi(ampliado, linhas * f, colunas * f)
        _pintar(rgb, contorno(m, espessura + 1), COR_HALO)
        _pintar(rgb, contorno(m, espessura), COR_RIM[rim])
    lado = max(linhas, colunas) * f
    preenchimento = 255.0 if invertido else 0.0
    saida = np.full((lado, lado, 3), preenchimento)
    y0, x0 = (lado - linhas * f) // 2, (lado - colunas * f) // 2
    saida[y0 : y0 + linhas * f, x0 : x0 + colunas * f] = rgb
    rgba = np.empty((lado, lado, 4), dtype=np.uint8)
    rgba[:, :, :3] = np.rint(np.clip(saida, 0, 255)).astype(np.uint8)
    rgba[:, :, 3] = 255
    return rgba


def quadro_png(*args, **kwargs) -> bytes:
    """O mesmo de :func:`quadro_rgba`, codificado em PNG."""
    return codificar_png(quadro_rgba(*args, **kwargs))
