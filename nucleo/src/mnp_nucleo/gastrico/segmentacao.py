"""Divisão da ROI gástrica em metades proximal e distal pelo eixo longitudinal.

Método de Silver et al. (2022), que segue Orthey et al. (2018):

1. a ROI do estômago inteiro é desenhada (contagens totais);
2. o eixo longitudinal é traçado à mão pela linha média do estômago, do topo
   do fundo (imagem de T0) até o estômago distal (imagens de 2 a 4 h);
3. o comprimento desse eixo é dividido ao meio e um corte perpendicular ao
   eixo, nesse ponto, separa o estômago proximal do distal;
4. contagens proximais vêm da metade proximal; contagens distais são o
   total menos o proximal.

No artigo, a ROI proximal é desenhada à mão a partir do corte. Aqui ela é
obtida automaticamente: cada pixel da ROI vai para a metade do ponto do eixo
mais próximo dele (projeção sobre o eixo). Perto do meio do eixo, a
fronteira é exatamente o corte perpendicular; longe dele, a regra impede
que a reta perpendicular atravesse outra parte do estômago (estômago em J).

Referências: Silver PJ, Dadparvar S, Maurer AH, Parkman HP. Proximal and
distal intragastric meal distribution during gastric emptying scintigraphy:
relationships to symptoms of gastroparesis. Neurogastroenterol Motil.
2022;34:e14436. doi:10.1111/nmo.14436 · Orthey P et al. J Nucl Med.
2018;59:691-7. doi:10.2967/jnumed.117.197053
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np

from ..comum.roi import Ponto, simplificar_trajeto

__all__ = [
    "Segmentacao",
    "orientar_eixo",
    "preparar_eixo",
    "comprimento_trajeto",
    "ponto_na_fracao",
    "projetar_no_eixo",
    "segmentar_por_eixo",
]


@dataclass
class Segmentacao:
    """Resultado da divisão.

    ``corte`` é o segmento do corte perpendicular no meio do eixo, limitado à
    fronteira entre as metades, para desenhar. Coordenadas contínuas de
    pixel (centro do pixel c em c + 0,5).
    """

    proximal: np.ndarray
    distal: np.ndarray
    eixo: list[Ponto]
    comprimento: float
    meio: Ponto
    tangente: tuple[float, float]
    corte: tuple[Ponto, Ponto]


def comprimento_trajeto(eixo: Sequence[Ponto]) -> float:
    """Comprimento da linha poligonal: L = Σ |pᵢ₊₁ − pᵢ|."""
    return float(sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(eixo, eixo[1:])))


def orientar_eixo(eixo: Sequence[Ponto]) -> list[Ponto]:
    """Garante que o eixo comece no topo do fundo.

    O início do eixo é a extremidade mais alta na imagem (menor y). Se o
    traço foi feito do distal para o fundo, ele é invertido.
    """
    eixo = list(eixo)
    if len(eixo) >= 2 and eixo[-1][1] < eixo[0][1]:
        eixo.reverse()
    return eixo


def preparar_eixo(pontos: Sequence[Ponto], distancia_minima: float = 1.5) -> list[Ponto]:
    """Simplifica o traço à mão livre e orienta do fundo para o distal."""
    eixo = simplificar_trajeto(list(pontos), distancia_minima)
    # simplificar_trajeto descarta o último ponto se ele encosta no primeiro
    # (pensado para polígonos); num eixo aberto, o fim do traço importa.
    if pontos and (not eixo or eixo[-1] != tuple(pontos[-1])) and len(pontos) >= 2:
        u = pontos[-1]
        if not eixo or math.hypot(u[0] - eixo[-1][0], u[1] - eixo[-1][1]) > 1e-9:
            eixo.append((float(u[0]), float(u[1])))
    return orientar_eixo(eixo)


def ponto_na_fracao(eixo: Sequence[Ponto], fracao: float = 0.5) -> tuple[Ponto, tuple[float, float]]:
    """Ponto a ``fracao`` do comprimento do eixo e a direção (unitária) do eixo ali.

    Para fracao = 0,5: o ponto M em que o comprimento percorrido desde o
    início é L/2.
    """
    total = comprimento_trajeto(eixo)
    alvo = total * fracao
    percorrido = 0.0
    for a, b in zip(eixo, eixo[1:]):
        seg = math.hypot(b[0] - a[0], b[1] - a[1])
        if seg == 0:
            continue
        if percorrido + seg >= alvo:
            t = (alvo - percorrido) / seg
            return (a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])), ((b[0] - a[0]) / seg, (b[1] - a[1]) / seg)
        percorrido += seg
    a, b = eixo[-2], eixo[-1]
    seg = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
    return (b[0], b[1]), ((b[0] - a[0]) / seg, (b[1] - a[1]) / seg)


def projetar_no_eixo(xs: np.ndarray, ys: np.ndarray, eixo: Sequence[Ponto]) -> np.ndarray:
    """Posição ao longo do eixo (comprimento percorrido) do ponto do eixo mais próximo de cada (x, y).

    Para cada segmento [a, b]: t = clamp(((p − a)·(b − a)) / |b − a|², 0, 1);
    distância² = |p − (a + t(b − a))|²; posição = comprimento até a + t·|b − a|.
    Fica a posição do segmento com menor distância (em empate, o primeiro).
    """
    melhor_d = np.full(xs.shape, np.inf)
    melhor_s = np.zeros(xs.shape)
    acumulado = 0.0
    for a, b in zip(eixo, eixo[1:]):
        vx, vy = b[0] - a[0], b[1] - a[1]
        seg2 = vx * vx + vy * vy
        if seg2 == 0:
            continue
        t = np.clip(((xs - a[0]) * vx + (ys - a[1]) * vy) / seg2, 0.0, 1.0)
        d = (xs - (a[0] + t * vx)) ** 2 + (ys - (a[1] + t * vy)) ** 2
        melhor = d < melhor_d
        melhor_d = np.where(melhor, d, melhor_d)
        melhor_s = np.where(melhor, acumulado + t * math.sqrt(seg2), melhor_s)
        acumulado += math.sqrt(seg2)
    return melhor_s


def segmentar_por_eixo(mascara: np.ndarray, eixo: Sequence[Ponto]) -> Segmentacao:
    """Divide a ROI em proximal e distal pelo corte perpendicular no meio do eixo.

    Proximal = pixels da ROI cujo ponto mais próximo do eixo está na primeira
    metade do comprimento (posição < L/2); distal = o restante. Assim
    proximal ∪ distal = ROI e proximal ∩ distal = ∅.
    """
    mascara = np.asarray(mascara, dtype=bool)
    eixo = [(float(x), float(y)) for x, y in eixo]
    if len(eixo) < 2:
        raise ValueError("Eixo longitudinal com menos de dois pontos.")
    comprimento = comprimento_trajeto(eixo)
    if comprimento < 2.0:
        raise ValueError("Eixo longitudinal curto demais.")
    ls, cs = np.nonzero(mascara)
    if ls.size < 2:
        raise ValueError("ROI vazia ou pequena demais para a divisão.")
    xs, ys = cs + 0.5, ls + 0.5
    posicao = projetar_no_eixo(xs, ys, eixo)
    prox = posicao < comprimento / 2.0
    proximal = np.zeros_like(mascara)
    distal = np.zeros_like(mascara)
    proximal[ls[prox], cs[prox]] = True
    distal[ls[~prox], cs[~prox]] = True

    meio, (tx, ty) = ponto_na_fracao(eixo, 0.5)
    nx, ny = -ty, tx
    # Corte para desenhar: pixels proximais vizinhos de distais, junto à
    # perpendicular que passa pelo meio do eixo.
    fronteira = proximal & (
        np.roll(distal, 1, 0) | np.roll(distal, -1, 0) | np.roll(distal, 1, 1) | np.roll(distal, -1, 1)
    )
    fl, fc = np.nonzero(fronteira)
    perto = np.abs((fc + 0.5 - meio[0]) * tx + (fl + 0.5 - meio[1]) * ty) <= 1.5
    if perto.any():
        s = (fc[perto] + 0.5 - meio[0]) * nx + (fl[perto] + 0.5 - meio[1]) * ny
        s0, s1 = float(s.min()) - 0.5, float(s.max()) + 0.5
    else:
        s0 = s1 = 0.0
    corte = ((meio[0] + s0 * nx, meio[1] + s0 * ny), (meio[0] + s1 * nx, meio[1] + s1 * ny))
    return Segmentacao(proximal, distal, eixo, comprimento, meio, (tx, ty), corte)
