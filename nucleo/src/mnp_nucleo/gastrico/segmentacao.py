"""Divisão automática da ROI gástrica em metades proximal e distal."""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

__all__ = ["Segmentacao", "segmentar_roi"]


@dataclass
class Segmentacao:
    """Resultado da divisão da ROI.

    ``linha`` é o segmento divisório (perpendicular ao eixo principal, pelo
    ponto de corte), recortado ao retângulo que contém a ROI, em coordenadas de
    pixel contínuas (centro do pixel c em c + 0,5).
    """

    proximal: np.ndarray
    distal: np.ndarray
    eixo: tuple[float, float]
    centroide: tuple[float, float]
    ponto_corte: tuple[float, float]
    linha: tuple[tuple[float, float], tuple[float, float]]
    centroide_proximal: tuple[float, float]
    centroide_distal: tuple[float, float]


def _recortar_reta(px, py, nx, ny, x0, y0, x1, y1):
    """Interseção da reta p + t·n com o retângulo [x0, x1] × [y0, y1]."""
    ts = []
    if abs(nx) > 1e-12:
        ts += [(x0 - px) / nx, (x1 - px) / nx]
    if abs(ny) > 1e-12:
        ts += [(y0 - py) / ny, (y1 - py) / ny]
    pontos = []
    for t in ts:
        x, y = px + t * nx, py + t * ny
        if x0 - 1e-9 <= x <= x1 + 1e-9 and y0 - 1e-9 <= y <= y1 + 1e-9:
            pontos.append((t, (min(max(x, x0), x1), min(max(y, y0), y1))))
    if len(pontos) < 2:
        return (px, py), (px, py)
    pontos.sort()
    return pontos[0][1], pontos[-1][1]


def segmentar_roi(mascara: np.ndarray) -> Segmentacao:
    """Divide a ROI em metade proximal e distal ao longo do eixo principal.

    Método (análise de componentes principais dos pixels da ROI):

    1. centros dos pixels pᵢ = (c + 0,5; l + 0,5) e centroide μ;
    2. covariância 2×2: Sxx, Syy, Sxy (divisor n);
    3. eixo principal = autovetor do maior autovalor, de ângulo
       θ = ½ · atan2(2·Sxy, Sxx − Syy), u = (cos θ, sen θ);
    4. projeção sᵢ = (pᵢ − μ) · u e corte na mediana m de s;
    5. metade A = {sᵢ < m}, metade B = {sᵢ ≥ m} (mesmo número de pixels,
       a menos de empates na mediana);
    6. proximal = metade cujo centroide está mais alto na imagem (menor y).

    É uma operacionalização da divisão do eixo longo do estômago em metades
    usada para a distribuição intragástrica da refeição (IMD). Diferença
    importante: aqui as metades têm o mesmo número de pixels, enquanto
    Orthey et al. dividem o comprimento do eixo longo ao meio. Os valores
    podem diferir, e os pontos de corte de IMD da literatura não se aplicam
    sem validação própria.

    Referências: Orthey P et al. J Nucl Med. 2018;59:691-7.
    doi:10.2967/jnumed.117.197053 · Orthey P et al. J Nucl Med Technol.
    2019;47:138-43. doi:10.2967/jnmt.118.215566
    """
    mascara = np.asarray(mascara, dtype=bool)
    linhas, colunas = mascara.shape
    ls, cs = np.nonzero(mascara)
    n = ls.size
    if n < 2:
        raise ValueError("ROI vazia ou pequena demais para segmentação.")
    xs = cs.astype(np.float64) + 0.5
    ys = ls.astype(np.float64) + 0.5
    cx, cy = float(xs.mean()), float(ys.mean())
    dx, dy = xs - cx, ys - cy
    sxx = float((dx * dx).sum() / n)
    sxy = float((dx * dy).sum() / n)
    syy = float((dy * dy).sum() / n)
    angulo = 0.5 * math.atan2(2.0 * sxy, sxx - syy)
    ux, uy = math.cos(angulo), math.sin(angulo)

    projecoes = dx * ux + dy * uy
    mediana = float(np.median(projecoes))
    em_a = projecoes < mediana
    em_b = ~em_a

    ca = (float(xs[em_a].mean()), float(ys[em_a].mean())) if em_a.any() else (cx, cy)
    cb = (float(xs[em_b].mean()), float(ys[em_b].mean()))
    a_proximal = ca[1] <= cb[1]
    sel_prox, sel_dist = (em_a, em_b) if a_proximal else (em_b, em_a)

    proximal = np.zeros_like(mascara)
    distal = np.zeros_like(mascara)
    proximal[ls[sel_prox], cs[sel_prox]] = True
    distal[ls[sel_dist], cs[sel_dist]] = True

    corte = (cx + ux * mediana, cy + uy * mediana)
    # segmento divisório limitado ao retângulo que contém a ROI
    linha = _recortar_reta(
        corte[0], corte[1], -uy, ux, float(cs.min()), float(ls.min()), float(cs.max() + 1), float(ls.max() + 1)
    )
    return Segmentacao(
        proximal=proximal,
        distal=distal,
        eixo=(ux, uy),
        centroide=(cx, cy),
        ponto_corte=corte,
        linha=linha,
        centroide_proximal=ca if a_proximal else cb,
        centroide_distal=cb if a_proximal else ca,
    )
