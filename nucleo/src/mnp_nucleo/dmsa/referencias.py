"""Fontes do método e faixa de normalidade da função renal relativa no DMSA.

Cada número usado aqui foi conferido no texto da fonte:

* Faixa normal 45–55%: Vali et al. 2022, p. 178 (seção de interpretação):
  a função de um rim em relação ao outro vai normalmente de 50–50% a
  45–55%. Mesmo limite inferior de 45% no consenso de Piepsz et al. 1999
  (resumo). A diretriz é pediátrica.
* Fundo: a diretriz manda subtrair o fundo medido perto do rim, fora do
  parênquima e de áreas de captação aumentada, sem definir forma nem
  tamanho da região (Vali 2022, p. 178). O anel perirrenal circunferencial
  segue Civan et al. 2022, em que só o fundo em volta do rim inteiro não
  diferiu do SPECT (resumo do artigo).
* Correção pelo tamanho: Estorch et al. 2004 (resumo do artigo).
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = [
    "Fonte",
    "VALI_2022",
    "CIVAN_2022",
    "FLEMING_1998",
    "GIROTTO_2008",
    "ESTORCH_2004",
    "PIEPSZ_1999",
    "LYTHGOE_1998",
    "BIBLIOGRAFIA",
    "FAIXA_NORMAL",
    "comparar_funcao",
]


@dataclass(frozen=True)
class Fonte:
    curta: str
    citacao: str
    doi: str | None


VALI_2022 = Fonte(
    "Vali et al., 2022",
    "Vali R, Armstrong IS, Bar-Sever Z, et al. SNMMI procedure standard/EANM practice guideline on pediatric "
    "[99mTc]Tc-DMSA renal cortical scintigraphy: an update. Clin Transl Imaging. 2022;10(2):173-84.",
    "10.1007/s40336-022-00484-x",
)
CIVAN_2022 = Fonte(
    "Civan et al., 2022",
    "Civan C, Has Simsek D, Kiran MY, Isik EG, Ozkan ZG, Sanli Y, Kuyumcu S. Comparison of 2D planar and 3D "
    "volumetric methods for estimation of split renal function by 99mTc-DMSA scintigraphy. Phys Med. 2022;95:83-8.",
    "10.1016/j.ejmp.2022.01.010",
)
FLEMING_1998 = Fonte(
    "Fleming et al., 1998",
    "Fleming JS, Cosgriff PS, Houston AS, Jarritt PH, Skrypniuk JV, Whalley DR. UK audit of relative renal "
    "function measurement using DMSA scintigraphy. Nucl Med Commun. 1998;19(10):989-97.",
    "10.1097/00006231-199810000-00009",
)
GIROTTO_2008 = Fonte(
    "Girotto et al., 2008",
    "Girotto N, Smokvina A, Grbac Ivanković S, Licul V. Effects of background substraction on differential "
    "kidney function measured by static scintigraphy with DMSA and dynamic scintigraphy with MAG 3. "
    "Nuklearmedizin. 2008;47(1):43-7. PMID 18278212.",
    None,
)
ESTORCH_2004 = Fonte(
    "Estorch et al., 2004",
    "Estorch M, Torres G, Camacho V, Tembl A, Prat L, Mena E, Flotats A, Carrió I. Individual renal function "
    "based on 99mTc dimercaptosuccinic acid uptake corrected for renal size. Nucl Med Commun. 2004;25(2):167-70.",
    "10.1097/00006231-200402000-00013",
)
PIEPSZ_1999 = Fonte(
    "Piepsz et al., 1999",
    "Piepsz A, Blaufox MD, Gordon I, et al. Consensus on renal cortical scintigraphy in children with urinary "
    "tract infection. Semin Nucl Med. 1999;29(2):160-74.",
    "10.1016/s0001-2998(99)80006-3",
)
LYTHGOE_1998 = Fonte(
    "Lythgoe et al., 1998",
    "Lythgoe MF, Gradwell MJ, Evans K, Gordon I. Estimation and relevance of depth correction in paediatric "
    "renal studies. Eur J Nucl Med. 1998;25(2):115-9.",
    "10.1007/s002590050202",
)

BIBLIOGRAFIA = (VALI_2022, CIVAN_2022, FLEMING_1998, GIROTTO_2008, ESTORCH_2004, PIEPSZ_1999, LYTHGOE_1998)

#: Faixa normal da função renal relativa de cada rim, em %, limites incluídos (Vali 2022).
FAIXA_NORMAL = (45.0, 55.0)
CRITERIO = "45,0% a 55,0% para cada rim (Vali et al., 2022; diretriz pediátrica)"


def comparar_funcao(percentual_arredondado: float) -> dict:
    """Compara a função relativa de um rim com a faixa normal.

    O valor comparado é o já arredondado a uma casa decimal (o mesmo que a
    tabela mostra), para que "45,0" nunca apareça como fora. Limites
    incluídos: dentro se 45,0 ≤ FRR ≤ 55,0. Como os dois rins somam 100%,
    os dois ficam sempre do mesmo lado do critério.
    """
    a, b = FAIXA_NORMAL
    return {"dentro": bool(a <= percentual_arredondado <= b), "criterio": CRITERIO}
