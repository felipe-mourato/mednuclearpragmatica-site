"""Reorientação: eixo longo do VE em duas etapas e cortes eixo curto, eixo longo vertical e horizontal.

Método manual descrito por Germano (J Nucl Med 2001;42:1499-507): o eixo
longo do VE é traçado num corte transaxial medioventricular; o volume é
reamostrado num plano que contém essa linha (eixo longo vertical), onde o
eixo é traçado de novo. As duas linhas definem o eixo no espaço.

Nesta ferramenta:

1. No transaxial k, o usuário marca a base (B₁) e o ápice (A₁): d = (A₁ − B₁)
   normalizado, no plano x-y.
2. O plano vertical contém d e o eixo z (cabeça). Nele, o ponto (s, v)
   corresponde a O + s·d + v·ẑ, com O = ponto médio de B₁A₁ no corte k. O
   usuário marca de novo a base B e o ápice A.

Sistema do VE (todas as direções em mm, x esquerda, y trás, z cabeça):

* a = (A − B)/|A − B|: para o ápice;
* w = componente de ẑ perpendicular a a, normalizada: a parede anterior
  fica em cima nos cortes (no traçado manual o plano vertical contém ẑ);
* h = w × a: para a parede lateral.

Exibição (padrão de cortes e de segmentação, Cerqueira et al., J Nucl Cardiol
2002;9:240-5; figura reproduzida na diretriz ASNC de laudos, 2017, e
Tabela 18 da diretriz SBC 2020):

* eixo curto: cortes do ápice para a base; na imagem, anterior em cima,
  septo à esquerda e lateral à direita;
* eixo longo vertical: cortes do septo para a lateral; anterior em cima e
  ápice à direita;
* eixo longo horizontal: cortes de inferior para anterior; ápice em cima,
  septo à esquerda e lateral à direita.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .reconstrucao import Volume

__all__ = ["Eixo", "base_vetorial", "plano_vertical", "corte", "cortes", "MARGEM_FATIAS", "LADO_CORTE_MM", "MEIA_LARGURA_LONGO_MM"]

Z = np.array([0.0, 0.0, 1.0])
#: Lado da imagem de cada corte reorientado (mm) e meia-largura da pilha de cortes longos.
LADO_CORTE_MM = 140.0
MEIA_LARGURA_LONGO_MM = 35.0
#: Cortes extras além do ápice e da base, no eixo curto.
MARGEM_FATIAS = 1


@dataclass
class Eixo:
    """Eixo do VE de um estudo: base e ápice (mm) e o que foi marcado em cada etapa (para editar)."""

    base: np.ndarray
    apice: np.ndarray
    corte_transaxial: int
    base_1: tuple  # (coluna, linha) no transaxial
    apice_1: tuple
    base_2: tuple  # (coluna, linha) no plano vertical
    apice_2: tuple

    @property
    def comprimento(self) -> float:
        return float(np.linalg.norm(self.apice - self.base))

    def como_dict(self) -> dict:
        # Sem arredondar: o protocolo reproduz o cálculo bit a bit no lote.
        r = lambda v: [float(x) for x in v]  # noqa: E731
        return {
            "base_mm": r(self.base),
            "apice_mm": r(self.apice),
            "corte_transaxial": int(self.corte_transaxial),
            "base_1": r(self.base_1),
            "apice_1": r(self.apice_1),
            "base_2": r(self.base_2),
            "apice_2": r(self.apice_2),
        }


def base_vetorial(base, apice) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(a, w, h): para o ápice, para a parede anterior e para a parede lateral (unitários).

    a = (A − B)/|A − B|; w = (ẑ − (ẑ·a)a) normalizado; h = w × a.
    Se o eixo for quase vertical, usa −ŷ (anterior) no lugar de ẑ.
    """
    a = np.asarray(apice, dtype=np.float64) - np.asarray(base, dtype=np.float64)
    norma = np.linalg.norm(a)
    if norma < 1e-6:
        raise ValueError("Base e ápice no mesmo ponto: trace o eixo de novo.")
    a = a / norma
    ref = Z if abs(a @ Z) < 0.95 else np.array([0.0, -1.0, 0.0])
    w = ref - (ref @ a) * a
    w /= np.linalg.norm(w)
    h = np.cross(w, a)
    return a, w, h


def geometria_plano_vertical(vol: Volume, corte_k: int, base_1, apice_1) -> tuple[np.ndarray, np.ndarray]:
    """Origem O (mm) e direção d do plano vertical a partir da linha no transaxial (coluna, linha)."""
    p_b = vol.para_mm(corte_k, base_1[1], base_1[0])
    p_a = vol.para_mm(corte_k, apice_1[1], apice_1[0])
    d = p_a - p_b
    d[2] = 0.0
    n = np.linalg.norm(d)
    if n < 1e-6:
        raise ValueError("Base e ápice no mesmo ponto do transaxial: trace a linha de novo.")
    return (p_a + p_b) / 2.0, d / n


def plano_vertical(vol: Volume, corte_k: int, base_1, apice_1, n: int | None = None) -> np.ndarray:
    """Imagem do plano vertical (n × n, mesmo pixel do volume): coluna → +d (ápice à direita), linha → −ẑ.

    O centro da imagem é O. Ponto (coluna c, linha r) ↔ O + (c − m)Δ·d − (r − m)Δ·ẑ, m = (n − 1)/2.
    """
    n = int(n or vol.n)
    o, d = geometria_plano_vertical(vol, corte_k, base_1, apice_1)
    m = (n - 1) / 2.0
    cc, rr = np.meshgrid(np.arange(n) - m, np.arange(n) - m)
    pts = o + (cc[..., None] * d - rr[..., None] * Z) * vol.pixel_mm
    return vol.amostrar(pts)


def eixo_de_marcacoes(vol: Volume, corte_k: int, base_1, apice_1, base_2, apice_2, n: int | None = None) -> Eixo:
    """Eixo 3D a partir das duas etapas (pontos em pixels de cada imagem)."""
    n = int(n or vol.n)
    o, d = geometria_plano_vertical(vol, corte_k, base_1, apice_1)
    m = (n - 1) / 2.0

    def ponto(p):
        return o + ((float(p[0]) - m) * d - (float(p[1]) - m) * Z) * vol.pixel_mm

    b, a = ponto(base_2), ponto(apice_2)
    if np.linalg.norm(a - b) < 2 * vol.pixel_mm:
        raise ValueError("Eixo curto demais: marque a base e o ápice nas extremidades do VE.")
    return Eixo(b, a, int(corte_k), tuple(map(float, base_1)), tuple(map(float, apice_1)), tuple(map(float, base_2)), tuple(map(float, apice_2)))


def marcacoes_de_eixo(vol: Volume, base, apice, n: int | None = None) -> Eixo:
    """Inverso aproximado: marcações das duas etapas que reproduzem um eixo dado (ex.: copiado de outro estudo)."""
    n = int(n or vol.n)
    base = np.asarray(base, dtype=np.float64)
    apice = np.asarray(apice, dtype=np.float64)
    meio = (base + apice) / 2.0
    k = int(np.clip(round(float(vol.para_indices(meio)[0])), 0, vol.n_cortes - 1))
    d = apice - base
    d[2] = 0.0
    if np.linalg.norm(d) < 1e-6:
        d = np.array([1.0, 0.0, 0.0])
    d /= np.linalg.norm(d)
    meio_k = meio.copy()
    meio_k[2] = vol.z_mm[k]
    pb1 = vol.para_indices(meio_k - d * np.linalg.norm((apice - base)[:2]) / 2.0)
    pa1 = vol.para_indices(meio_k + d * np.linalg.norm((apice - base)[:2]) / 2.0)
    base_1 = (float(pb1[2]), float(pb1[1]))
    apice_1 = (float(pa1[2]), float(pa1[1]))
    o, d2 = geometria_plano_vertical(vol, k, base_1, apice_1)
    m = (n - 1) / 2.0

    def no_plano(p):
        rel = p - o
        return ((rel @ d2) / vol.pixel_mm + m, -(rel @ Z) / vol.pixel_mm + m)

    return Eixo(base, apice, k, base_1, apice_1, no_plano(base), no_plano(apice))


def _grade(centro, dir_col, dir_lin, pixel_mm, n):
    m = (n - 1) / 2.0
    cc, rr = np.meshgrid(np.arange(n) - m, np.arange(n) - m)
    return centro + (cc[..., None] * dir_col + rr[..., None] * dir_lin) * pixel_mm


def posicoes(eixo: Eixo, pixel_mm: float, tipo: str) -> np.ndarray:
    """Distâncias (mm) dos cortes ao longo do eixo de empilhamento.

    Eixo curto: do ápice (0) para a base (+), com ``MARGEM_FATIAS`` a mais
    de cada lado. Longos: de −35 a +35 mm do eixo, de pixel em pixel.
    """
    if tipo == "SA":
        n = int(np.floor(eixo.comprimento / pixel_mm))
        return np.arange(-MARGEM_FATIAS, n + 1 + MARGEM_FATIAS) * pixel_mm
    m = int(np.floor(MEIA_LARGURA_LONGO_MM / pixel_mm))
    return np.arange(-m, m + 1) * pixel_mm


def corte(vol: Volume, eixo: Eixo, tipo: str, distancia_mm: float, n: int | None = None) -> np.ndarray:
    """Um corte reorientado (n × n pixels de Δ mm).

    SA: centro = A − distância·a; coluna → h (lateral), linha → −w (de anterior para inferior).
    VLA: centro = meio do eixo + distância·h; coluna → a (ápice à direita), linha → −w.
    HLA: centro = meio do eixo + distância·w; coluna → h, linha → −a (ápice em cima).
    """
    n = int(n or int(round(LADO_CORTE_MM / vol.pixel_mm)))
    a, w, h = base_vetorial(eixo.base, eixo.apice)
    meio = (eixo.base + eixo.apice) / 2.0
    if tipo == "SA":
        pts = _grade(eixo.apice - distancia_mm * a, h, -w, vol.pixel_mm, n)
    elif tipo == "VLA":
        pts = _grade(meio + distancia_mm * h, a, -w, vol.pixel_mm, n)
    elif tipo == "HLA":
        pts = _grade(meio + distancia_mm * w, h, -a, vol.pixel_mm, n)
    else:
        raise ValueError("Tipo de corte deve ser SA, VLA ou HLA.")
    return vol.amostrar(pts)


def cortes(vol: Volume, eixo: Eixo, tipo: str, n: int | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Pilha de cortes de um tipo: (distâncias em mm, imagens (cortes, n, n))."""
    pos = posicoes(eixo, vol.pixel_mm, tipo)
    return pos, np.stack([corte(vol, eixo, tipo, float(d), n) for d in pos])


def plano_vertical_info(vol: Volume, corte_k: int, base_1, apice_1):
    return geometria_plano_vertical(vol, corte_k, base_1, apice_1)
