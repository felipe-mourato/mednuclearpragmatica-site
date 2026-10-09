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
    "eixo_automatico",
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


# ---------------------------------------------------------------------------
# Eixo longitudinal automático
# ---------------------------------------------------------------------------

_VIZINHOS = (
    (-1, -1, math.sqrt(2.0)), (-1, 0, 1.0), (-1, 1, math.sqrt(2.0)),
    (0, -1, 1.0), (0, 1, 1.0),
    (1, -1, math.sqrt(2.0)), (1, 0, 1.0), (1, 1, math.sqrt(2.0)),
)


def _distancia_a_borda(mascara: np.ndarray) -> np.ndarray:
    """Distância euclidiana (pixels) de cada pixel da ROI até a borda da ROI.

    Borda = pixels da ROI com algum vizinho (4-conectado) fora dela. A
    distância é medida entre centros de pixel, mais 0,5 (a borda vale 0,5).
    """
    m = np.pad(mascara, 1)
    interior = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
    borda = mascara & ~interior
    bl, bc = np.nonzero(borda)
    ml, mc = np.nonzero(mascara)
    dist = np.zeros(mascara.shape)
    if bl.size == 0:
        return dist
    for i in range(0, ml.size, 2048):
        dl = ml[i : i + 2048, None] - bl[None, :]
        dc = mc[i : i + 2048, None] - bc[None, :]
        dist[ml[i : i + 2048], mc[i : i + 2048]] = np.sqrt((dl * dl + dc * dc).min(axis=1)) + 0.5
    return dist


def _dijkstra(mascara: np.ndarray, origem: tuple[int, int], peso: np.ndarray | None = None):
    """Menor caminho dentro da ROI (8-vizinhança) a partir de ``origem`` (linha, coluna).

    Custo de um passo = comprimento do passo (1 ou √2) × peso do pixel de
    chegada (1 se ``peso`` for None). Devolve (custo, predecessor).
    """
    import heapq

    linhas, colunas = mascara.shape
    custo = np.full(mascara.shape, np.inf)
    pred = np.full(mascara.shape + (2,), -1, dtype=np.int64)
    custo[origem] = 0.0
    fila = [(0.0, origem[0], origem[1])]
    while fila:
        c, l, k = heapq.heappop(fila)
        if c > custo[l, k]:
            continue
        for dl, dk, passo in _VIZINHOS:
            nl, nk = l + dl, k + dk
            if 0 <= nl < linhas and 0 <= nk < colunas and mascara[nl, nk]:
                nc = c + passo * (1.0 if peso is None else peso[nl, nk])
                if nc < custo[nl, nk]:
                    custo[nl, nk] = nc
                    pred[nl, nk] = (l, k)
                    heapq.heappush(fila, (nc, nl, nk))
    return custo, pred


def _mais_distante(custo: np.ndarray) -> tuple[int, int]:
    finito = np.where(np.isfinite(custo), custo, -1.0)
    l, k = np.unravel_index(int(np.argmax(finito)), custo.shape)
    return int(l), int(k)


def _suavizar(pontos: list[Ponto], janela: int = 5) -> list[Ponto]:
    """Média móvel dos pontos internos; as extremidades ficam fixas."""
    n = len(pontos)
    if n <= 2:
        return list(pontos)
    meia = janela // 2
    saida = [pontos[0]]
    for i in range(1, n - 1):
        r = min(meia, i, n - 1 - i)
        trecho = pontos[i - r : i + r + 1]
        saida.append((sum(p[0] for p in trecho) / len(trecho), sum(p[1] for p in trecho) / len(trecho)))
    saida.append(pontos[-1])
    return saida


def eixo_automatico(mascara: np.ndarray) -> list[Ponto]:
    """Eixo longitudinal traçado automaticamente pela linha média da ROI.

    1. Extremidades: os dois pixels da ROI mais distantes entre si medindo
       por dentro da ROI (diâmetro geodésico, obtido por duas buscas de
       menor caminho). Num estômago, são o topo do fundo e a extremidade
       distal.
    2. Linha média: menor caminho entre as extremidades com custo por passo
       proporcional a 1 / d², em que d é a distância do pixel até a borda da
       ROI. O caminho foge das bordas e segue o meio do estômago.
    3. Suavização (média móvel de 5 pontos) e orientação: o eixo começa na
       extremidade mais alta da imagem (topo do fundo).

    Substitui o traçado manual do artigo (Silver 2022) por uma regra
    determinística, sem parâmetros de contagem: o resultado depende só do
    contorno da ROI. Desenhe a ROI acompanhando o estômago.
    """
    mascara = np.asarray(mascara, dtype=bool)
    ls, cs = np.nonzero(mascara)
    if ls.size < 3:
        raise ValueError("ROI pequena demais para traçar o eixo.")
    # componente principal: parte do pixel mais próximo do centroide
    cl, cc = ls.mean(), cs.mean()
    i0 = int(np.argmin((ls - cl) ** 2 + (cs - cc) ** 2))
    custo, _ = _dijkstra(mascara, (int(ls[i0]), int(cs[i0])))
    a = _mais_distante(custo)
    custo, _ = _dijkstra(mascara, a)
    b = _mais_distante(custo)
    d = _distancia_a_borda(mascara)
    peso = np.where(mascara, 1.0 / np.maximum(d, 0.5) ** 2, np.inf)
    _, pred = _dijkstra(mascara, a, peso)
    caminho = [b]
    while caminho[-1] != a:
        l, k = pred[caminho[-1]]
        if l < 0:
            break
        caminho.append((int(l), int(k)))
    caminho.reverse()
    pontos = [(k + 0.5, l + 0.5) for l, k in caminho]
    raios = [float(d[l, k]) for l, k in caminho]
    if len(pontos) < 2 or comprimento_trajeto(pontos) < 2.0:
        raise ValueError("ROI pequena demais para traçar o eixo.")
    pontos = _ajustar_extremidades(_suavizar(pontos, 5), raios, mascara)
    eixo = simplificar_trajeto(pontos, 1.0)
    if eixo[-1] != pontos[-1]:
        eixo.append(pontos[-1])
    return orientar_eixo(eixo)


def _acumulado(pontos: list[Ponto]) -> list[float]:
    s = [0.0]
    for a, b in zip(pontos, pontos[1:]):
        s.append(s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
    return s


def _prolongar(ponto: Ponto, direcao: tuple[float, float], mascara: np.ndarray) -> Ponto:
    """Anda de ``ponto`` na ``direcao`` (unitária) até sair da ROI; devolve o último ponto dentro."""
    linhas, colunas = mascara.shape
    x, y = ponto
    passo = 0.25
    for _ in range(4 * (linhas + colunas)):
        nx, ny = x + direcao[0] * passo, y + direcao[1] * passo
        l, k = int(math.floor(ny)), int(math.floor(nx))
        if not (0 <= l < linhas and 0 <= k < colunas) or not mascara[l, k]:
            break
        x, y = nx, ny
    return (x, y)


def _ajustar_extremidades(pontos: list[Ponto], raios: list[float], mascara: np.ndarray) -> list[Ponto]:
    """Corrige as pontas do eixo, que o menor caminho leva para os cantos da ROI.

    Em cada ponta: R = maior distância à borda nos primeiros 25% do eixo
    (meia largura do estômago naquela região). Apara-se o trecho de
    comprimento R junto à ponta e prolonga-se o eixo em linha reta, na
    direção do trecho seguinte (de R a 2R), até a borda da ROI. Assim o
    eixo começa no meio do topo do fundo e termina no meio da extremidade
    distal.
    """
    if len(pontos) < 4:
        return pontos

    def uma_ponta(pts: list[Ponto], rs: list[float]) -> list[Ponto]:
        s = _acumulado(pts)
        total = s[-1]
        r = max([rv for sv, rv in zip(s, rs) if sv <= 0.25 * total] or [rs[0]])
        r = min(r, 0.25 * total)
        i = next((j for j, sv in enumerate(s) if sv >= r), 0)
        k = next((j for j, sv in enumerate(s) if sv >= s[i] + r), len(pts) - 1)
        if k <= i:
            return pts
        dx, dy = pts[i][0] - pts[k][0], pts[i][1] - pts[k][1]
        n = math.hypot(dx, dy)
        if n == 0:
            return pts
        ponta = _prolongar(pts[i], (dx / n, dy / n), mascara)
        return [ponta] + pts[i:]

    pontos = uma_ponta(pontos, raios)
    raios_inv = raios[::-1]
    # após aparar o início, os raios do fim continuam alinhados pelo fim do caminho
    fim = uma_ponta(pontos[::-1], raios_inv[: len(pontos)])
    return fim[::-1]
