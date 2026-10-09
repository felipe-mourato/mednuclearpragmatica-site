"""Fantomas sintéticos: DICOMs com contagens conhecidas para testar e validar.

Os arquivos são DICOM de verdade (Secondary Capture, MONOCHROME2, não
comprimidos), escritos com pydicom. Servem aos testes automáticos e a quem
quiser conferir a ferramenta web com um caso de resposta conhecida.

Exemplo::

    from mnp_nucleo.fantomas import fantoma_esvaziamento
    f = fantoma_esvaziamento()
    for nome, dados in f.arquivos.items():
        open(nome, "wb").write(dados)
    print(f.retencao)  # retenção esperada em cada tempo (%)
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta

import numpy as np
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.uid import ExplicitVRLittleEndian, ImplicitVRLittleEndian, SecondaryCaptureImageStorage, generate_uid

__all__ = ["gerar_dicom", "Fantoma", "fantoma_esvaziamento"]


def gerar_dicom(
    quadros,
    data_hora: datetime | None = None,
    descricao: str = "",
    bits: int = 16,
    com_sinal: bool = False,
    inclinacao: float | None = None,
    intercepto: float | None = None,
    sintaxe=ExplicitVRLittleEndian,
    tag_hora: str = "AcquisitionTime",
    preambulo: bool = True,
) -> bytes:
    """Escreve um DICOM com os quadros dados (lista de arrays 2D de inteiros)."""
    quadros = [np.asarray(q) for q in (quadros if isinstance(quadros, (list, tuple)) else [quadros])]
    linhas, colunas = quadros[0].shape
    tipo = {(8, False): np.uint8, (16, False): np.uint16, (16, True): np.int16, (32, False): np.uint32, (32, True): np.int32}[
        (bits, com_sinal)
    ]
    pixels = np.stack(quadros).astype(tipo)

    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = sintaxe
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "NM"
    ds.PatientName = "FANTOMA^SINTETICO"
    ds.PatientID = "0000"
    if data_hora is not None:
        ds.StudyDate = ds.AcquisitionDate = data_hora.strftime("%Y%m%d")
        setattr(ds, tag_hora, data_hora.strftime("%H%M%S"))
    if descricao:
        ds.SeriesDescription = descricao
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = bits
    ds.BitsStored = bits
    ds.HighBit = bits - 1
    ds.PixelRepresentation = 1 if com_sinal else 0
    if len(quadros) > 1:
        ds.NumberOfFrames = len(quadros)
    if inclinacao is not None:
        ds.RescaleSlope = repr(float(inclinacao))
    if intercepto is not None:
        ds.RescaleIntercept = repr(float(intercepto))
    ds.PixelData = pixels.tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=preambulo, implicit_vr=sintaxe == ImplicitVRLittleEndian, little_endian=True)
    return buffer.getvalue()


@dataclass
class Fantoma:
    """Fantoma de esvaziamento gástrico com resposta conhecida.

    ``roi`` é o contorno exato do "estômago" na anterior; ``retencao`` e
    ``distribuicao`` são os valores esperados (%) após correção de
    decaimento; ``minutos`` os tempos decorridos.
    """

    arquivos: dict[str, bytes]
    roi: list[tuple[float, float]]
    minutos: list[float]
    retencao: list[float]
    distribuicao: list[float]
    multiframe: dict[str, bytes] = field(default_factory=dict)


def fantoma_esvaziamento(
    tamanho: int = 64,
    retencao=(100.0, 60.0, 30.0, 8.0),
    distribuicao=(75.0, 55.0, 40.0, 30.0),
    minutos=(0.0, 60.0, 120.0, 240.0),
    atenuacao_post: float = 0.8,
    meia_vida_h: float = 6.0067,
    por_pixel_t0: float = 5000.0,
    inicio: datetime = datetime(2026, 9, 21, 13, 0, 0),
) -> Fantoma:
    """Gera um exame de esvaziamento gástrico com contagens conhecidas.

    "Estômago" retangular de 12 × 24 pixels (largura × altura) na anterior,
    com atividade uniforme na metade superior (proximal) e na inferior
    (distal). Na posterior o estômago aparece espelhado (do outro lado da
    imagem) e atenuado por ``atenuacao_post``. Fundo zero. As contagens
    caem com o esvaziamento biológico (``retencao``) e com o decaimento
    físico do ⁹⁹ᵐTc, de modo que a ferramenta deve devolver exatamente
    ``retencao`` (a menos do arredondamento dos pixels para inteiros) e
    ``distribuicao`` como distribuição proximal.
    """
    larg, alt = 12, 24
    x0, y0 = tamanho // 2 + 6, tamanho // 4
    x0_post = tamanho - x0 - larg  # espelho exato: coluna c → tamanho − 1 − c
    metade = alt // 2
    n_metade = larg * metade
    arquivos: dict[str, bytes] = {}
    multiframe: dict[str, bytes] = {}
    for i, (r, d, t) in enumerate(zip(retencao, distribuicao, minutos)):
        total_bio = por_pixel_t0 * 2 * n_metade * r / 100.0
        decai = 2.0 ** (-t / (meia_vida_h * 60.0))
        prox_px = total_bio * d / 100.0 / n_metade * decai
        dist_px = total_bio * (1 - d / 100.0) / n_metade * decai
        dh = inicio + timedelta(minutes=t)
        imgs = {}
        for vista, xc, fator in (("ant", x0, 1.0), ("post", x0_post, atenuacao_post)):
            img = np.zeros((tamanho, tamanho), dtype=np.int64)
            img[y0 : y0 + metade, xc : xc + larg] = round(prox_px * fator)
            img[y0 + metade : y0 + alt, xc : xc + larg] = round(dist_px * fator)
            imgs[vista] = img
            rotulo = "ANT" if vista == "ant" else "POST"
            arquivos[f"T{i}_{vista}.dcm"] = gerar_dicom(img, dh, f"{rotulo} T{i}")
        multiframe[f"T{i}_antpost.dcm"] = gerar_dicom([imgs["ant"], imgs["post"]], dh, f"ANT/POST T{i}")
    roi = [(float(x0), float(y0)), (float(x0 + larg), float(y0)), (float(x0 + larg), float(y0 + alt)), (float(x0), float(y0 + alt))]
    return Fantoma(arquivos, roi, list(minutos), list(retencao), list(distribuicao), multiframe)
