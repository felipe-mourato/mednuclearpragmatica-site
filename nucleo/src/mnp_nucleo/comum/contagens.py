"""Contagens em ROI, média geométrica e correção de decaimento físico."""

from __future__ import annotations

import math

import numpy as np

__all__ = [
    "MEIA_VIDA_TC99M_H",
    "soma_contagens",
    "media_geometrica",
    "fator_decaimento",
]

#: Meia-vida física do ⁹⁹ᵐTc em horas: 6,0067 h.
#: Fonte: NNDC/ENSDF (National Nuclear Data Center), avaliação do ⁹⁹ᵐTc.
MEIA_VIDA_TC99M_H = 6.0067


def soma_contagens(valores: np.ndarray, mascara: np.ndarray) -> float:
    """Soma dos valores dos pixels dentro da máscara.

    C(ROI) = Σ v(i), para todo pixel i com máscara(i) verdadeira.

    Os valores são os da imagem com rescale aplicado (ver
    :func:`mnp_nucleo.comum.dicom.ler_dicom`), nunca os da exibição.
    """
    valores = np.asarray(valores, dtype=np.float64)
    mascara = np.asarray(mascara, dtype=bool)
    if valores.shape != mascara.shape:
        raise ValueError("Imagem e máscara com dimensões diferentes.")
    return float(valores[mascara].sum())


def media_geometrica(anterior: float, posterior: float) -> float:
    """Média geométrica das contagens anterior e posterior.

    MG = √(C_ANT × C_POST)

    Reduz o efeito da profundidade da fonte (atenuação) em relação a uma
    projeção única. Referência: Abell TL et al. Consensus recommendations for
    gastric emptying scintigraphy. Am J Gastroenterol. 2008;103:753-63.
    doi:10.1111/j.1572-0241.2007.01636.x

    Contagens negativas (possíveis com intercepto de rescale negativo) não
    têm média geométrica definida e geram ``ValueError``.
    """
    if anterior < 0 or posterior < 0:
        raise ValueError("Contagem negativa: média geométrica indefinida.")
    return math.sqrt(anterior * posterior)


def fator_decaimento(minutos: float, meia_vida_h: float | None) -> float:
    """Fator que corrige o decaimento físico para o instante de referência (T0).

    f(t) = 2^( t / (T½ × 60) ),  t em minutos, T½ em horas.

    Multiplicar a contagem do tempo t por f(t) devolve a contagem que seria
    medida em T0 sem decaimento. Sem meia-vida (``None`` ou ≤ 0), f = 1.
    Referência: Donohoe KJ et al. Procedure guideline for adult solid-meal
    gastric-emptying study 3.0. J Nucl Med Technol. 2009;37:196-200.
    doi:10.2967/jnmt.109.067843
    """
    if meia_vida_h is None or meia_vida_h <= 0:
        return 1.0
    return 2.0 ** (minutos / (meia_vida_h * 60.0))
