"""Leitura de arquivos DICOM de medicina nuclear (pydicom + NumPy).

Escopo: DICOM não comprimido (sintaxes de transferência nativas), imagem
monocromática (1 amostra por pixel), 8, 16 ou 32 bits, com ou sem sinal,
quadro único ou multiframe. Arquivos comprimidos e outros casos fora do
escopo geram :class:`ErroDicom` com mensagem em português para o usuário.

Os dados de identificação do paciente (nome, nascimento, prontuário) não são
lidos nem guardados: só a geometria, os pixels, os horários e a descrição
da série.
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pydicom
from pydicom.errors import InvalidDicomError

__all__ = [
    "ErroDicom",
    "ImagemDicom",
    "ler_dicom",
    "interpretar_hora",
    "interpretar_data",
    "combinar_data_hora",
    "adivinhar_vista",
    "como_bytes",
]

# Ordem de procura do horário de aquisição (atributo, tag).
TAGS_HORA = (
    ("AcquisitionTime", "(0008,0032)"),
    ("ContentTime", "(0008,0033)"),
    ("SeriesTime", "(0008,0031)"),
    ("StudyTime", "(0008,0030)"),
)
# Ordem de procura da data, para não errar na virada da meia-noite.
TAGS_DATA = (
    ("AcquisitionDate", "(0008,0022)"),
    ("SeriesDate", "(0008,0021)"),
    ("ContentDate", "(0008,0023)"),
    ("StudyDate", "(0008,0020)"),
)
# Data usada quando o arquivo tem horário, mas nenhuma data.
DATA_BASE = (2000, 1, 1)


class ErroDicom(ValueError):
    """Erro de leitura com mensagem pronta para mostrar ao usuário."""


@dataclass
class ImagemDicom:
    """Imagem lida de um arquivo DICOM, com rescale já aplicado.

    Atributos
    ---------
    quadros : ndarray float64, forma (n_quadros, linhas, colunas)
        Valores dos pixels de todos os quadros, já com
        ``valor = bruto × RescaleSlope + RescaleIntercept``.
    """

    linhas: int
    colunas: int
    bits_alocados: int
    representacao_pixel: int
    quadros: np.ndarray
    inclinacao: float
    intercepto: float
    hora_bruta: str | None
    data_bruta: str | None
    tag_hora: str | None
    data_hora: datetime | None
    descricao: str | None
    sintaxe: str
    sha256: str
    avisos: list[str] = field(default_factory=list)

    @property
    def n_quadros(self) -> int:
        return int(self.quadros.shape[0])

    @property
    def multiframe(self) -> bool:
        return self.n_quadros > 1

    @property
    def horario_encontrado(self) -> bool:
        return self.data_hora is not None

    def quadro(self, indice: int) -> np.ndarray:
        """Pixels de um quadro (índice a partir de 0), limitado ao intervalo válido."""
        i = min(max(0, int(indice)), self.n_quadros - 1)
        return self.quadros[i]

    def contagem_total(self, indice: int = 0) -> float:
        """Soma dos valores (com rescale) de um quadro."""
        return float(self.quadro(indice).sum())


def como_bytes(dados) -> bytes:
    """Converte o conteúdo recebido em ``bytes``.

    Aceita ``bytes``, ``bytearray``, ``memoryview`` e o objeto que o Pyodide
    entrega para um ``Uint8Array`` do JavaScript (que tem ``to_bytes()``).
    """
    if isinstance(dados, bytes):
        return dados
    if hasattr(dados, "to_bytes") and not isinstance(dados, int):
        return dados.to_bytes()
    return bytes(dados)


def interpretar_hora(tm: str | None) -> tuple[int, int, int] | None:
    """Interpreta um valor DICOM TM (``HHMMSS.FFFFFF``, que pode vir parcial).

    Aceita ``HH``, ``HHMM``, ``HHMMSS`` e frações; aceita também o formato
    antigo com dois-pontos (``HH:MM:SS``). Retorna ``(h, m, s)`` ou ``None``.
    """
    if not tm:
        return None
    limpo = str(tm).strip().replace(":", "")
    limpo = re.sub(r"\.\d*$", "", limpo)
    if not re.fullmatch(r"\d{2}(\d{2})?(\d{2})?", limpo):
        return None
    h = int(limpo[0:2])
    m = int(limpo[2:4]) if len(limpo) >= 4 else 0
    s = int(limpo[4:6]) if len(limpo) >= 6 else 0
    if h > 23 or m > 59 or s > 59:
        return None
    return h, m, s


def interpretar_data(da: str | None) -> tuple[int, int, int] | None:
    """Interpreta um valor DICOM DA (``AAAAMMDD``). Retorna ``(a, m, d)`` ou ``None``."""
    if not da:
        return None
    limpo = str(da).strip().replace(".", "").replace("-", "")
    if not re.fullmatch(r"\d{8}", limpo):
        return None
    a, m, d = int(limpo[0:4]), int(limpo[4:6]), int(limpo[6:8])
    try:
        datetime(a, m, d)
    except ValueError:
        return None
    return a, m, d


def combinar_data_hora(da: str | None, tm: str | None) -> datetime | None:
    """Combina data e hora DICOM. Sem data válida, usa 1 jan 2000 como base."""
    hora = interpretar_hora(tm)
    if hora is None:
        return None
    data = interpretar_data(da) or DATA_BASE
    return datetime(*data, *hora)


def _primeiro_texto(ds, tags) -> tuple[str | None, str | None]:
    for atributo, rotulo in tags:
        valor = ds.get(atributo, None)
        if valor is None:
            continue
        texto = str(valor).strip()
        if texto:
            return texto, rotulo
    return None, None


def _numero(ds, atributo: str, padrao: float) -> float:
    valor = ds.get(atributo, None)
    if valor is None or str(valor).strip() == "":
        return padrao
    try:
        return float(valor)
    except (TypeError, ValueError):
        return padrao


def adivinhar_vista(descricao: str | None) -> str:
    """Sugere a vista ("anterior" ou "posterior") pela descrição da série.

    Procura "post", "pos" ou "pós" no texto. Se o texto citar as duas vistas
    (ex.: "ANT/POST", típico de arquivo multiframe), devolve "anterior" e a
    interface oferece usar os quadros 1 e 2 como ANT e PÓS. Sem pista,
    devolve "anterior". O usuário sempre pode corrigir.
    """
    texto = (descricao or "").lower()
    tem_post = re.search(r"post|p[oó]s", texto) is not None
    tem_ant = re.search(r"\bant", texto) is not None
    if tem_post and not tem_ant:
        return "posterior"
    return "anterior"


def _abrir(dados: bytes):
    try:
        return pydicom.dcmread(io.BytesIO(dados))
    except InvalidDicomError:
        pass
    except Exception as erro:  # noqa: BLE001 - qualquer falha vira mensagem amigável
        raise ErroDicom(
            "Arquivo não é um DICOM válido (não foi possível interpretar o cabeçalho)."
        ) from erro
    # Arquivos antigos de medicina nuclear às vezes vêm sem o preâmbulo "DICM".
    try:
        ds = pydicom.dcmread(io.BytesIO(dados), force=True)
    except Exception as erro:  # noqa: BLE001
        raise ErroDicom(
            "Arquivo não é um DICOM válido (não foi possível interpretar o cabeçalho)."
        ) from erro
    if "Rows" not in ds or "Columns" not in ds:
        raise ErroDicom("Arquivo não é um DICOM válido (não foi possível interpretar o cabeçalho).")
    return ds


def ler_dicom(dados) -> ImagemDicom:
    """Lê um arquivo DICOM não comprimido e devolve uma :class:`ImagemDicom`.

    Pixels: lidos pelo pydicom e convertidos para float64 com a transformação
    de modalidade linear do padrão DICOM (PS3.3, C.11.1)::

        valor = bruto × RescaleSlope (0028,1053) + RescaleIntercept (0028,1052)

    (inclinação 1 e intercepto 0 quando ausentes). Multiframe: o número de
    quadros vem de NumberOfFrames (0028,0008).

    Horário: AcquisitionTime (0008,0032), depois ContentTime (0008,0033),
    SeriesTime (0008,0031) e StudyTime (0008,0030), combinado com a primeira
    data presente entre AcquisitionDate (0008,0022), SeriesDate (0008,0021),
    ContentDate (0008,0023) e StudyDate (0008,0020).

    Raises
    ------
    ErroDicom
        Arquivo não DICOM, comprimido, sem pixels, colorido ou com profundidade
        de bits fora do escopo. A mensagem é para o usuário final.
    """
    dados = como_bytes(dados)
    if len(dados) < 132:
        raise ErroDicom("Arquivo pequeno demais para ser um DICOM.")
    ds = _abrir(dados)

    meta = getattr(ds, "file_meta", None)
    sintaxe_uid = getattr(meta, "TransferSyntaxUID", None) if meta is not None else None
    if sintaxe_uid is not None and sintaxe_uid.is_compressed:
        raise ErroDicom(
            f"DICOM comprimido não suportado ({sintaxe_uid.name}). Exporte as imagens sem "
            "compressão (Explicit ou Implicit VR Little Endian) na estação de trabalho."
        )
    sintaxe = sintaxe_uid.name if sintaxe_uid is not None else "não informada (lida como Implicit VR Little Endian)"

    linhas = int(ds.get("Rows", 0) or 0)
    colunas = int(ds.get("Columns", 0) or 0)
    if linhas <= 0 or colunas <= 0:
        raise ErroDicom("DICOM sem dimensões de imagem válidas (Rows/Columns ausentes).")
    if "PixelData" not in ds:
        if "FloatPixelData" in ds or "DoubleFloatPixelData" in ds:
            raise ErroDicom("DICOM com pixels em ponto flutuante não suportado nesta versão.")
        raise ErroDicom("DICOM sem dados de pixel (elemento 7FE0,0010 ausente).")
    amostras = int(ds.get("SamplesPerPixel", 1) or 1)
    if amostras != 1:
        raise ErroDicom(
            "Imagem colorida (provavelmente uma captura de tela). Use o DICOM original da "
            "gama-câmara, em escala de cinza."
        )
    bits = int(ds.get("BitsAllocated", 16) or 16)
    if bits not in (8, 16, 32):
        raise ErroDicom(
            f"Profundidade de bits não suportada (BitsAllocated={bits}). Use imagens de 8, 16 ou 32 bits."
        )
    representacao = int(ds.get("PixelRepresentation", 0) or 0)

    try:
        brutos = ds.pixel_array
    except Exception as erro:  # noqa: BLE001
        raise ErroDicom(
            "Não foi possível ler os pixels: os dados de imagem estão incompletos ou em formato "
            "não suportado."
        ) from erro
    brutos = np.asarray(brutos)
    if brutos.ndim == 2:
        brutos = brutos[np.newaxis, :, :]
    if brutos.ndim != 3 or brutos.shape[1:] != (linhas, colunas):
        raise ErroDicom("Dados de pixel com dimensões diferentes das declaradas no cabeçalho.")

    inclinacao = _numero(ds, "RescaleSlope", 1.0)
    intercepto = _numero(ds, "RescaleIntercept", 0.0)
    quadros = brutos.astype(np.float64) * inclinacao + intercepto

    hora_bruta, tag_hora = _primeiro_texto(ds, TAGS_HORA)
    data_bruta, _ = _primeiro_texto(ds, TAGS_DATA)
    data_hora = combinar_data_hora(data_bruta, hora_bruta)
    descricao, _ = _primeiro_texto(
        ds, (("SeriesDescription", "(0008,103E)"), ("ImageComments", "(0020,4000)"))
    )

    avisos = []
    if hora_bruta is not None and data_hora is None:
        avisos.append(f"Horário em formato não reconhecido: {hora_bruta!r}.")
    if str(ds.get("PhotometricInterpretation", "MONOCHROME2")).strip() == "MONOCHROME1":
        avisos.append("Imagem MONOCHROME1: a exibição pode aparecer invertida; as contagens não mudam.")

    return ImagemDicom(
        linhas=linhas,
        colunas=colunas,
        bits_alocados=bits,
        representacao_pixel=representacao,
        quadros=quadros,
        inclinacao=inclinacao,
        intercepto=intercepto,
        hora_bruta=hora_bruta,
        data_bruta=data_bruta,
        tag_hora=tag_hora,
        data_hora=data_hora,
        descricao=descricao,
        sintaxe=str(sintaxe),
        sha256=hashlib.sha256(dados).hexdigest(),
        avisos=avisos,
    )
