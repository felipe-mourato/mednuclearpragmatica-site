"""Figuras: escalas de cor, faixas de cortes e mapa polar com os segmentos e os escores.

Só exibição: nada aqui altera os valores usados nos cálculos.
"""

from __future__ import annotations

import numpy as np

from ..comum.png import codificar_png
from .polar import geometria_segmentos, segmento_em

__all__ = ["MAPAS", "colorir", "ampliar", "faixa_rgba", "polar_rgba", "png", "rgba_bytes"]

#: Escalas de cor: cinza; cinza invertida; "quente" (preto → vermelho → amarelo → branco) e
#: "fria" (cool: preto → azul → ciano → branco), as duas monotônicas em luminância.
MAPAS = ("cinza", "invertida", "quente", "fria")
_QUENTE = np.array(
    [
        [0.00, 0, 0, 0],
        [0.30, 150, 20, 10],
        [0.55, 230, 90, 20],
        [0.80, 250, 200, 60],
        [1.00, 255, 255, 255],
    ]
)
_FRIA = np.array(
    [
        [0.00, 0, 0, 0],
        [0.30, 10, 30, 160],
        [0.55, 20, 110, 235],
        [0.80, 80, 220, 250],
        [1.00, 255, 255, 255],
    ]
)
_TABELAS = {"quente": _QUENTE, "fria": _FRIA}
FUNDO = (12, 20, 30)


def colorir(valores: np.ndarray, teto: float, mapa: str = "quente", piso: float = 0.0) -> np.ndarray:
    """RGB uint8 (…, 3) de valores entre ``piso`` (preto) e ``teto`` (branco). NaN → cor de fundo."""
    v = np.asarray(valores, dtype=np.float64)
    nan = ~np.isfinite(v)
    t = np.clip((np.nan_to_num(v) - piso) / max(teto - piso, 1e-9), 0.0, 1.0)
    if mapa in _TABELAS:
        tab = _TABELAS[mapa]
        rgb = np.stack([np.interp(t, tab[:, 0], tab[:, k]) for k in (1, 2, 3)], axis=-1)
    else:
        g = 255.0 * (1.0 - t if mapa == "invertida" else t)
        rgb = np.stack([g, g, g], axis=-1)
    rgb[nan] = (255, 255, 255) if mapa == "invertida" else FUNDO
    return np.rint(rgb).astype(np.uint8)


def ampliar(img: np.ndarray, fator: int) -> np.ndarray:
    """Ampliação bilinear por um fator inteiro (só para exibir as imagens pequenas do SPECT)."""
    a = np.asarray(img, dtype=np.float64)
    n0, n1 = a.shape
    y = (np.arange(n0 * fator) + 0.5) / fator - 0.5
    x = (np.arange(n1 * fator) + 0.5) / fator - 0.5
    y0 = np.clip(np.floor(y).astype(int), 0, n0 - 1)
    x0 = np.clip(np.floor(x).astype(int), 0, n1 - 1)
    y1 = np.clip(y0 + 1, 0, n0 - 1)
    x1 = np.clip(x0 + 1, 0, n1 - 1)
    wy = np.clip(y - y0, 0, 1)[:, None]
    wx = np.clip(x - x0, 0, 1)[None, :]
    return (a[y0][:, x0] * (1 - wy) * (1 - wx) + a[y1][:, x0] * wy * (1 - wx) + a[y0][:, x1] * (1 - wy) * wx + a[y1][:, x1] * wy * wx)


def rgba_bytes(rgb: np.ndarray) -> np.ndarray:
    saida = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    saida[..., :3] = rgb
    saida[..., 3] = 255
    return saida


def faixa_rgba(imagens: np.ndarray, teto: float, mapa: str, fator: int = 4, espaco: int = 2) -> np.ndarray:
    """Cortes lado a lado (ampliados), separados por ``espaco`` pixels claros."""
    partes = []
    for k, im in enumerate(imagens):
        if k:
            partes.append(np.full((imagens.shape[1] * fator, espaco, 3), 255, dtype=np.uint8))
        partes.append(colorir(ampliar(im, fator), teto, mapa))
    return rgba_bytes(np.concatenate(partes, axis=1))


# Algarismos 5 × 7 para escrever os escores no PNG do mapa polar (sem depender de fontes).
_DIGITOS = {
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    "–": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
}


def _escrever(rgb: np.ndarray, texto: str, cx: float, cy: float, escala: int = 2) -> None:
    larg = len(texto) * 6 * escala - escala
    x0 = int(round(cx - larg / 2))
    y0 = int(round(cy - 7 * escala / 2))
    for k, ch in enumerate(texto):
        mapa = _DIGITOS.get(ch)
        if not mapa:
            continue
        for r, linha in enumerate(mapa):
            for c, bit in enumerate(linha):
                if bit == "1":
                    ys = slice(y0 + r * escala, y0 + (r + 1) * escala)
                    xs = slice(x0 + (k * 6 + c) * escala, x0 + (k * 6 + c + 1) * escala)
                    # contorno escuro e algarismo branco
                    rgb[max(ys.start - 1, 0) : ys.stop + 1, max(xs.start - 1, 0) : xs.stop + 1] = (8, 16, 25)
        for r, linha in enumerate(mapa):
            for c, bit in enumerate(linha):
                if bit == "1":
                    rgb[y0 + r * escala : y0 + (r + 1) * escala, x0 + (k * 6 + c) * escala : x0 + (k * 6 + c + 1) * escala] = (255, 255, 255)


def polar_rgba(mapa_img: np.ndarray, rho_apice: float, mapa: str = "quente", escores: dict | None = None, lado: int | None = None) -> np.ndarray:
    """Mapa polar colorido (0–100%), com as bordas dos 17 segmentos e, se dados, os escores escritos."""
    lado = lado or mapa_img.shape[0]
    rgb = colorir(mapa_img, 100.0, mapa).copy()
    m = (lado - 1) / 2.0
    yy, xx = np.mgrid[0:lado, 0:lado]
    x = (xx - m) / (m + 0.5)
    y = (m - yy) / (m + 0.5)
    rho = np.hypot(x, y)
    ang = np.degrees(np.arctan2(y, x)) % 360.0
    seg = np.zeros((lado, lado), dtype=int)
    dentro = rho <= 1.0
    seg[dentro] = [segmento_em(r, a, rho_apice) for r, a in zip(rho[dentro], ang[dentro])]
    borda = np.zeros_like(dentro)
    borda[:-1, :] |= seg[:-1, :] != seg[1:, :]
    borda[:, :-1] |= seg[:, :-1] != seg[:, 1:]
    borda &= dentro | np.roll(dentro, 1, 0) | np.roll(dentro, 1, 1)
    rgb[borda] = (200, 210, 220)
    if escores:
        for g in geometria_segmentos(rho_apice, lado):
            v = escores.get(g["segmento"])
            texto = "–" if v is None else str(int(v))
            _escrever(rgb, texto, g["rotulo"][0], g["rotulo"][1], escala=max(1, lado // 128))
    rgba = rgba_bytes(rgb)
    rgba[..., 3] = np.where(dentro | borda, 255, 0)  # fora do círculo: transparente
    return rgba


def png(rgba: np.ndarray) -> bytes:
    return codificar_png(rgba)
