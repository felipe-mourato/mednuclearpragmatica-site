"""Cálculos da cintilografia de esvaziamento gástrico.

Protocolo de referência: refeição sólida padronizada marcada com ⁹⁹ᵐTc,
imagens anterior e posterior em 0, 1, 2 e 4 h, média geométrica e correção
de decaimento (Abell 2008; Donohoe 2009). As funções aceitam qualquer
número de tempos (mínimo 3 na interface).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

from ..comum.contagens import fator_decaimento, media_geometrica, soma_contagens

__all__ = [
    "ContagensRegionais",
    "LinhaResultado",
    "RETENCAO_MINIMA_REGIONAL",
    "retencao_percentual",
    "contagens_regionais",
    "calcular_resultados",
]

#: Abaixo desta retenção total (%), a distribuição regional não é avaliável
#: (contagens insuficientes). Silver 2022: "<5% TGR ... non-evaluable for RIMD".
RETENCAO_MINIMA_REGIONAL = 5.0


@dataclass
class ContagensRegionais:
    """Contagens de um tempo: por vista e médias geométricas por região."""

    minutos: float
    total_ant: float
    total_post: float
    proximal_ant: float
    proximal_post: float
    mg_total: float
    mg_proximal: float
    mg_distal: float


@dataclass
class LinhaResultado:
    rotulo: str
    minutos: float
    mg_total: float
    mg_proximal: float
    mg_distal: float
    distribuicao_proximal: float
    razao_pd: float | None
    esvaziamento: float
    retencao: float
    retencao_proximal: float
    retencao_distal: float
    regional_avaliavel: bool

    def como_dict(self) -> dict:
        return asdict(self)


def retencao_percentual(mg_t: float, mg_t0: float, minutos: float, meia_vida_h: float | None) -> float:
    """Retenção gástrica no tempo t, em % da atividade do T0.

    R(t) = MG(t) / MG(T0) × 100 × 2^( t / (T½ × 60) )

    com t em minutos desde o T0 e T½ em horas. Sem meia-vida (``None``),
    não há correção de decaimento: R(t) = MG(t) / MG(T0) × 100.

    Referências: Abell TL et al. Am J Gastroenterol. 2008;103:753-63.
    doi:10.1111/j.1572-0241.2007.01636.x · Donohoe KJ et al. J Nucl Med
    Technol. 2009;37:196-200. doi:10.2967/jnmt.109.067843
    """
    if mg_t0 <= 0:
        raise ValueError("Contagem do T0 igual a zero: retenção indefinida.")
    return (mg_t / mg_t0) * 100.0 * fator_decaimento(minutos, meia_vida_h)


def contagens_regionais(
    minutos: float,
    valores_ant: np.ndarray,
    valores_post: np.ndarray,
    mascara_ant: np.ndarray,
    proximal_ant: np.ndarray,
    mascara_post: np.ndarray,
    proximal_post: np.ndarray,
) -> ContagensRegionais:
    """Contagens totais e proximais nas duas vistas e as médias geométricas.

    MG_total = √( C_ANT(ROI total) × C_PÓS(ROI total) )
    MG_prox  = √( C_ANT(proximal) × C_PÓS(proximal) )
    MG_dist  = MG_total − MG_prox

    Contagens distais = total − proximal, como em Silver et al. 2022
    (Neurogastroenterol Motil 2022;34:e14436, doi:10.1111/nmo.14436). As
    máscaras posteriores vêm da ROI e do eixo espelhados.
    """
    t_a = soma_contagens(valores_ant, mascara_ant)
    t_p = soma_contagens(valores_post, mascara_post)
    p_a = soma_contagens(valores_ant, proximal_ant)
    p_p = soma_contagens(valores_post, proximal_post)
    mg_total = media_geometrica(t_a, t_p)
    mg_prox = media_geometrica(p_a, p_p)
    return ContagensRegionais(
        minutos=float(minutos),
        total_ant=t_a,
        total_post=t_p,
        proximal_ant=p_a,
        proximal_post=p_p,
        mg_total=mg_total,
        mg_proximal=mg_prox,
        mg_distal=mg_total - mg_prox,
    )


def calcular_resultados(tempos: list[ContagensRegionais], meia_vida_h: float | None) -> list[LinhaResultado]:
    """Monta a tabela de resultados (o primeiro item é o T0).

    Para cada tempo t:

    - Retenção R(t): ver :func:`retencao_percentual`; R(T0) = 100.
    - Esvaziamento E(t) = 100 − R(t); E(T0) = 0.
    - Distribuição proximal D(t) = MG_prox(t) / MG_total(t) × 100 (no T0, é a
      distribuição intragástrica da refeição, IMD; Orthey 2018).
    - Razão proximal/distal PDCR(t) = MG_prox(t) / MG_dist(t) (Silver 2022).
    - Retenção proximal Rp(t) = R(t) × D(t) / 100; distal Rd(t) = R(t) − Rp(t).

    Rp + Rd = R em todas as linhas. Com R(t) < 5%, PDCR fica indefinida
    (``None``) e a linha é marcada como não avaliável para a distribuição
    regional (Silver 2022).
    """
    if not tempos:
        return []
    mg_t0 = tempos[0].mg_total
    linhas = []
    for i, t in enumerate(tempos):
        if i == 0:
            retencao, esvaziamento = 100.0, 0.0
        else:
            retencao = retencao_percentual(t.mg_total, mg_t0, t.minutos, meia_vida_h)
            esvaziamento = 100.0 - retencao
        distribuicao = (t.mg_proximal / t.mg_total) * 100.0 if t.mg_total > 0 else 0.0
        avaliavel = retencao >= RETENCAO_MINIMA_REGIONAL and t.mg_total > 0
        razao = t.mg_proximal / t.mg_distal if (avaliavel and t.mg_distal > 0) else None
        ret_prox = retencao * distribuicao / 100.0
        linhas.append(
            LinhaResultado(
                rotulo=f"T{i}",
                minutos=t.minutos,
                mg_total=t.mg_total,
                mg_proximal=t.mg_proximal,
                mg_distal=t.mg_distal,
                distribuicao_proximal=distribuicao,
                razao_pd=razao,
                esvaziamento=esvaziamento,
                retencao=retencao,
                retencao_proximal=ret_prox,
                retencao_distal=retencao - ret_prox,
                regional_avaliavel=avaliavel,
            )
        )
    return linhas
