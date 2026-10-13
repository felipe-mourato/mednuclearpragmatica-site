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

__all__ = ["gerar_dicom", "Fantoma", "fantoma_esvaziamento", "FantomaDMSA", "fantoma_dmsa"]


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

    ``roi`` é o contorno exato do "estômago" na anterior; ``eixo`` é o eixo
    longitudinal (linha média vertical, do topo ao fundo do retângulo, cujo
    meio separa exatamente as duas metades); ``retencao`` e
    ``distribuicao`` são os valores esperados (%) após correção de
    decaimento; ``minutos`` os tempos decorridos.
    """

    arquivos: dict[str, bytes]
    roi: list[tuple[float, float]]
    eixo: list[tuple[float, float]]
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
    eixo = [(float(x0 + larg / 2), float(y0)), (float(x0 + larg / 2), float(y0 + alt))]
    return Fantoma(arquivos, roi, eixo, list(minutos), list(retencao), list(distribuicao), multiframe)


@dataclass
class FantomaDMSA:
    """Fantoma de cintilografia renal com DMSA com resposta conhecida.

    ``rois`` traz os contornos exatos dos rins na posterior; ``esperado`` os
    percentuais do rim direito (o esquerdo é 100 menos) calculados à mão a
    partir das contagens do desenho, com o fundo uniforme subtraído.
    """

    arquivos: dict[str, bytes]
    multiframe: dict[str, bytes]
    rois: dict[str, list[tuple[float, float]]]
    esperado: dict[str, float]
    contagens: dict[str, float]


def fantoma_dmsa(
    tamanho: int = 64,
    fundo_post: int = 10,
    fundo_ant: int = 8,
    rim_d_post: int = 100,
    rim_e_post: int = 100,
    rim_d_ant: int = 50,
    rim_e_ant: int = 40,
    inicio: datetime = datetime(2026, 10, 13, 11, 0, 0),
) -> FantomaDMSA:
    """Gera um exame de DMSA com contagens conhecidas.

    Posterior (o rim direito do paciente fica à direita da imagem): rim
    direito retangular de 10 × 22 pixels (área 220) e rim esquerdo de
    10 × 28 pixels (área 280), ou seja, áreas de 44% e 56%. Atividade
    uniforme por pixel acima de um fundo uniforme em toda a imagem. Na
    anterior os rins aparecem espelhados (x' = tamanho − x) e com atividade
    menor, diferente em cada rim (profundidades diferentes).

    Como o fundo é uniforme, qualquer região de fundo fora dos rins mede
    exatamente o fundo, e a contagem corrigida de cada rim é
    (atividade por pixel) × área. Com os valores padrão, e os mesmos
    100 por pixel nos dois rins na posterior:

    * função relativa posterior: 22000 ÷ (22000 + 28000) = 44,0%;
    * área relativa: 220 ÷ 500 = 44,0%;
    * corrigida pelo tamanho (contagem por pixel): 100 ÷ (100 + 100) = 50,0%;
    * média geométrica: √(22000 × 11000) ÷ (√(22000 × 11000) + √(28000 × 11200)).

    Inclui também imagens OPD e OPE (só para exibição) e uma versão
    multiframe com o quadro 1 posterior e o quadro 2 anterior.
    """
    import math

    caixa_d = (38, 18, 10, 22)  # x0, y0, largura, altura, na posterior
    caixa_e = (14, 15, 10, 28)

    def imagem(fundo, caixas_valores):
        img = np.full((tamanho, tamanho), fundo, dtype=np.int64)
        for (x0, y0, w, h), valor in caixas_valores:
            img[y0 : y0 + h, x0 : x0 + w] = fundo + valor
        return img

    def espelho(caixa):
        x0, y0, w, h = caixa
        return (tamanho - x0 - w, y0, w, h)

    post = imagem(fundo_post, [(caixa_d, rim_d_post), (caixa_e, rim_e_post)])
    ant = imagem(fundo_ant, [(espelho(caixa_d), rim_d_ant), (espelho(caixa_e), rim_e_ant)])
    # Oblíquas: rins estreitados, só para a grade de imagens.
    opd = imagem(fundo_post, [((40, 18, 6, 22), rim_d_post), ((16, 15, 8, 28), rim_e_post)])
    ope = imagem(fundo_post, [((40, 18, 8, 22), rim_d_post), ((18, 15, 6, 28), rim_e_post)])

    arquivos = {
        "dmsa_post.dcm": gerar_dicom(post, inicio, "DMSA POST"),
        "dmsa_ant.dcm": gerar_dicom(ant, inicio + timedelta(minutes=1), "DMSA ANT"),
        "dmsa_opd.dcm": gerar_dicom(opd, inicio + timedelta(minutes=2), "DMSA OPD"),
        "dmsa_ope.dcm": gerar_dicom(ope, inicio + timedelta(minutes=3), "DMSA OPE"),
    }
    multiframe = {"dmsa_post_ant.dcm": gerar_dicom([post, ant], inicio, "DMSA")}

    def retangulo(caixa):
        x0, y0, w, h = caixa
        return [(float(x0), float(y0)), (float(x0 + w), float(y0)), (float(x0 + w), float(y0 + h)), (float(x0), float(y0 + h))]

    a_d = caixa_d[2] * caixa_d[3]
    a_e = caixa_e[2] * caixa_e[3]
    c = {
        "D_post": rim_d_post * a_d,
        "E_post": rim_e_post * a_e,
        "D_ant": rim_d_ant * a_d,
        "E_ant": rim_e_ant * a_e,
    }
    mg_d = math.sqrt(c["D_ant"] * c["D_post"])
    mg_e = math.sqrt(c["E_ant"] * c["E_post"])
    esp = {k: math.sqrt((c[f"{k}_ant"] / a) * (c[f"{k}_post"] / a)) for k, a in (("D", a_d), ("E", a_e))}
    esperado = {
        "frr_post": 100.0 * c["D_post"] / (c["D_post"] + c["E_post"]),
        "frr_mg": 100.0 * mg_d / (mg_d + mg_e),
        "area_post": 100.0 * a_d / (a_d + a_e),
        "area_mg": 100.0 * a_d / (a_d + a_e),
        "tam_post": 100.0 * rim_d_post / (rim_d_post + rim_e_post),
        "tam_mg": 100.0 * esp["D"] / (esp["D"] + esp["E"]),
    }
    return FantomaDMSA(arquivos, multiframe, {"D": retangulo(caixa_d), "E": retangulo(caixa_e)}, esperado, c)
