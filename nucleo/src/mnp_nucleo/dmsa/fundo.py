"""Região de fundo perirrenal (anel circunferencial em volta do rim inteiro).

Método: a diretriz SNMMI/EANM manda subtrair a atividade de fundo medida
perto do rim, fora do parênquima renal e de áreas de captação aumentada, sem
fixar forma nem tamanho da região (Vali et al., Clin Transl Imaging
2022;10:173-84, doi:10.1007/s40336-022-00484-x, p. 178). Entre as formas
comparadas por Civan et al. (Phys Med 2022;95:83-8,
doi:10.1016/j.ejmp.2022.01.010), só o fundo circunferencial, em volta do rim
inteiro, não diferiu da função relativa medida no SPECT; o crescente
ínfero-lateral e a ausência de fundo diferiram. Por isso a ferramenta usa o
anel em volta de todo o rim.

A largura do anel (4 pixels, contíguo ao rim) é escolha desta ferramenta: a
fonte consultada não informa a largura. Fica declarada no laudo e pode ser
substituída, rim a rim e vista a vista, por uma região desenhada à mão.
"""

from __future__ import annotations

import numpy as np

from ..comum.morfologia import dilatar_disco

__all__ = ["LARGURA_ANEL_PX", "anel_perirrenal"]

#: Largura do anel, em pixels (distância entre centros de pixel até a borda do rim).
LARGURA_ANEL_PX = 4


def anel_perirrenal(mascara_rim: np.ndarray, mascara_outro_rim: np.ndarray, largura: float = LARGURA_ANEL_PX) -> np.ndarray:
    """Anel de fundo em volta do rim inteiro.

    anel = dilatação(rim, disco de raio ``largura``) − rim − outro rim

    Um pixel fora do rim entra no anel quando o centro dele fica a até
    ``largura`` pixels do centro de algum pixel do rim. Pixels da ROI do
    outro rim nunca entram (o anel não invade o outro rim). O anel termina na
    borda da imagem.
    """
    rim = np.asarray(mascara_rim, dtype=bool)
    outro = np.asarray(mascara_outro_rim, dtype=bool)
    if rim.shape != outro.shape:
        raise ValueError("Máscaras dos rins com dimensões diferentes.")
    return dilatar_disco(rim, largura) & ~rim & ~outro
