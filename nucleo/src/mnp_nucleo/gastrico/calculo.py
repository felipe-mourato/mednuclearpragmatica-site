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
    "retencao_percentual",
    "contagens_regionais",
    "calcular_resultados",
    "REFERENCIA_TOUGAS_2000",
]


@dataclass
class ContagensRegionais:
    """Contagens de um tempo: por vista e médias geométricas por região."""

    minutos: float
    total_ant: float
    total_post: float
    proximal_ant: float
    proximal_post: float
    distal_ant: float
    distal_post: float
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
    esvaziamento: float
    retencao: float
    retencao_proximal: float
    retencao_distal: float

    def como_dict(self) -> dict:
        return asdict(self)


#: Percentil 95 da retenção gástrica em 123 voluntários saudáveis, refeição
#: de baixo teor de gordura (substituto de ovo) marcada com ⁹⁹ᵐTc.
#: Retenção acima desses valores indica esvaziamento lento NESSE protocolo.
#: Tougas G et al. Am J Gastroenterol. 2000;95:1456-62.
#: doi:10.1111/j.1572-0241.2000.02076.x
REFERENCIA_TOUGAS_2000 = (
    {"minutos": 60, "mediana": 69.0, "p95": 90.0},
    {"minutos": 120, "mediana": 24.0, "p95": 60.0},
    {"minutos": 240, "mediana": 1.2, "p95": 10.0},
)


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
    distal_ant: np.ndarray,
    mascara_post: np.ndarray,
    proximal_post: np.ndarray,
    distal_post: np.ndarray,
) -> ContagensRegionais:
    """Soma as contagens de cada região nas duas vistas e calcula as médias geométricas.

    MG(região) = √( C_ANT(região) × C_POST(região) ), região ∈ {total, proximal, distal}.

    As máscaras posteriores vêm da ROI espelhada (ver
    :func:`mnp_nucleo.comum.roi.espelhar_horizontal`), segmentada de novo
    para que proximal continue sendo a metade superior.
    """
    t_a = soma_contagens(valores_ant, mascara_ant)
    t_p = soma_contagens(valores_post, mascara_post)
    p_a = soma_contagens(valores_ant, proximal_ant)
    p_p = soma_contagens(valores_post, proximal_post)
    d_a = soma_contagens(valores_ant, distal_ant)
    d_p = soma_contagens(valores_post, distal_post)
    return ContagensRegionais(
        minutos=float(minutos),
        total_ant=t_a,
        total_post=t_p,
        proximal_ant=p_a,
        proximal_post=p_p,
        distal_ant=d_a,
        distal_post=d_p,
        mg_total=media_geometrica(t_a, t_p),
        mg_proximal=media_geometrica(p_a, p_p),
        mg_distal=media_geometrica(d_a, d_p),
    )


def calcular_resultados(tempos: list[ContagensRegionais], meia_vida_h: float | None) -> list[LinhaResultado]:
    """Monta a tabela de resultados (o primeiro item é o T0).

    Para cada tempo t:

    - Retenção R(t): ver :func:`retencao_percentual`; R(T0) = 100.
    - Esvaziamento E(t) = 100 − R(t); E(T0) = 0.
    - Distribuição proximal D(t) = MG_prox(t) / MG_total(t) × 100. No T0 é a
      distribuição intragástrica da refeição (IMD₀; Orthey 2018).
    - Retenção proximal Rp(t) = R(t) × D(t) / 100.
    - Retenção distal Rd(t) = R(t) − Rp(t).

    Assim Rp + Rd = R em todas as linhas. Nota: como √(a·b) não é aditiva,
    MG_prox + MG_dist em geral difere um pouco de MG_total; por isso as
    parcelas usam a fração D(t), e não MG_dist diretamente.
    """
    if not tempos:
        return []
    mg_t0 = tempos[0].mg_total
    linhas = []
    for i, t in enumerate(tempos):
        if i == 0:
            retencao = 100.0
            esvaziamento = 0.0
        else:
            retencao = retencao_percentual(t.mg_total, mg_t0, t.minutos, meia_vida_h)
            esvaziamento = 100.0 - retencao
        distribuicao = (t.mg_proximal / t.mg_total) * 100.0 if t.mg_total > 0 else 0.0
        ret_prox = retencao * distribuicao / 100.0
        linhas.append(
            LinhaResultado(
                rotulo=f"T{i}",
                minutos=t.minutos,
                mg_total=t.mg_total,
                mg_proximal=t.mg_proximal,
                mg_distal=t.mg_distal,
                distribuicao_proximal=distribuicao,
                esvaziamento=esvaziamento,
                retencao=retencao,
                retencao_proximal=ret_prox,
                retencao_distal=retencao - ret_prox,
            )
        )
    return linhas
