"""Codificador PNG mínimo (biblioteca padrão), para as figuras do laudo.

Gera PNG RGBA de 8 bits sem entrelaçamento. Determinístico: os mesmos
pixels geram sempre os mesmos bytes, no navegador e no computador.
"""

from __future__ import annotations

import struct
import zlib

import numpy as np

__all__ = ["codificar_png"]

_ASSINATURA = b"\x89PNG\r\n\x1a\n"


def _bloco(tipo: bytes, dados: bytes) -> bytes:
    crc = zlib.crc32(tipo + dados) & 0xFFFFFFFF
    return struct.pack(">I", len(dados)) + tipo + dados + struct.pack(">I", crc)


def codificar_png(rgba: np.ndarray) -> bytes:
    """PNG a partir de um array (linhas, colunas, 4) uint8."""
    a = np.ascontiguousarray(np.asarray(rgba, dtype=np.uint8))
    if a.ndim != 3 or a.shape[2] != 4:
        raise ValueError("Esperado array RGBA (linhas, colunas, 4).")
    altura, largura = a.shape[:2]
    cabecalho = struct.pack(">IIBBBBB", largura, altura, 8, 6, 0, 0, 0)
    # Filtro 0 (nenhum) em todas as linhas.
    cru = np.concatenate([np.zeros((altura, 1), dtype=np.uint8), a.reshape(altura, largura * 4)], axis=1)
    return (
        _ASSINATURA
        + _bloco(b"IHDR", cabecalho)
        + _bloco(b"IDAT", zlib.compress(cru.tobytes(), 6))
        + _bloco(b"IEND", b"")
    )
