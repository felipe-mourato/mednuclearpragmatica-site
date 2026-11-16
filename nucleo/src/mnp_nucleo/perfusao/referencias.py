"""Fontes do método da ferramenta de perfusão miocárdica.

Cada número usado foi conferido no texto (PDFs enviados pelo Mourato em
16 nov 2026):

* Escala de 0 a 4 por segmento: SBC 2020, p. 346 ("0 = normal; 1 = tênue
  ou discreta hipocaptação; 2 = moderada; 3 = acentuada; 4 = ausência de
  captação"); mesma escala na figura do Apêndice 6 da ASNC 2017.
* 17 segmentos, nomes e territórios: ASNC 2017, Apêndice 6 (figura
  adaptada de Cerqueira et al.); SBC 2020, Tabela 18.
* SSS, SRS, SDS = SSS − SRS e percentual = escore ÷ 68; nenhum segmento
  com escore negativo: ASNC 2017, texto (p. 2078) e Tabela 12.
* Faixas do SSS (< 4; 4–8; 9–13; > 13): SBC 2020, p. 347, citando
  Hachamovitch et al.
* Butterworth B(f) = 1/(1 + (f/fc)^(2n)), aplicado às projeções antes da
  reconstrução, e as duas convenções de unidade do corte: Germano 2001,
  p. 1503; Lyra e Ploussi 2011, eq. 2.
* Padrão inicial (ordem 11, corte 0,45 Nyquist): Lyra e Ploussi 2011,
  seção 4.1, citando Takavar et al. 2004 (fantoma de VE com ⁹⁹ᵐTc).
* Reorientação manual em duas etapas: Germano 2001, p. 1504 e figura 10.
* Movimento ≥ 2 pixels: Germano 2001, p. 1506.
* Janela R-R em torno de 20%: SBC 2020, p. 338.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["Fonte", "BIBLIOGRAFIA", "SBC_2020", "ASNC_2017", "GERMANO_2001", "LYRA_2011", "CERQUEIRA_2002", "GERMANO_2000", "KAK_1988"]


@dataclass(frozen=True)
class Fonte:
    curta: str
    citacao: str
    doi: str | None


SBC_2020 = Fonte(
    "SBC 2020",
    "Mastrocola LE, Amorim BJ, Vitola JV, et al. Atualização da Diretriz Brasileira de Cardiologia Nuclear – 2020. "
    "Arq Bras Cardiol. 2020;114(2):325-429.",
    "10.36660/abc.20200087",
)
ASNC_2017 = Fonte(
    "ASNC 2017",
    "Tilkemeier PL, Bourque J, Doukky R, Sanghani R, Weinberg RL. ASNC imaging guidelines for nuclear cardiology "
    "procedures: standardized reporting of nuclear cardiology procedures. J Nucl Cardiol. 2017;24(6):2064-128.",
    "10.1007/s12350-017-1057-y",
)
CERQUEIRA_2002 = Fonte(
    "Cerqueira et al., 2002",
    "Cerqueira MD, Weissman NJ, Dilsizian V, et al. Standardized myocardial segmentation and nomenclature for "
    "tomographic imaging of the heart. J Nucl Cardiol. 2002;9(2):240-5 (figura reproduzida na ASNC 2017, Apêndice 6).",
    "10.1067/mnc.2002.123122",
)
GERMANO_2001 = Fonte(
    "Germano, 2001",
    "Germano G. Technical aspects of myocardial SPECT imaging. J Nucl Med. 2001;42(10):1499-507.",
    None,
)
LYRA_2011 = Fonte(
    "Lyra e Ploussi, 2011",
    "Lyra M, Ploussi A. Filtering in SPECT image reconstruction. Int J Biomed Imaging. 2011;2011:693795.",
    "10.1155/2011/693795",
)
GERMANO_2000 = Fonte(
    "Germano et al., 2000",
    "Germano G, Kavanagh PB, Waechter P, et al. A new algorithm for the quantitation of myocardial perfusion SPECT. "
    "I: technical principles and reproducibility. J Nucl Med. 2000;41(4):712-9 (método de referência, ainda não "
    "implementado nesta versão).",
    None,
)
KAK_1988 = Fonte(
    "Kak e Slaney, 1988",
    "Kak AC, Slaney M. Principles of Computerized Tomographic Imaging. New York: IEEE Press; 1988. Cap. 3.",
    None,
)

BIBLIOGRAFIA = (SBC_2020, ASNC_2017, CERQUEIRA_2002, GERMANO_2001, LYRA_2011, KAK_1988, GERMANO_2000)
