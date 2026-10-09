import numpy as np
import pytest

from mnp_nucleo.comum.contagens import MEIA_VIDA_TC99M_H, fator_decaimento, media_geometrica, soma_contagens
from mnp_nucleo.comum.exibicao import (
    ajustar_janela_por_arraste,
    aplicar_janela,
    janela_padrao,
    renderizar_rgba,
)


def test_soma_contagens():
    v = np.arange(12, dtype=float).reshape(3, 4)
    m = np.zeros((3, 4), bool)
    m[1, 1:3] = True
    assert soma_contagens(v, m) == 5 + 6


def test_soma_dimensoes_diferentes():
    with pytest.raises(ValueError):
        soma_contagens(np.zeros((2, 2)), np.zeros((3, 3), bool))


def test_media_geometrica():
    assert media_geometrica(400, 900) == 600
    assert media_geometrica(0, 900) == 0
    with pytest.raises(ValueError):
        media_geometrica(-1, 4)


def test_fator_decaimento():
    assert fator_decaimento(0, MEIA_VIDA_TC99M_H) == 1
    assert fator_decaimento(MEIA_VIDA_TC99M_H * 60, MEIA_VIDA_TC99M_H) == pytest.approx(2.0)
    # 4 h de Tc-99m: 2^(240/360,402) = 1,586583
    assert fator_decaimento(240, MEIA_VIDA_TC99M_H) == pytest.approx(1.586583, abs=1e-6)
    assert fator_decaimento(240, None) == 1
    assert fator_decaimento(240, 0) == 1


# ---------------------------------------------------------------- exibição
def test_janela_padrao():
    j = janela_padrao(np.array([10.0, 30.0]))
    assert (j.nivel, j.largura) == (20, 20)
    assert janela_padrao(np.array([5.0, 5.0])).largura == 1


def test_aplicar_janela_extremos_e_meio():
    v = np.array([0.0, 50.0, 100.0, -10.0, 200.0])
    assert aplicar_janela(v, 50, 100).tolist() == [0, 128, 255, 0, 255]


def test_arraste_de_janela():
    j = ajustar_janela_por_arraste(100, 50, dx_px=256, dy_px=-256, faixa=256)
    assert (j.nivel, j.largura) == (356, 306)
    assert ajustar_janela_por_arraste(100, 50, -1000, 0, 256).largura == 1


def test_exibicao_nao_altera_valores_brutos():
    """Invariante: janela, inversão e sobreposição nunca mudam os pixels usados no cálculo."""
    rng = np.random.default_rng(0)
    v = rng.uniform(0, 1000, (16, 16))
    copia = v.copy()
    m = np.zeros((16, 16), bool)
    m[4:9, 4:9] = True
    antes = soma_contagens(v, m)
    for nivel, largura, inv in [(500, 1000, False), (10, 2, True), (900, 50, False)]:
        aplicar_janela(v, nivel, largura)
        renderizar_rgba(v, nivel, largura, inv, [(m, (255, 0, 0), 0.5)])
    assert np.array_equal(v, copia)
    assert soma_contagens(v, m) == antes


def test_renderizar_rgba_formato_e_inversao():
    v = np.array([[0.0, 100.0]])
    normal = np.frombuffer(renderizar_rgba(v, 50, 100), np.uint8).reshape(1, 2, 4)
    inv = np.frombuffer(renderizar_rgba(v, 50, 100, True), np.uint8).reshape(1, 2, 4)
    assert normal[0, 0].tolist() == [0, 0, 0, 255] and normal[0, 1].tolist() == [255, 255, 255, 255]
    assert inv[0, 0].tolist() == [255, 255, 255, 255]


def test_sobreposicao_mistura_cor():
    v = np.zeros((1, 2))
    m = np.array([[True, False]])
    px = np.frombuffer(renderizar_rgba(v, 50, 100, False, [(m, (200, 100, 0), 0.5)]), np.uint8).reshape(1, 2, 4)
    assert px[0, 0, :3].tolist() == [100, 50, 0]
    assert px[0, 1, :3].tolist() == [0, 0, 0]
