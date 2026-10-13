"""Cálculos da cintilografia renal com ⁹⁹ᵐTc-DMSA.

Notação: D = rim direito, E = rim esquerdo; C = contagens, A = área da ROI
em pixels; "post" e "ant" são as projeções posterior e anterior.

Todas as contagens vêm dos valores dos pixels com rescale aplicado (nunca
da exibição). Todas as funções relativas somam 100% por construção.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from ..comum.contagens import media_geometrica, soma_contagens

__all__ = [
    "ContagensRim",
    "Parametro",
    "ResultadoDMSA",
    "contagens_rim",
    "contagem_corrigida",
    "percentual",
    "arredondar_par",
    "funcao_relativa",
    "area_relativa",
    "funcao_corrigida_tamanho",
    "calcular",
]


@dataclass(frozen=True)
class ContagensRim:
    rim: str  # "D" ou "E"
    vista: str  # "post" ou "ant"
    bruta: float
    area_px: int
    fundo_soma: float
    fundo_pixels: int
    fundo_por_pixel: float
    corrigida: float

    def como_dict(self) -> dict:
        return asdict(self)


def contagem_corrigida(bruta: float, area_px: int, fundo_por_pixel: float) -> float:
    """Contagem do rim corrigida pelo fundo.

    C_corr = máx(0, C_rim − (C_fundo ÷ A_fundo) × A_rim)

    O fundo por pixel (C_fundo ÷ A_fundo) é multiplicado pela área do rim e
    subtraído da contagem do rim (Vali et al., Clin Transl Imaging
    2022;10:173-84, doi:10.1007/s40336-022-00484-x: subtrair o fundo medido
    perto do rim). Resultado negativo (fundo maior que o rim) vira zero.
    """
    return max(0.0, float(bruta) - float(fundo_por_pixel) * int(area_px))


def contagens_rim(
    valores: np.ndarray, mascara_rim: np.ndarray, mascara_fundo: np.ndarray | None, rim: str, vista: str
) -> ContagensRim:
    """Contagens de um rim numa vista, com o fundo da região dada (ou sem fundo, se ``None``)."""
    area = int(np.count_nonzero(mascara_rim))
    if area == 0:
        raise ValueError(f"ROI do rim {'direito' if rim == 'D' else 'esquerdo'} vazia na vista {vista}.")
    bruta = soma_contagens(valores, mascara_rim)
    if mascara_fundo is None:
        return ContagensRim(rim, vista, bruta, area, 0.0, 0, 0.0, bruta)
    n_fundo = int(np.count_nonzero(mascara_fundo))
    if n_fundo == 0:
        raise ValueError(
            f"Região de fundo vazia para o rim {'direito' if rim == 'D' else 'esquerdo'} na vista {vista}."
        )
    soma_fundo = soma_contagens(valores, mascara_fundo)
    por_pixel = soma_fundo / n_fundo
    return ContagensRim(rim, vista, bruta, area, soma_fundo, n_fundo, por_pixel, contagem_corrigida(bruta, area, por_pixel))


def percentual(parte_d: float, parte_e: float) -> float:
    """Percentual do rim direito: D ÷ (D + E) × 100. O do esquerdo é 100 − este."""
    total = float(parte_d) + float(parte_e)
    if not math.isfinite(total) or total <= 0:
        raise ValueError("Soma dos dois rins igual a zero: não há função relativa definida.")
    return float(parte_d) / total * 100.0


def arredondar_par(percentual_d: float) -> tuple[float, float]:
    """Arredonda o percentual do rim direito a uma casa (metade para cima) e completa o esquerdo.

    D' = ⌊10·D + 0,5⌋ ÷ 10;  E' = 100 − D'. Assim os dois valores mostrados
    somam exatamente 100,0%.
    """
    d = math.floor(percentual_d * 10.0 + 0.5) / 10.0
    return d, round(100.0 - d, 1)


def funcao_relativa(c_d: float, c_e: float) -> float:
    """Função renal relativa do rim direito (%).

    FRR_D = C_D ÷ (C_D + C_E) × 100, com as contagens corrigidas pelo fundo
    (Vali et al., 2022). Vale para a vista posterior e para a média
    geométrica √(C_ant × C_post) de cada rim.
    """
    return percentual(c_d, c_e)


def area_relativa(a_d: float, a_e: float) -> float:
    """Área renal relativa do rim direito (%): A_D ÷ (A_D + A_E) × 100, com A em pixels da ROI."""
    return percentual(a_d, a_e)


def funcao_corrigida_tamanho(c_d: float, a_d: float, c_e: float, a_e: float) -> float:
    """Função relativa corrigida pelo tamanho (contagem por pixel), rim direito (%).

    FRR_tam,D = (C_D ÷ A_D) ÷ (C_D ÷ A_D + C_E ÷ A_E) × 100

    Segue a ideia de Estorch et al. (Nucl Med Commun 2004;25:167-70,
    doi:10.1097/00006231-200402000-00013): corrigir a captação relativa pelo
    tamanho do rim separa o rim pequeno e normal do rim hipofuncionante.
    Aqui o tamanho é a área da ROI na imagem planar, em pixels; é uma
    projeção, não o volume (ver o laudo).
    """
    if a_d <= 0 or a_e <= 0:
        raise ValueError("Área de ROI igual a zero.")
    return percentual(c_d / a_d, c_e / a_e)


@dataclass(frozen=True)
class Parametro:
    chave: str
    titulo: str
    d: float | None  # percentual bruto do rim direito
    d_arred: float | None
    e_arred: float | None
    comparar: bool  # se tem faixa de normalidade

    @property
    def e(self) -> float | None:
        return None if self.d is None else 100.0 - self.d

    @property
    def disponivel(self) -> bool:
        return self.d is not None


@dataclass(frozen=True)
class ResultadoDMSA:
    post: dict  # rim -> ContagensRim
    ant: dict | None  # rim -> ContagensRim ou None sem anterior
    parametros: tuple  # Parametro, na ordem da tabela
    mg_contagens: dict | None  # rim -> √(C_ant × C_post)

    def parametro(self, chave: str) -> Parametro:
        for p in self.parametros:
            if p.chave == chave:
                return p
        raise KeyError(chave)


def _par(chave: str, titulo: str, valor_d: float | None, comparar: bool) -> Parametro:
    if valor_d is None:
        return Parametro(chave, titulo, None, None, None, comparar)
    d, e = arredondar_par(valor_d)
    return Parametro(chave, titulo, valor_d, d, e, comparar)


TITULOS = {
    "frr_post": "Função relativa, posterior",
    "frr_mg": "Função relativa, média geométrica",
    "area_post": "Área relativa, posterior",
    "area_mg": "Área relativa, média geométrica",
    "tam_post": "Função corrigida pelo tamanho, posterior",
    "tam_mg": "Função corrigida pelo tamanho, média geométrica",
}


def calcular(post: dict, ant: dict | None = None) -> ResultadoDMSA:
    """Todos os parâmetros a partir das contagens de cada rim (e da anterior, se houver).

    ``post`` e ``ant``: dicionários {"D": ContagensRim, "E": ContagensRim}.
    Sem anterior, os parâmetros por média geométrica ficam indisponíveis.

    Médias geométricas (por rim): contagens √(C_ant × C_post); áreas
    √(A_ant × A_post); contagem por pixel √((C_ant ÷ A_ant) × (C_post ÷ A_post)).
    """
    d, e = post["D"], post["E"]
    frr_post = funcao_relativa(d.corrigida, e.corrigida)
    area_post = area_relativa(d.area_px, e.area_px)
    tam_post = funcao_corrigida_tamanho(d.corrigida, d.area_px, e.corrigida, e.area_px)
    frr_mg = area_mg = tam_mg = None
    mg = None
    if ant is not None:
        da, ea = ant["D"], ant["E"]
        mg = {
            "D": media_geometrica(da.corrigida, d.corrigida),
            "E": media_geometrica(ea.corrigida, e.corrigida),
        }
        frr_mg = funcao_relativa(mg["D"], mg["E"])
        area_mg = area_relativa(media_geometrica(da.area_px, d.area_px), media_geometrica(ea.area_px, e.area_px))
        esp_d = media_geometrica(da.corrigida / da.area_px, d.corrigida / d.area_px)
        esp_e = media_geometrica(ea.corrigida / ea.area_px, e.corrigida / e.area_px)
        tam_mg = percentual(esp_d, esp_e)
    parametros = (
        _par("frr_post", TITULOS["frr_post"], frr_post, True),
        _par("frr_mg", TITULOS["frr_mg"], frr_mg, True),
        _par("area_post", TITULOS["area_post"], area_post, False),
        _par("area_mg", TITULOS["area_mg"], area_mg, False),
        _par("tam_post", TITULOS["tam_post"], tam_post, False),
        _par("tam_mg", TITULOS["tam_mg"], tam_mg, False),
    )
    return ResultadoDMSA(post, ant, parametros, mg)
