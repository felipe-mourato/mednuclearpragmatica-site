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

__all__ = [
    "gerar_dicom",
    "Fantoma",
    "fantoma_esvaziamento",
    "FantomaDMSA",
    "fantoma_dmsa",
    "codificar_jpeg_sem_perdas",
    "gerar_dicom_nm",
    "FantomaPerfusao",
    "fantoma_perfusao",
    "fantoma_ponto",
]


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


# ---------------------------------------------------------------------------
# Perfusão miocárdica: projeções de SPECT (DICOM NM) com geometria conhecida
# ---------------------------------------------------------------------------

_BITS_HUFF = [0, 1, 5, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 0]  # comprimentos 1..16
_VALS_HUFF = list(range(17))


def _codigos_huffman():
    codigos = {}
    codigo = 0
    k = 0
    for comprimento in range(1, 17):
        for _ in range(_BITS_HUFF[comprimento - 1]):
            codigos[_VALS_HUFF[k]] = (codigo, comprimento)
            codigo += 1
            k += 1
        codigo <<= 1
    return codigos


def codificar_jpeg_sem_perdas(quadro, precisao: int = 16) -> bytes:
    """Codifica um quadro em JPEG sem perdas (processo 14, preditor 1), para testes.

    Tabela de Huffman fixa para as categorias 0 a 16; segue a norma T.81
    (anexo H), com enchimento 0xFF 0x00. Não otimizado: serve para gerar
    fantomas comprimidos como os da Siemens.
    """
    x = np.asarray(quadro, dtype=np.int64) % (1 << precisao)
    linhas, colunas = x.shape
    pred = np.empty_like(x)
    pred[0, 0] = 1 << (precisao - 1)
    pred[0, 1:] = x[0, :-1]
    pred[1:, 0] = x[:-1, 0]
    pred[1:, 1:] = x[1:, :-1]
    dif = (x - pred) % (1 << 16)
    dif = np.where(dif >= 32768, dif - 65536, dif)
    codigos = _codigos_huffman()
    bits = []
    for d in dif.ravel().tolist():
        if d == 0:
            cat = 0
        elif d == -32768:
            cat = 16
        else:
            cat = abs(d).bit_length()
        cod, comp = codigos[cat]
        bits.append(format(cod, f"0{comp}b"))
        if 0 < cat < 16:
            v = d if d > 0 else d + (1 << cat) - 1
            bits.append(format(v, f"0{cat}b"))
    s = "".join(bits)
    s += "1" * ((-len(s)) % 8)
    corpo = bytearray()
    for i in range(0, len(s), 8):
        b = int(s[i : i + 8], 2)
        corpo.append(b)
        if b == 0xFF:
            corpo.append(0x00)
    dht = bytes([0x00]) + bytes(_BITS_HUFF) + bytes(_VALS_HUFF)
    sof = bytes([precisao]) + linhas.to_bytes(2, "big") + colunas.to_bytes(2, "big") + bytes([1, 1, 0x11, 0])
    sos = bytes([1, 1, 0x00, 1, 0, 0])

    def seg(m, dados):
        return bytes([0xFF, m]) + (len(dados) + 2).to_bytes(2, "big") + dados

    return b"\xff\xd8" + seg(0xC4, dht) + seg(0xC3, sof) + seg(0xDA, sos) + bytes(corpo) + b"\xff\xd9"


#: Geometria igual à da Siemens Symbia dos exames de teste: duas cabeças a 90°,
#: 32 vistas por cabeça, passo de 2,8125°, 180° no total, rotação horária.
GEOMETRIA_PADRAO = {
    "inicio": (225.0, 135.0),
    "passo": 2.8125,
    "vistas": 32,
    "pixel_mm": 6.4,
    "matriz": 64,
}


def _direcao_coluna(theta):
    t = np.deg2rad(theta)
    return np.array([-np.cos(t), np.sin(t)])


def projetar_pontos(pontos, pesos, angulos, pixel_mm: float, matriz: int, z0_mm: float, sigma_px: float = 0.8):
    """Projeções paralelas (ângulos, linhas, colunas) de uma nuvem de pontos com atividade.

    Coluna = (x, y)·u(θ)/Δ + c; linha = (z₀ − z)/Δ (a linha cresce para os
    pés). Espalhamento bilinear e borramento gaussiano (resolução do
    colimador), sem atenuação.
    """
    pts = np.asarray(pontos, dtype=np.float64)
    w = np.asarray(pesos, dtype=np.float64)
    c = (matriz - 1) / 2.0
    lin = (z0_mm - pts[:, 2]) / pixel_mm
    r0 = np.floor(lin).astype(int)
    wr = lin - r0
    saida = np.zeros((len(angulos), matriz, matriz))
    for a, th in enumerate(angulos):
        u = _direcao_coluna(th)
        col = (pts[:, 0] * u[0] + pts[:, 1] * u[1]) / pixel_mm + c
        c0 = np.floor(col).astype(int)
        wc = col - c0
        img = np.zeros((matriz + 2) * (matriz + 2))
        for dr, pr in ((0, 1 - wr), (1, wr)):
            for dc, pc in ((0, 1 - wc), (1, wc)):
                rr = np.clip(r0 + dr + 1, 0, matriz + 1)
                cc = np.clip(c0 + dc + 1, 0, matriz + 1)
                img += np.bincount(rr * (matriz + 2) + cc, weights=w * pr * pc, minlength=(matriz + 2) ** 2)
        saida[a] = img.reshape(matriz + 2, matriz + 2)[1:-1, 1:-1]
    if sigma_px > 0:
        k = np.arange(-4, 5)
        g = np.exp(-0.5 * (k / sigma_px) ** 2)
        g /= g.sum()
        saida = np.apply_along_axis(lambda v: np.convolve(v, g, mode="same"), 2, saida)
        saida = np.apply_along_axis(lambda v: np.convolve(v, g, mode="same"), 1, saida)
    return saida


def gerar_dicom_nm(
    projecoes,
    descricao: str,
    gated: bool = False,
    comprimir: bool = False,
    geometria: dict | None = None,
    z0_mm: float = 0.0,
    info_gated: dict | None = None,
    posicao: str = "FFS",
) -> bytes:
    """DICOM NM de projeções tomográficas com os vetores e sequências da geometria.

    ``projecoes``: (ângulos, linhas, colunas) ou, no gated,
    (intervalos, ângulos, linhas, colunas), na ordem: detector 1 (vistas
    1..32), detector 2 (vistas 1..32). Ordem dos quadros como na Siemens:
    para cada intervalo, detector, vista.
    """
    from pydicom.dataset import Dataset, FileMetaDataset
    from pydicom.encaps import encapsulate
    from pydicom.sequence import Sequence
    from pydicom.uid import ExplicitVRLittleEndian, JPEGLosslessSV1, generate_uid

    g = dict(GEOMETRIA_PADRAO, **(geometria or {}))
    p = np.asarray(projecoes)
    if p.ndim == 3:
        p = p[np.newaxis]
    n_int, n_ang, linhas, colunas = p.shape
    vistas = g["vistas"]
    quadros, det_v, vis_v, int_v = [], [], [], []
    for i in range(n_int):
        for d in range(2):
            for v in range(vistas):
                quadros.append(np.rint(np.clip(p[i, d * vistas + v], 0, 65535)).astype(np.uint16))
                det_v.append(d + 1)
                vis_v.append(v + 1)
                int_v.append(i + 1)
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = "1.2.840.10008.5.1.4.1.1.20"
    meta.MediaStorageSOPInstanceUID = generate_uid()
    meta.TransferSyntaxUID = JPEGLosslessSV1 if comprimir else ExplicitVRLittleEndian
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = meta.MediaStorageSOPClassUID
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Modality = "NM"
    ds.PatientName = "FANTOMA^PERFUSAO"
    ds.PatientID = "0000"
    ds.Manufacturer = "MedNuclear Pragmatica (fantoma digital)"
    ds.ManufacturerModelName = "Fantoma de VE"
    ds.SeriesDescription = descricao
    ds.ImageType = ["ORIGINAL", "PRIMARY", "GATED TOMO" if gated else "TOMO", "EMISSION"]
    ds.PatientPosition = posicao
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows, ds.Columns = linhas, colunas
    ds.BitsAllocated = ds.BitsStored = 16
    ds.HighBit = 15
    ds.PixelRepresentation = 0
    ds.NumberOfFrames = len(quadros)
    ds.PixelSpacing = [g["pixel_mm"], g["pixel_mm"]]
    ponteiros = [0x00540010, 0x00540020, 0x00540050] + ([0x00540070] if gated else []) + [0x00540090]
    ds.FrameIncrementPointer = ponteiros
    ds.EnergyWindowVector = [1] * len(quadros)
    ds.NumberOfEnergyWindows = 1
    ds.DetectorVector = det_v
    ds.NumberOfDetectors = 2
    ds.RotationVector = [1] * len(quadros)
    ds.NumberOfRotations = 1
    ds.AngularViewVector = vis_v
    if gated:
        ds.TimeSlotVector = int_v
        ds.NumberOfTimeSlots = n_int
        ds.RRIntervalVector = [1] * len(quadros)
        ds.NumberOfRRIntervals = 1
        ds.BeatRejectionFlag = "Y"
        ig = info_gated or {}
        if "frequencia" in ig:
            ds.HeartRate = int(ig["frequencia"])
        gi = Dataset()
        gi.CardiacFramingType = "FORW"
        di = Dataset()
        for nome, chave in (("NominalInterval", "rr_nominal"), ("LowRRValue", "rr_min"), ("HighRRValue", "rr_max"),
                            ("IntervalsAcquired", "aceitos"), ("IntervalsRejected", "rejeitados")):
            if chave in ig:
                setattr(di, nome, int(ig[chave]))
        gi.DataInformationSequence = Sequence([di])
        ds.GatedInformationSequence = Sequence([gi])
    ew = Dataset()
    faixa = Dataset()
    faixa.EnergyWindowLowerLimit = 129.5
    faixa.EnergyWindowUpperLimit = 150.5
    ew.EnergyWindowRangeSequence = Sequence([faixa])
    ew.EnergyWindowName = "99m Technetium"
    ds.EnergyWindowInformationSequence = Sequence([ew])
    dets = []
    for d in range(2):
        it = Dataset()
        a0 = g["inicio"][d]
        u = _direcao_coluna(a0)
        it.StartAngle = a0
        it.ImageOrientationPatient = [float(u[0]), float(u[1]), 0.0, 0.0, 0.0, -1.0]
        it.ImagePositionPatient = [0.0, 0.0, float(z0_mm)]
        it.CenterOfRotationOffset = 0
        it.CollimatorType = "PARA"
        dets.append(it)
    ds.DetectorInformationSequence = Sequence(dets)
    rot = Dataset()
    rot.StartAngle = g["inicio"][0]
    rot.AngularStep = g["passo"]
    rot.RotationDirection = "CW"
    rot.ScanArc = 90
    rot.NumberOfFramesInRotation = vistas
    rot.ActualFrameDuration = 20000
    ds.RotationInformationSequence = Sequence([rot])
    ds.TypeOfDetectorMotion = "STEP AND SHOOT"
    if comprimir:
        ds.PixelData = encapsulate([codificar_jpeg_sem_perdas(q) for q in quadros])
        ds["PixelData"].VR = "OB"
    else:
        ds.PixelData = np.stack(quadros).tobytes()
    buffer = io.BytesIO()
    ds.save_as(buffer, enforce_file_format=True)
    return buffer.getvalue()


def _angulos_padrao(g=None):
    g = dict(GEOMETRIA_PADRAO, **(g or {}))
    angs = [(g["inicio"][d] - v * g["passo"]) % 360 for d in range(2) for v in range(g["vistas"])]
    return np.asarray(angs)


def _base_ve(a):
    z = np.array([0.0, 0.0, 1.0])
    w = z - (z @ a) * a
    w /= np.linalg.norm(w)
    return w, np.cross(w, a)


def volume_elipsoide_truncado(L: float, R: float, s_base: float) -> float:
    """Volume (mm³) de {(s/L)² + (ρ/R)² ≤ 1, s ≥ s_base}: π R² [(L − s_b) − (L³ − s_b³)/(3L²)]."""
    s_b = max(float(s_base), -float(L))
    return float(np.pi * R**2 * ((L - s_b) - (L**3 - s_b**3) / (3.0 * L**2)))


@dataclass(frozen=True)
class GeometriaVE:
    """Geometria do VE sintético num instante (mm, coordenadas locais a partir do centro).

    Endocárdio: (s/L)² + (ρ/R)² = 1; epicárdio: (s/Le)² + (ρ/Re)² = 1;
    plano valvar em s = s_base (s cresce para o ápice).
    """

    L: float
    R: float
    Le: float
    Re: float
    s_base: float

    @property
    def cavidade_ml(self) -> float:
        return volume_elipsoide_truncado(self.L, self.R, self.s_base) / 1000.0

    @property
    def miocardio_ml(self) -> float:
        return volume_elipsoide_truncado(self.Le, self.Re, self.s_base) / 1000.0 - self.cavidade_ml


#: Diástole final do VE sintético: cavidade de ~71 mL, parede de ~9 mm.
GEOMETRIA_DIASTOLE = GeometriaVE(L=40.0, R=22.0, Le=50.0, Re=31.0, s_base=-22.0)
#: Contração ao longo de 8 intervalos (0 = diástole final, 1 = sístole final).
CONTRACAO_8 = (0.0, 0.45, 0.9, 1.0, 0.75, 0.4, 0.15, 0.02)


def geometria_no_ciclo(g: float, dilatacao: float = 1.0) -> GeometriaVE:
    """Geometria na fração de contração ``g`` (0–1), com massa miocárdica constante.

    Endocárdio: raio −30% e semieixo longo −12% na sístole final; a base
    desce 8 mm para o ápice; o ápice epicárdico recua 3 mm. O raio
    epicárdico sai da conservação do volume miocárdico (o da diástole
    final). ``dilatacao`` (estresse com dilatação isquêmica transitória)
    afasta endo e epicárdio do centro pela mesma distância (o raio
    endocárdico da diástole cresce na proporção ``dilatacao``), sem mudar
    a espessura da parede.
    """
    d = GEOMETRIA_DIASTOLE
    L = d.L * (1.0 - 0.12 * g)
    R = d.R * (1.0 - 0.30 * g)
    s_b = d.s_base + 8.0 * g
    Le = d.Le - 3.0 * g
    v_mio = d.miocardio_ml * 1000.0
    v_cav = volume_elipsoide_truncado(L, R, s_b)
    unit = volume_elipsoide_truncado(Le, 1.0, s_b)
    Re = float(np.sqrt((v_mio + v_cav) / unit))
    dr = (dilatacao - 1.0) * d.R
    dl = (dilatacao - 1.0) * d.L
    return GeometriaVE(L=L + dl, R=R + dr, Le=Le + dl, Re=Re + dr, s_base=s_b)


def _pontos_ve(centro, a, defeito: dict | None, geo: GeometriaVE = GEOMETRIA_DIASTOLE, passo: float = 2.0):
    """Miocárdio entre os dois elipsoides de ``geo``, acima do plano valvar; atividade 1 por mm³.

    Defeito: fator de atividade nos pontos com azimute (0° = lateral,
    90° = anterior) entre ``az`` e s < ``s_max``.
    """
    w, h = _base_ve(a)
    lim = geo.Le + 4.0
    gs = np.arange(-lim, lim + 0.01, passo)
    gr = np.arange(-(geo.Re + 4.0), geo.Re + 4.01, passo)
    s, u, v = np.meshgrid(gs, gr, gr, indexing="ij")
    s, u, v = s.ravel(), u.ravel(), v.ravel()
    rho = np.hypot(u, v)
    ext = (s / geo.Le) ** 2 + (rho / geo.Re) ** 2 <= 1.0
    inte = (s / geo.L) ** 2 + (rho / geo.R) ** 2 >= 1.0
    m = ext & inte & (s >= geo.s_base)
    s, u, v = s[m], u[m], v[m]
    pesos = np.ones(s.size)
    if defeito:
        az = np.degrees(np.arctan2(v, u)) % 360.0  # u ao longo de h (lateral), v ao longo de w (anterior)
        a0, a1 = defeito["az"]
        dentro = ((az - a0) % 360.0) <= ((a1 - a0) % 360.0)
        pesos[dentro & (s < defeito["s_max"])] *= defeito["fator"]
    pts = centro + s[:, None] * a + u[:, None] * h + v[:, None] * w
    return pts, pesos * passo**3


def _elipsoide(centro, raios, atividade, passo):
    g = [np.arange(-r, r + 0.01, passo) for r in raios]
    x, y, z = np.meshgrid(*g, indexing="ij")
    m = (x / raios[0]) ** 2 + (y / raios[1]) ** 2 + (z / raios[2]) ** 2 <= 1.0
    pts = np.stack([x[m], y[m], z[m]], axis=1) + np.asarray(centro)
    return pts, np.full(pts.shape[0], atividade * passo**3)


@dataclass
class FantomaPerfusao:
    """Exame de perfusão sintético: projeções DICOM NM, o eixo e as medidas verdadeiras do VE.

    ``eixo``: base e ápice verdadeiros (mm, x esquerda, y trás, z cabeça).
    ``defeito``: segmentos com captação reduzida no estresse (lateral:
    5, 6, 11 e 12, a 50%); o repouso é normal. ``verdade``: por estudo
    (``estresse``, ``repouso``), volumes da cavidade em cada intervalo (mL),
    VDF, VSF, FE (%) e o volume médio no ciclo (base da TID verdadeira).
    """

    arquivos: dict[str, bytes]
    eixo: dict
    segmentos_defeito: tuple
    fator_defeito: float
    descricao: str
    verdade: dict


#: Dilatação do VE no estresse (TID verdadeira ≈ 1,15).
DILATACAO_ESTRESSE = 1.05


def fantoma_perfusao(semente: int = 7, ruido: bool = True, contagens_estresse: float = 6.0e6) -> FantomaPerfusao:
    """Gera estresse, repouso e os dois gated (8 intervalos, VE batendo, arritmia no estresse).

    VE com o ápice para a esquerda, para a frente e para baixo
    (a ∝ (1; −0,7; −0,5)), centro da cavidade em (45; −25; 10) mm.
    Geometria em ``geometria_no_ciclo``: cavidade de ~71 mL na diástole
    final e ~27 mL na sístole final do repouso (FE ≈ 62%), massa constante,
    descida da base. Estresse com o VE dilatado (raio endocárdico da
    diástole 5% maior, parede com a mesma espessura). Defeito de estresse na parede lateral
    (azimute −60° a 60°, porções basal e média): 50% da atividade. As
    aquisições não sincronizadas são a média dos 8 instantes. Fígado à
    direita, foco intestinal intenso abaixo do coração e fundo corporal
    baixo. O estresse sai comprimido em JPEG sem perdas (como na Siemens);
    os demais sem compressão. Sem atenuação. Ruído de Poisson com semente fixa.
    """
    rng = np.random.default_rng(semente)
    g = GEOMETRIA_PADRAO
    angulos = _angulos_padrao()
    z0 = (g["matriz"] - 1) / 2.0 * g["pixel_mm"]
    a = np.array([1.0, -0.7, -0.5])
    a /= np.linalg.norm(a)
    centro = np.array([45.0, -25.0, 10.0])
    defeito = {"az": (300.0, 60.0), "s_max": 12.0, "fator": 0.5}
    figado = _elipsoide((-75.0, 0.0, -85.0), (85.0, 70.0, 45.0), 0.35, 5.0)
    foco = _elipsoide((-15.0, 5.0, -80.0), (12.0, 12.0, 12.0), 4.0, 2.0)
    corpo_g = np.arange(-150, 150.1, 12.0)
    zx, zy, zz = np.meshgrid(corpo_g, np.arange(-110, 110.1, 12.0), np.arange(-180, 180.1, 12.0), indexing="ij")
    mcorpo = (zx / 160.0) ** 2 + (zy / 115.0) ** 2 <= 1.0
    corpo = (np.stack([zx[mcorpo], zy[mcorpo], zz[mcorpo]], axis=1), np.full(int(mcorpo.sum()), 0.03 * 12.0**3))
    fundo = projetar_pontos(np.concatenate([figado[0], foco[0], corpo[0]]), np.concatenate([figado[1], foco[1], corpo[1]]),
                            angulos, g["pixel_mm"], g["matriz"], z0)

    def ve(com_defeito: bool, geo: GeometriaVE):
        pv, wv = _pontos_ve(centro, a, defeito if com_defeito else None, geo)
        return projetar_pontos(pv, wv, angulos, g["pixel_mm"], g["matriz"], z0)

    verdade = {}
    gated = {}
    for estudo, com_defeito, dil in (("estresse", True, DILATACAO_ESTRESSE), ("repouso", False, 1.0)):
        geos = [geometria_no_ciclo(c, dil) for c in CONTRACAO_8]
        gated[estudo] = np.stack([ve(com_defeito, ge) + fundo for ge in geos])
        vols = [ge.cavidade_ml for ge in geos]
        verdade[estudo] = {"volumes_ml": vols, "vdf_ml": max(vols), "vsf_ml": min(vols),
                           "fe": 100.0 * (max(vols) - min(vols)) / max(vols), "volume_medio_ml": float(np.mean(vols)),
                           "geometrias": geos}
    verdade["tid"] = verdade["estresse"]["volume_medio_ml"] / verdade["repouso"]["volume_medio_ml"]
    est = gated["estresse"].mean(axis=0)
    rep = gated["repouso"].mean(axis=0)
    est *= contagens_estresse / est.sum()
    rep *= 0.5 * contagens_estresse / rep.sum()
    # gated: estresse com arritmia (últimos intervalos com menos contagens)
    peso_est = np.array([1, 1, 1, 1, 1, 1, 0.9, 0.6])
    peso_rep = np.ones(8)
    gat_est = gated["estresse"] * (contagens_estresse / 8.0 * peso_est / gated["estresse"].sum(axis=(1, 2, 3)))[:, None, None, None]
    gat_rep = gated["repouso"] * (0.5 * contagens_estresse / 8.0 * peso_rep / gated["repouso"].sum(axis=(1, 2, 3)))[:, None, None, None]
    if ruido:
        est, rep, gat_est, gat_rep = (rng.poisson(x).astype(np.float64) for x in (est, rep, gat_est, gat_rep))
    arquivos = {
        "estresse.dcm": gerar_dicom_nm(est, "Stress", comprimir=True, z0_mm=z0),
        "repouso.dcm": gerar_dicom_nm(rep, "REST", z0_mm=z0),
        "gated_estresse.dcm": gerar_dicom_nm(gat_est, "Stress Gated", gated=True, z0_mm=z0,
                                             info_gated={"frequencia": 72, "rr_nominal": 833, "rr_min": 667, "rr_max": 1000, "aceitos": 610, "rejeitados": 95}),
        "gated_repouso.dcm": gerar_dicom_nm(gat_rep, "REST Gated", gated=True, z0_mm=z0,
                                            info_gated={"frequencia": 64, "rr_nominal": 938, "rr_min": 750, "rr_max": 1125, "aceitos": 700, "rejeitados": 6}),
    }
    d = GEOMETRIA_DIASTOLE
    eixo = {"base": (centro + d.s_base * a).tolist(), "apice": (centro + d.Le * a).tolist()}
    return FantomaPerfusao(arquivos, eixo, (5, 6, 11, 12), 0.5,
                           "VE sintético batendo (FE verdadeira de cerca de 60%), com defeito lateral no estresse "
                           "(50% nos segmentos 5, 6, 11 e 12), dilatação de 5% no estresse e repouso normal.", verdade)


def fantoma_ponto(posicao_mm=(40.0, -30.0, 20.0), geometria: dict | None = None) -> bytes:
    """Projeções de uma fonte pontual (sem ruído), para conferir geometria e lateralidade."""
    g = dict(GEOMETRIA_PADRAO, **(geometria or {}))
    z0 = (g["matriz"] - 1) / 2.0 * g["pixel_mm"]
    p = projetar_pontos(np.asarray([posicao_mm], dtype=np.float64), [1.0e5], _angulos_padrao(g), g["pixel_mm"], g["matriz"], z0)
    return gerar_dicom_nm(p, "Ponto", geometria=g, z0_mm=z0)
