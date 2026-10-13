"""Operações morfológicas simples sobre máscaras booleanas (só NumPy).

Usadas para o anel de fundo perirrenal e para desenhar contornos nas
figuras do laudo. Nada aqui depende de SciPy, para rodar igual no navegador
(Pyodide) e no computador.
"""

from __future__ import annotations

import numpy as np

__all__ = ["deslocamentos_disco", "dilatar_disco", "erodir_quadrado", "contorno", "rle_codificar", "rle_decodificar"]


def deslocamentos_disco(raio: float) -> list[tuple[int, int]]:
    """Deslocamentos inteiros (dy, dx) com dy² + dx² ≤ raio², em ordem fixa."""
    r = int(np.floor(raio))
    saida = []
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dy * dy + dx * dx <= raio * raio + 1e-9:
                saida.append((dy, dx))
    return saida


def _deslocar(mascara: np.ndarray, dy: int, dx: int) -> np.ndarray:
    """Máscara deslocada por (dy, dx), preenchendo com falso o que entra pela borda."""
    linhas, colunas = mascara.shape
    saida = np.zeros_like(mascara)
    ys = slice(max(dy, 0), linhas + min(dy, 0))
    yo = slice(max(-dy, 0), linhas + min(-dy, 0))
    xs = slice(max(dx, 0), colunas + min(dx, 0))
    xo = slice(max(-dx, 0), colunas + min(-dx, 0))
    saida[ys, xs] = mascara[yo, xo]
    return saida


def dilatar_disco(mascara: np.ndarray, raio: float) -> np.ndarray:
    """Dilatação por um disco de raio dado (distância euclidiana entre centros de pixel).

    Um pixel p entra na máscara dilatada quando existe um pixel q da máscara
    original com |p − q| ≤ raio. A imagem não é estendida: a dilatação para
    na borda.
    """
    m = np.asarray(mascara, dtype=bool)
    saida = np.zeros_like(m)
    if raio <= 0 or not m.any():
        return m.copy()
    for dy, dx in deslocamentos_disco(raio):
        saida |= _deslocar(m, dy, dx)
    return saida


def erodir_quadrado(mascara: np.ndarray, raio: int = 1) -> np.ndarray:
    """Erosão por um quadrado (2·raio + 1)²; pixels fora da imagem contam como fora."""
    m = np.asarray(mascara, dtype=bool)
    saida = m.copy()
    for dy in range(-raio, raio + 1):
        for dx in range(-raio, raio + 1):
            saida &= _deslocar(m, dy, dx)
    return saida


def contorno(mascara: np.ndarray, espessura: int = 1) -> np.ndarray:
    """Pixels da máscara que estão a até ``espessura`` pixels da sua borda."""
    m = np.asarray(mascara, dtype=bool)
    return m & ~erodir_quadrado(m, espessura)


def rle_codificar(mascara: np.ndarray) -> list[list[int]]:
    """Codifica a máscara por trechos [início, comprimento] na ordem linha a linha.

    Formato compacto e exato para guardar no protocolo de reprodução a
    geometria calculada automaticamente.
    """
    plano = np.asarray(mascara, dtype=bool).ravel()
    if not plano.any():
        return []
    d = np.diff(np.concatenate(([0], plano.astype(np.int8), [0])))
    inicios = np.flatnonzero(d == 1)
    fins = np.flatnonzero(d == -1)
    return [[int(a), int(b - a)] for a, b in zip(inicios, fins)]


def rle_decodificar(trechos, linhas: int, colunas: int) -> np.ndarray:
    """Inverso de :func:`rle_codificar`."""
    plano = np.zeros(linhas * colunas, dtype=bool)
    for inicio, comprimento in trechos:
        inicio, comprimento = int(inicio), int(comprimento)
        if inicio < 0 or comprimento < 0 or inicio + comprimento > plano.size:
            raise ValueError("Máscara do protocolo fora das dimensões da imagem.")
        plano[inicio : inicio + comprimento] = True
    return plano.reshape(linhas, colunas)
