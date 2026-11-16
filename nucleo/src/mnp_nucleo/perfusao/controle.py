"""Controle de qualidade das projeções: cine, sinograma, linograma e curvas de contagens.

* Sinograma de uma linha r: imagem (ângulos × colunas) com a linha r de
  cada projeção, em ordem de ângulo. Movimento lateral aparece como
  degrau ou quebra na curva do coração.
* Linograma: imagem (linhas × ângulos), soma de cada linha da projeção.
  Movimento vertical (craniocaudal) aparece como degrau horizontal.
* Contagens por projeção e, no gated, contagens por intervalo do ciclo
  (soma de todas as projeções daquele intervalo). Queda nos últimos
  intervalos sugere arritmia ou rejeição de batimentos inadequada; a
  diretriz SBC 2020 (p. 338) descreve a janela de aceitação dos
  intervalos R-R, em geral em torno de 20%.

Referência para movimento: deslocamento de 2 pixels ou mais costuma
causar artefato clinicamente importante (Germano, J Nucl Med
2001;42:1499-507, citando Matsumoto et al. 2001). A ferramenta só mostra:
quem julga é o médico.
"""

from __future__ import annotations

import numpy as np

from .aquisicao import Aquisicao

__all__ = ["sinograma", "linograma", "contagens_por_projecao", "contagens_por_intervalo", "linha_do_coracao"]


def sinograma(aq: Aquisicao, linha: int) -> np.ndarray:
    """(ângulos, colunas): a linha ``linha`` de cada projeção (soma dos intervalos)."""
    linha = int(np.clip(linha, 0, aq.linhas - 1))
    return aq.somadas()[:, linha, :]


def linograma(aq: Aquisicao) -> np.ndarray:
    """(linhas, ângulos): soma de cada linha de cada projeção."""
    return aq.somadas().sum(axis=2).T


def contagens_por_projecao(aq: Aquisicao) -> np.ndarray:
    return aq.somadas().sum(axis=(1, 2))


def contagens_por_intervalo(aq: Aquisicao) -> dict:
    """Contagens totais de cada intervalo do gated e em % da média dos intervalos."""
    tot = aq.projecoes.sum(axis=(1, 2, 3))
    media = float(tot.mean()) if tot.size else 0.0
    return {
        "contagens": [float(x) for x in tot],
        "percentual_da_media": [100.0 * float(x) / media if media else 0.0 for x in tot],
    }


def linha_do_coracao(aq: Aquisicao) -> int:
    """Linha inicial sugerida para o sinograma: a do meio, porque a aquisição cardíaca é centrada no coração.

    A linha de maior contagem costuma ser a do fígado ou das alças. O
    usuário escolhe a linha clicando na projeção.
    """
    return aq.linhas // 2
