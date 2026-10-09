"""Valores de referência do esvaziamento gástrico, por faixa etária e refeição.

Cada referência dá, para um tempo nominal (min), a faixa de RETENÇÃO total
considerada normal no protocolo publicado. A comparação só é feita quando o
tempo decorrido do exame está a até ``TOLERANCIA_MIN`` minutos do nominal.

A ferramenta compara e mostra; a interpretação é do médico nuclear.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Referencia",
    "Faixa",
    "REFERENCIAS",
    "TOLERANCIA_MIN",
    "obter",
    "comparar",
    "MEDIANAS_PDCR_SILVER_2022",
]

#: Distância máxima (min) entre o tempo do exame e o tempo de referência.
TOLERANCIA_MIN = 15.0


@dataclass(frozen=True)
class Faixa:
    """Faixa normal de retenção (%) num tempo nominal.

    ``minimo``/``maximo``: limites da retenção normal; ``None`` = sem limite.
    ``inclusivo``: se o próprio limite conta como normal.
    ``texto``: como o artigo expressa o critério.
    """

    minutos: float
    minimo: float | None
    maximo: float | None
    inclusivo: bool
    texto: str


@dataclass(frozen=True)
class Referencia:
    chave: str
    grupo: str
    refeicao: str
    fonte: str
    doi: str
    faixas: tuple[Faixa, ...]
    nota: str


REFERENCIAS = {
    # Tougas 2000: percentil 95 da retenção em 123 voluntários saudáveis,
    # refeição de baixo teor de gordura (substituto de ovo). Retenção acima
    # do p95 sugere esvaziamento lento.
    "adulto": Referencia(
        chave="adulto",
        grupo="Adulto",
        refeicao="Refeição padronizada de clara de ovo (substituto de ovo), 4 h",
        fonte="Tougas G et al. Am J Gastroenterol. 2000;95:1456-62",
        doi="10.1111/j.1572-0241.2000.02076.x",
        faixas=(
            Faixa(60, None, 90.0, True, "retenção ≤ 90% (p95; mediana 69%)"),
            Faixa(120, None, 60.0, True, "retenção ≤ 60% (p95; mediana 24%)"),
            Faixa(240, None, 10.0, True, "retenção ≤ 10% (p95; mediana 1,2%)"),
        ),
        nota="Percentil 95 da retenção em 123 voluntários saudáveis de 11 centros.",
    ),
    # MacLean & El-Chammas 2024, Tabela 2: valores adotados pelo Cincinnati
    # Children's Hospital, expressos como esvaziamento. Convertidos para
    # retenção (R = 100 − E) sem mudar os limites.
    "pediatrico_ovo": Referencia(
        chave="pediatrico_ovo",
        grupo="Pediátrico",
        refeicao="Clara de ovo ou Ensure Plus, estudo de 4 h",
        fonte="MacLean J, El-Chammas K. J Nucl Med Technol. 2024;52:40-5 (Tabela 2)",
        doi="10.2967/jnmt.123.266857",
        faixas=(
            Faixa(60, 30.0, 90.0, False, "esvaziamento > 10% e < 70%"),
            Faixa(120, None, 60.0, False, "esvaziamento > 40%"),
            Faixa(240, None, 10.0, False, "esvaziamento > 90%"),
        ),
        nota=(
            "Valores de referência adotados pelo Cincinnati Children's Hospital, que em 2017 passou a usar "
            "nos estudos pediátricos os padrões do adulto (refeição padronizada e imagens por 4 h)."
        ),
    ),
    "pediatrico_aveia": Referencia(
        chave="pediatrico_aveia",
        grupo="Pediátrico",
        refeicao="Aveia, estudo de 1 h",
        fonte="MacLean J, El-Chammas K. J Nucl Med Technol. 2024;52:40-5 (Tabela 2)",
        doi="10.2967/jnmt.123.266857",
        faixas=(Faixa(60, None, 50.0, False, "esvaziamento > 50%"),),
        nota="Estudo de 1 h com aveia, para quem não come ovo nem toma Ensure Plus.",
    ),
}

#: Medianas da razão proximal/distal (PDCR) em Silver 2022 (Tabela 3).
#: Não são limites de normalidade: o artigo divide os pacientes pela mediana.
#: Em 4 h, a maioria dos controles tinha < 5% de retenção (não avaliável).
MEDIANAS_PDCR_SILVER_2022 = (
    {"grupo": "Controles assintomáticos (n = 21)", "valores": {0: 3.81, 60: 1.11, 120: 0.73, 240: None}},
    {"grupo": "Sintomáticos, esvaziamento normal (n = 93)", "valores": {0: 2.65, 60: 1.43, 120: 0.77, 240: None}},
    {"grupo": "Sintomáticos, esvaziamento lento (n = 100)", "valores": {0: 3.54, 60: 1.52, 120: 0.94, 240: 0.48}},
)


def obter(faixa_etaria: str | None, refeicao: str | None = None) -> Referencia | None:
    """Referência para a faixa etária ("adulto" ou "pediatrico") e, no pediátrico, a refeição ("ovo" ou "aveia")."""
    if faixa_etaria == "adulto":
        return REFERENCIAS["adulto"]
    if faixa_etaria == "pediatrico":
        return REFERENCIAS["pediatrico_aveia" if refeicao == "aveia" else "pediatrico_ovo"]
    return None


def _dentro(f: Faixa, retencao: float) -> bool:
    if f.minimo is not None and (retencao < f.minimo or (not f.inclusivo and retencao == f.minimo)):
        return False
    if f.maximo is not None and (retencao > f.maximo or (not f.inclusivo and retencao == f.maximo)):
        return False
    return True


def comparar(ref: Referencia | None, minutos: float, retencao: float) -> dict | None:
    """Compara a retenção de um tempo com a faixa de referência mais próxima.

    Devolve ``None`` se não houver referência ou se nenhum tempo nominal
    estiver a até ``TOLERANCIA_MIN`` minutos. Senão, devolve o texto do
    critério e ``dentro`` (True/False).
    """
    if ref is None:
        return None
    candidatas = [f for f in ref.faixas if abs(f.minutos - minutos) <= TOLERANCIA_MIN]
    if not candidatas:
        return None
    f = min(candidatas, key=lambda x: abs(x.minutos - minutos))
    return {"minutos_ref": f.minutos, "criterio": f.texto, "dentro": _dentro(f, retencao)}
