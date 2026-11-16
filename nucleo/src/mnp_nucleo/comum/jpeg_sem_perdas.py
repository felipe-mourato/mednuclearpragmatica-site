"""Decodificador de JPEG sem perdas (processo 14), em Python puro + NumPy.

Muitas estações de medicina nuclear (ex.: Siemens) exportam o DICOM com a
sintaxe "JPEG Lossless, Non-Hierarchical, First-Order Prediction (Process
14 [Selection Value 1])" (1.2.840.10008.1.2.4.70) ou "JPEG Lossless,
Non-Hierarchical (Process 14)" (1.2.840.10008.1.2.4.57). Os
decodificadores prontos (pylibjpeg-libjpeg, GDCM) são compilados e não
estão garantidos no navegador; este módulo cobre esse caso sem
dependências, seguindo a norma ITU-T T.81 (ISO/IEC 10918-1), anexo H
(modo sem perdas) e anexo C/F (códigos de Huffman).

Escopo: um componente (escala de cinza), precisão de 2 a 16 bits,
preditores 1 a 7, transformação de ponto (Pt) e intervalos de reinício
alinhados ao começo das linhas. Fora disso, :class:`ErroJpeg`.

Reconstrução (T.81, H.1.2.1): cada amostra = predição + diferença, módulo
2^P. Predição: primeira amostra da imagem (e de cada intervalo de
reinício) = 2^(P − Pt − 1); resto da primeira linha = Ra (vizinho à
esquerda); primeira coluna das demais linhas = Rb (vizinho de cima); demais
amostras pelo preditor Ss: 1 Ra, 2 Rb, 3 Rc, 4 Ra+Rb−Rc, 5 Ra+((Rb−Rc)>>1),
6 Rb+((Ra−Rc)>>1), 7 (Ra+Rb)>>1.
"""

from __future__ import annotations

import numpy as np

__all__ = ["ErroJpeg", "decodificar_jpeg_sem_perdas", "SINTAXES_JPEG_SEM_PERDAS"]

#: UIDs de sintaxe de transferência que este módulo decodifica.
SINTAXES_JPEG_SEM_PERDAS = ("1.2.840.10008.1.2.4.57", "1.2.840.10008.1.2.4.70")


class ErroJpeg(ValueError):
    """Fluxo JPEG fora do escopo ou corrompido (mensagem para o usuário)."""


def _u16(dados: bytes, i: int) -> int:
    return (dados[i] << 8) | dados[i + 1]


def _tabela_huffman(contagens: list[int], valores: list[int]) -> list:
    """Tabela de consulta de 16 bits: índice = próximos 16 bits; valor = (símbolo, comprimento).

    Códigos gerados como em T.81, anexo C (figuras C.1 a C.3): em ordem de
    comprimento, o código aumenta de 1 a cada símbolo e dobra ao passar
    para o comprimento seguinte.
    """
    tabela: list = [None] * 65536
    codigo = 0
    k = 0
    for comprimento in range(1, 17):
        for _ in range(contagens[comprimento - 1]):
            if k >= len(valores):
                raise ErroJpeg("Tabela de Huffman inválida no JPEG.")
            inicio = codigo << (16 - comprimento)
            n = 1 << (16 - comprimento)
            if inicio + n > 65536:
                raise ErroJpeg("Tabela de Huffman inválida no JPEG.")
            tabela[inicio : inicio + n] = [(valores[k], comprimento)] * n
            codigo += 1
            k += 1
        codigo <<= 1
    return tabela


def _limpar_entropia(segmento: bytes) -> bytes:
    """Remove o enchimento de bytes (0xFF 0x00 → 0xFF) de um trecho codificado."""
    return segmento.replace(b"\xff\x00", b"\xff")


def _diferencas(dados: bytes, tabela: list, n: int) -> np.ndarray:
    """Decodifica ``n`` diferenças de um trecho sem marcadores (já sem enchimento)."""
    buf = dados + b"\x00\x00\x00\x00\x00"
    saida = np.empty(n, dtype=np.int64)
    pos = 0  # posição em bits
    de_bytes = int.from_bytes
    for i in range(n):
        b = pos >> 3
        janela = (de_bytes(buf[b : b + 4], "big") >> (16 - (pos & 7))) & 0xFFFF
        entrada = tabela[janela]
        if entrada is None:
            raise ErroJpeg("Código de Huffman inválido: dados JPEG corrompidos.")
        t, comprimento = entrada
        pos += comprimento
        if t == 0:
            saida[i] = 0
        elif t == 16:
            saida[i] = 32768
        else:
            b = pos >> 3
            v = (de_bytes(buf[b : b + 4], "big") >> (32 - t - (pos & 7))) & ((1 << t) - 1)
            pos += t
            saida[i] = v if v >= (1 << (t - 1)) else v - (1 << t) + 1
    if (pos + 7) >> 3 > len(dados) + 1:
        raise ErroJpeg("Dados JPEG incompletos (o fluxo terminou antes do fim da imagem).")
    return saida


def _reconstruir(dif: np.ndarray, linhas: int, colunas: int, precisao: int, pt: int, preditor: int, inicio_linhas) -> np.ndarray:
    modulo = 1 << precisao
    d = dif.reshape(linhas, colunas)
    x = np.zeros((linhas, colunas), dtype=np.int64)
    padrao = 1 << (precisao - pt - 1)
    for r in range(linhas):
        primeira = r in inicio_linhas
        if primeira:
            x[r, 0] = (padrao + d[r, 0]) % modulo
        else:
            x[r, 0] = (x[r - 1, 0] + d[r, 0]) % modulo
        if primeira or preditor == 1:
            x[r, 1:] = (x[r, 0] + np.cumsum(d[r, 1:])) % modulo
            continue
        for c in range(1, colunas):
            ra, rb, rc = int(x[r, c - 1]), int(x[r - 1, c]), int(x[r - 1, c - 1])
            if preditor == 2:
                p = rb
            elif preditor == 3:
                p = rc
            elif preditor == 4:
                p = ra + rb - rc
            elif preditor == 5:
                p = ra + ((rb - rc) >> 1)
            elif preditor == 6:
                p = rb + ((ra - rc) >> 1)
            else:
                p = (ra + rb) >> 1
            x[r, c] = (p + d[r, c]) % modulo
    return x << pt


def decodificar_jpeg_sem_perdas(dados: bytes) -> np.ndarray:
    """Decodifica um quadro JPEG sem perdas e devolve um array (linhas, colunas) int64.

    Raises
    ------
    ErroJpeg
        Formato fora do escopo (mais de um componente, processo diferente
        do 14, reinício no meio da linha) ou dados corrompidos.
    """
    dados = bytes(dados)
    if len(dados) < 4 or dados[0] != 0xFF or dados[1] != 0xD8:
        raise ErroJpeg("Quadro JPEG sem o marcador inicial (SOI).")
    tabelas: dict[int, list] = {}
    reinicio = 0
    linhas = colunas = precisao = None
    i = 2
    while i < len(dados) - 1:
        if dados[i] != 0xFF:
            raise ErroJpeg("Estrutura JPEG inválida (marcador esperado).")
        marcador = dados[i + 1]
        if marcador == 0xFF:
            i += 1
            continue
        if marcador == 0xD9:
            break
        comprimento = _u16(dados, i + 2)
        corpo = dados[i + 4 : i + 2 + comprimento]
        if marcador == 0xC4:  # DHT
            j = 0
            while j < len(corpo):
                tc_th = corpo[j]
                contagens = list(corpo[j + 1 : j + 17])
                total = sum(contagens)
                valores = list(corpo[j + 17 : j + 17 + total])
                tabelas[tc_th & 0x0F] = _tabela_huffman(contagens, valores)
                j += 17 + total
        elif marcador == 0xC3:  # SOF3: sem perdas, Huffman
            precisao = corpo[0]
            linhas = _u16(corpo, 1)
            colunas = _u16(corpo, 3)
            if corpo[5] != 1:
                raise ErroJpeg("JPEG com mais de um componente (imagem colorida) não suportado.")
            if not 2 <= precisao <= 16:
                raise ErroJpeg(f"Precisão JPEG não suportada ({precisao} bits).")
        elif marcador in (0xC0, 0xC1, 0xC2, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
            raise ErroJpeg("JPEG com perdas ou aritmético: só o JPEG sem perdas (processo 14) é suportado.")
        elif marcador == 0xDD:  # DRI
            reinicio = _u16(corpo, 0)
        elif marcador == 0xDA:  # SOS
            if linhas is None:
                raise ErroJpeg("JPEG sem cabeçalho de quadro (SOF3) antes dos dados.")
            ns = corpo[0]
            if ns != 1:
                raise ErroJpeg("JPEG com vários componentes por varredura não suportado.")
            td = corpo[2] >> 4
            preditor = corpo[3]
            pt = corpo[5] & 0x0F
            if not 1 <= preditor <= 7:
                raise ErroJpeg(f"Preditor JPEG não suportado ({preditor}).")
            if td not in tabelas:
                raise ErroJpeg("Tabela de Huffman ausente no JPEG.")
            inicio = i + 2 + comprimento
            # Dados codificados até o próximo marcador que não seja enchimento nem RST.
            fim = inicio
            trechos = []
            ultimo = inicio
            while fim < len(dados) - 1:
                if dados[fim] == 0xFF and dados[fim + 1] != 0x00:
                    if 0xD0 <= dados[fim + 1] <= 0xD7:
                        trechos.append(dados[ultimo:fim])
                        fim += 2
                        ultimo = fim
                        continue
                    if dados[fim + 1] == 0xFF:
                        fim += 1
                        continue
                    break
                fim += 1
            trechos.append(dados[ultimo:fim])
            n_total = linhas * colunas
            if reinicio and len(trechos) > 1:
                if reinicio % colunas:
                    raise ErroJpeg("JPEG com reinício no meio da linha não suportado.")
                por_trecho = reinicio
            else:
                por_trecho = n_total
                trechos = [b"".join(trechos)]
            partes = []
            restante = n_total
            for t in trechos:
                n = min(por_trecho, restante)
                if n <= 0:
                    break
                partes.append(_diferencas(_limpar_entropia(t), tabelas[td], n))
                restante -= n
            if restante:
                raise ErroJpeg("Dados JPEG incompletos (faltam amostras).")
            dif = np.concatenate(partes)
            linhas_reinicio = set(range(0, linhas, por_trecho // colunas)) if por_trecho < n_total else {0}
            return _reconstruir(dif, linhas, colunas, precisao, pt, preditor, linhas_reinicio)
        i += 2 + comprimento
    raise ErroJpeg("JPEG sem dados de imagem (SOS ausente).")
