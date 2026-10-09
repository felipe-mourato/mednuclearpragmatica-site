from datetime import datetime

import numpy as np
import pydicom
import pytest
from pydicom.dataset import Dataset, FileMetaDataset
from pydicom.encaps import encapsulate
from pydicom.uid import ImplicitVRLittleEndian, JPEGBaseline8Bit, SecondaryCaptureImageStorage, generate_uid

from mnp_nucleo.comum.dicom import (
    ErroDicom,
    adivinhar_vista,
    combinar_data_hora,
    interpretar_data,
    interpretar_hora,
    ler_dicom,
)
from mnp_nucleo.fantomas import gerar_dicom

DH = datetime(2026, 9, 21, 13, 5, 30)


def imagem(valor=7, linhas=4, colunas=5):
    return np.full((linhas, colunas), valor)


# ------------------------------------------------------------------ horário
@pytest.mark.parametrize(
    "tm, esperado",
    [
        ("130530", (13, 5, 30)),
        ("130530.123456", (13, 5, 30)),
        ("1305", (13, 5, 0)),
        ("13", (13, 0, 0)),
        ("13:05:30", (13, 5, 30)),
        (" 080000 ", (8, 0, 0)),
        ("250000", None),
        ("abc", None),
        ("", None),
        (None, None),
    ],
)
def test_interpretar_hora(tm, esperado):
    assert interpretar_hora(tm) == esperado


def test_interpretar_data():
    assert interpretar_data("20260921") == (2026, 9, 21)
    assert interpretar_data("20260231") is None
    assert interpretar_data("2026") is None


def test_combinar_data_hora_sem_data_usa_base():
    assert combinar_data_hora(None, "0930") == datetime(2000, 1, 1, 9, 30)
    assert combinar_data_hora("20260921", None) is None


def test_virada_da_meia_noite_preservada():
    a = combinar_data_hora("20260921", "2350")
    b = combinar_data_hora("20260922", "0050")
    assert (b - a).total_seconds() / 60 == 60


# ---------------------------------------------------------------- leitura
def test_le_quadro_unico_e_soma():
    img = ler_dicom(gerar_dicom(imagem(7), DH, "ANT"))
    assert (img.linhas, img.colunas, img.n_quadros) == (4, 5, 1)
    assert img.contagem_total() == 7 * 20
    assert img.data_hora == DH
    assert img.tag_hora == "(0008,0032)"
    assert not img.multiframe


def test_rescale_aplicado():
    img = ler_dicom(gerar_dicom(imagem(10), DH, inclinacao=2.5, intercepto=-3))
    assert np.allclose(img.quadro(0), 10 * 2.5 - 3)
    assert img.contagem_total() == pytest.approx(20 * 22.0)


@pytest.mark.parametrize("bits,sinal,valor", [(8, False, 200), (16, False, 60000), (16, True, -1200), (32, False, 100000)])
def test_profundidades(bits, sinal, valor):
    img = ler_dicom(gerar_dicom(imagem(valor), DH, bits=bits, com_sinal=sinal))
    assert img.bits_alocados == bits
    assert np.all(img.quadro(0) == valor)


def test_multiframe_e_selecao_de_quadro():
    dados = gerar_dicom([imagem(1), imagem(2), imagem(3)], DH, "ANT/POST")
    img = ler_dicom(dados)
    assert img.n_quadros == 3 and img.multiframe
    assert [img.contagem_total(i) for i in range(3)] == [20, 40, 60]
    # índice fora do intervalo é limitado
    assert img.contagem_total(9) == 60


def test_implicit_vr_e_sem_preambulo():
    img = ler_dicom(gerar_dicom(imagem(5), DH, sintaxe=ImplicitVRLittleEndian))
    assert img.contagem_total() == 100
    sem = gerar_dicom(imagem(5), DH, sintaxe=ImplicitVRLittleEndian, preambulo=False)
    assert sem[128:132] != b"DICM"
    assert ler_dicom(sem).contagem_total() == 100


@pytest.mark.parametrize(
    "tag, rotulo",
    [("ContentTime", "(0008,0033)"), ("SeriesTime", "(0008,0031)"), ("StudyTime", "(0008,0030)")],
)
def test_alternativas_de_horario(tag, rotulo):
    img = ler_dicom(gerar_dicom(imagem(), DH, tag_hora=tag))
    assert img.tag_hora == rotulo
    assert img.data_hora == DH


def test_sem_horario():
    img = ler_dicom(gerar_dicom(imagem(), None))
    assert img.data_hora is None and not img.horario_encontrado


def test_aceita_memoryview_e_objeto_com_to_bytes():
    dados = gerar_dicom(imagem(3), DH)

    class ProxyJs:  # imita o JsProxy de um Uint8Array no Pyodide
        def to_bytes(self):
            return dados

    assert ler_dicom(memoryview(dados)).contagem_total() == 60
    assert ler_dicom(ProxyJs()).contagem_total() == 60


def test_sha256_estavel():
    dados = gerar_dicom(imagem(3), DH)
    assert ler_dicom(dados).sha256 == ler_dicom(bytes(dados)).sha256


# ------------------------------------------------------------------- erros
def test_nao_dicom():
    with pytest.raises(ErroDicom, match="não é um DICOM"):
        ler_dicom(b"isto nao e um dicom" * 20)


def test_pequeno_demais():
    with pytest.raises(ErroDicom):
        ler_dicom(b"123")


def _ds_base():
    meta = FileMetaDataset()
    meta.MediaStorageSOPClassUID = SecondaryCaptureImageStorage
    meta.MediaStorageSOPInstanceUID = generate_uid()
    ds = Dataset()
    ds.file_meta = meta
    ds.SOPClassUID = SecondaryCaptureImageStorage
    ds.SOPInstanceUID = meta.MediaStorageSOPInstanceUID
    ds.Rows, ds.Columns = 4, 5
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    return ds


def _salvar(ds, **kw):
    import io

    b = io.BytesIO()
    ds.save_as(b, enforce_file_format=True, **kw)
    return b.getvalue()


def test_comprimido_mensagem_clara():
    ds = _ds_base()
    ds.file_meta.TransferSyntaxUID = JPEGBaseline8Bit
    ds.PixelData = encapsulate([b"\xff\xd8\xff\xd9"])
    with pytest.raises(ErroDicom, match="comprimido não suportado"):
        ler_dicom(_salvar(ds))


def test_sem_pixels():
    ds = _ds_base()
    ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    with pytest.raises(ErroDicom, match="sem dados de pixel"):
        ler_dicom(_salvar(ds, implicit_vr=True, little_endian=True))


def test_colorido():
    ds = _ds_base()
    ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds.SamplesPerPixel = 3
    ds.PhotometricInterpretation = "RGB"
    ds.PlanarConfiguration = 0
    ds.PixelData = bytes(4 * 5 * 3)
    with pytest.raises(ErroDicom, match="colorida"):
        ler_dicom(_salvar(ds, implicit_vr=True, little_endian=True))


def test_pixels_truncados():
    ds = _ds_base()
    ds.file_meta.TransferSyntaxUID = ImplicitVRLittleEndian
    ds.PixelData = bytes(6)
    with pytest.raises(ErroDicom):
        ler_dicom(_salvar(ds, implicit_vr=True, little_endian=True))


# ------------------------------------------------------------------ vista
@pytest.mark.parametrize(
    "descricao, vista",
    [
        ("ANT T0", "anterior"),
        ("POST T0", "posterior"),
        ("Estômago pós", "posterior"),
        ("ANT/POST", "anterior"),
        ("", "anterior"),
        (None, "anterior"),
    ],
)
def test_adivinhar_vista(descricao, vista):
    assert adivinhar_vista(descricao) == vista


def test_pydicom_versao_minima():
    assert int(pydicom.__version__.split(".")[0]) >= 3
