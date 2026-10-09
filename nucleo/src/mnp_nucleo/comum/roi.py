"""Geometria de ROI: polígonos sobre a grade de pixels.

Convenção de coordenadas (a mesma da interface): x cresce para a direita,
y para baixo, em unidades de pixel. O pixel (coluna c, linha l) ocupa o
quadrado [c, c+1) × [l, l+1) e é testado pelo centro (c+0,5; l+0,5).
Um polígono é uma lista de pontos ``(x, y)``; o fechamento é implícito.
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

__all__ = [
    "Ponto",
    "normalizar",
    "ponto_no_poligono",
    "mascara_roi",
    "area_poligono",
    "espelhar_horizontal",
    "transladar",
    "limitar_translacao",
    "ponto_perto_do_poligono",
    "simplificar_trajeto",
]

Ponto = tuple[float, float]


def normalizar(pontos: Iterable) -> list[Ponto]:
    """Converte pontos vindos da interface (listas, tuplas ou dicts x/y) em tuplas float."""
    saida: list[Ponto] = []
    for p in pontos:
        if isinstance(p, dict):
            x, y = p["x"], p["y"]
        else:
            x, y = p[0], p[1]
        x, y = float(x), float(y)
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError("Ponto de ROI com coordenada inválida.")
        saida.append((x, y))
    return saida


def ponto_no_poligono(x: float, y: float, poligono: Sequence[Ponto]) -> bool:
    """Teste de ponto no polígono por lançamento de raio (regra par-ímpar).

    Testa o ponto exato ``(x, y)``. Para o pixel inteiro (c, l), use
    ``ponto_no_poligono(c + 0.5, l + 0.5, poligono)``.

    Referência: Shimrat M. Algorithm 112: Position of point relative to
    polygon. Commun ACM. 1962;5(8):434.
    """
    dentro = False
    n = len(poligono)
    j = n - 1
    for i in range(n):
        xi, yi = poligono[i]
        xj, yj = poligono[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            dentro = not dentro
        j = i
    return dentro


def mascara_roi(poligono: Sequence[Ponto], linhas: int, colunas: int) -> np.ndarray:
    """Rasteriza um polígono em máscara booleana (linhas × colunas).

    Um pixel pertence à ROI quando o seu centro (c+0,5; l+0,5) está dentro
    do polígono pela regra par-ímpar (ver :func:`ponto_no_poligono`). A
    implementação é vetorizada, mas o critério é o mesmo pixel a pixel.
    """
    mascara = np.zeros((linhas, colunas), dtype=bool)
    if len(poligono) < 3:
        return mascara
    p = np.asarray(poligono, dtype=np.float64)
    x0 = max(0, int(math.floor(p[:, 0].min())))
    x1 = min(colunas - 1, int(math.ceil(p[:, 0].max())))
    y0 = max(0, int(math.floor(p[:, 1].min())))
    y1 = min(linhas - 1, int(math.ceil(p[:, 1].max())))
    if x1 < x0 or y1 < y0:
        return mascara
    cy, cx = np.mgrid[y0 : y1 + 1, x0 : x1 + 1]
    cx = cx + 0.5
    cy = cy + 0.5
    dentro = np.zeros(cx.shape, dtype=bool)
    xs, ys = p[:, 0], p[:, 1]
    xs_ant, ys_ant = np.roll(xs, 1), np.roll(ys, 1)
    for xi, yi, xj, yj in zip(xs, ys, xs_ant, ys_ant):
        if yi == yj:
            continue  # aresta horizontal nunca cruza (a condição (yi>y)!=(yj>y) é falsa)
        cruza = (yi > cy) != (yj > cy)
        x_cruz = (xj - xi) * (cy - yi) / (yj - yi) + xi
        dentro ^= cruza & (cx < x_cruz)
    mascara[y0 : y1 + 1, x0 : x1 + 1] = dentro
    return mascara


def area_poligono(poligono: Sequence[Ponto]) -> float:
    """Área geométrica do polígono (fórmula do laço de Gauss), em pixels²."""
    n = len(poligono)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x1, y1 = poligono[i]
        x2, y2 = poligono[(i + 1) % n]
        s += x1 * y2 - x2 * y1
    return abs(s) / 2.0


def espelhar_horizontal(poligono: Sequence[Ponto], largura: int) -> list[Ponto]:
    """Espelha a ROI no eixo vertical para aplicá-la à projeção posterior.

    Na posterior o paciente é visto de costas: esquerda e direita trocam,
    superior e inferior não. Com x contínuo em [0, largura], a reflexão que
    leva o pixel c ao pixel (largura − 1 − c) é::

        x' = largura − x,   y' = y

    Assim a máscara espelhada é exatamente a imagem especular da original
    (mesmo número de pixels).

    Nota: o app de referência em TypeScript usava x' = largura − 1 − x, que
    desloca a ROI espelhada 1 pixel para a esquerda. A correção está
    registrada no CHANGELOG (0.1.0).
    """
    return [(float(largura) - x, y) for x, y in poligono]


def transladar(poligono: Sequence[Ponto], dx: float, dy: float) -> list[Ponto]:
    """Desloca todos os pontos por (dx, dy)."""
    return [(x + dx, y + dy) for x, y in poligono]


def limitar_translacao(
    poligono: Sequence[Ponto], dx: float, dy: float, largura: int, altura: int
) -> tuple[float, float]:
    """Limita o deslocamento para o polígono não sair da imagem [0, largura] × [0, altura]."""
    if not poligono:
        return 0.0, 0.0
    xs = [p[0] for p in poligono]
    ys = [p[1] for p in poligono]
    dx = min(max(dx, -min(xs)), largura - max(xs))
    dy = min(max(dy, -min(ys)), altura - max(ys))
    return float(dx), float(dy)


def _dist_segmento(p: Ponto, a: Ponto, b: Ponto) -> float:
    abx, aby = b[0] - a[0], b[1] - a[1]
    comp2 = abx * abx + aby * aby
    t = 0.0 if comp2 == 0 else min(1.0, max(0.0, ((p[0] - a[0]) * abx + (p[1] - a[1]) * aby) / comp2))
    return math.hypot(p[0] - (a[0] + t * abx), p[1] - (a[1] + t * aby))


def ponto_perto_do_poligono(p: Ponto, poligono: Sequence[Ponto], tolerancia: float) -> bool:
    """Verdadeiro se o ponto está dentro do polígono ou a até ``tolerancia`` pixels de uma aresta.

    Usado para decidir se o clique pega a ROI (arrastar) ou começa uma nova.
    """
    if len(poligono) < 3:
        return False
    if ponto_no_poligono(p[0], p[1], poligono):
        return True
    n = len(poligono)
    return any(_dist_segmento(p, poligono[i - 1], poligono[i]) <= tolerancia for i in range(n))


def simplificar_trajeto(pontos: Sequence[Ponto], distancia_minima: float = 1.5) -> list[Ponto]:
    """Reduz os pontos do desenho à mão livre.

    Mantém um ponto só quando ele está a pelo menos ``distancia_minima``
    pixels do último ponto mantido; descarta o último se ele ficou colado no
    primeiro (o polígono se fecha sozinho).
    """
    if len(pontos) <= 2:
        return list(pontos)
    saida = [pontos[0]]
    for p in pontos[1:]:
        u = saida[-1]
        if math.hypot(p[0] - u[0], p[1] - u[1]) >= distancia_minima:
            saida.append(p)
    if len(saida) > 1 and math.hypot(saida[-1][0] - saida[0][0], saida[-1][1] - saida[0][1]) < distancia_minima:
        saida.pop()
    return saida
