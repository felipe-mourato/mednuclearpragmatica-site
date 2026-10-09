import numpy as np
import pytest

from mnp_nucleo.comum.roi import (
    area_poligono,
    espelhar_horizontal,
    limitar_translacao,
    mascara_roi,
    normalizar,
    ponto_no_poligono,
    ponto_perto_do_poligono,
    simplificar_trajeto,
    transladar,
)

QUADRADO = [(2, 2), (6, 2), (6, 6), (2, 6)]


def poligono_aleatorio(rng, n=9, centro=(20, 18), raio=12):
    angulos = np.sort(rng.uniform(0, 2 * np.pi, n))
    raios = rng.uniform(0.4, 1.0, n) * raio
    return [(centro[0] + r * np.cos(a), centro[1] + r * np.sin(a)) for a, r in zip(angulos, raios)]


def test_ponto_no_poligono_basico():
    assert ponto_no_poligono(4, 4, QUADRADO)
    assert not ponto_no_poligono(7, 4, QUADRADO)
    assert not ponto_no_poligono(1, 1, QUADRADO)


def test_mascara_retangulo_area_exata():
    m = mascara_roi(QUADRADO, 10, 10)
    assert m.sum() == 16  # 4 × 4 pixels, valor esperado
    assert m[2:6, 2:6].all()


def test_mascara_igual_ao_teste_pixel_a_pixel():
    rng = np.random.default_rng(1)
    for _ in range(5):
        p = poligono_aleatorio(rng)
        m = mascara_roi(p, 40, 40)
        esperado = np.array([[ponto_no_poligono(c + 0.5, l + 0.5, p) for c in range(40)] for l in range(40)])
        assert np.array_equal(m, esperado)


def test_mascara_limitada_a_imagem():
    m = mascara_roi([(-5, -5), (3, -5), (3, 3), (-5, 3)], 10, 10)
    assert m.sum() == 9


def test_mascara_menos_de_3_pontos():
    assert mascara_roi([(1, 1), (3, 3)], 5, 5).sum() == 0


def test_area_poligono():
    assert area_poligono(QUADRADO) == 16
    assert area_poligono([(0, 0), (4, 0), (0, 3)]) == 6


# ------------------------------------------------------------ espelhamento
def test_espelho_e_involucao():
    rng = np.random.default_rng(2)
    p = poligono_aleatorio(rng)
    assert np.allclose(espelhar_horizontal(espelhar_horizontal(p, 40), 40), p)


def test_espelho_preserva_area_geometrica_e_de_pixels():
    rng = np.random.default_rng(3)
    for _ in range(10):
        p = poligono_aleatorio(rng)
        e = espelhar_horizontal(p, 40)
        assert area_poligono(e) == pytest.approx(area_poligono(p))
        assert mascara_roi(e, 40, 40).sum() == mascara_roi(p, 40, 40).sum()


def test_espelho_e_imagem_especular_exata_da_mascara():
    rng = np.random.default_rng(4)
    for _ in range(10):
        p = poligono_aleatorio(rng)
        m = mascara_roi(p, 40, 40)
        me = mascara_roi(espelhar_horizontal(p, 40), 40, 40)
        assert np.array_equal(me, m[:, ::-1])


def test_espelho_mantem_superior_inferior():
    e = espelhar_horizontal([(1, 2), (3, 8)], 10)
    assert e == [(9, 2), (7, 8)]


# ------------------------------------------------------------- translação
def test_transladar():
    assert transladar(QUADRADO, 1, -1)[0] == (3, 1)


def test_translacao_preserva_area():
    t = transladar(QUADRADO, 1.5, 2)
    assert area_poligono(t) == area_poligono(QUADRADO)
    assert mascara_roi(transladar(QUADRADO, 1, 2), 12, 12).sum() == 16


@pytest.mark.parametrize(
    "dx, dy, esperado",
    [(0, 0, (0, 0)), (100, 0, (4, 0)), (-100, 0, (-2, 0)), (0, 100, (0, 4)), (-1, 1, (-1, 1))],
)
def test_limitar_translacao(dx, dy, esperado):
    assert limitar_translacao(QUADRADO, dx, dy, 10, 10) == esperado


def test_poligono_nunca_sai_da_imagem():
    rng = np.random.default_rng(5)
    p = poligono_aleatorio(rng)
    for dx, dy in rng.uniform(-80, 80, (50, 2)):
        ddx, ddy = limitar_translacao(p, dx, dy, 40, 40)
        t = np.array(transladar(p, ddx, ddy))
        assert t[:, 0].min() >= -1e-9 and t[:, 0].max() <= 40 + 1e-9
        assert t[:, 1].min() >= -1e-9 and t[:, 1].max() <= 40 + 1e-9


def test_ponto_perto():
    assert ponto_perto_do_poligono((4, 4), QUADRADO, 0)
    assert ponto_perto_do_poligono((7, 4), QUADRADO, 1.5)
    assert not ponto_perto_do_poligono((9, 4), QUADRADO, 1.5)


def test_simplificar_trajeto():
    pts = [(0, 0), (0.5, 0), (2, 0), (2, 0.4), (2, 2), (0.2, 0.3)]
    assert simplificar_trajeto(pts, 1.5) == [(0, 0), (2, 0), (2, 2)]


def test_normalizar_formatos():
    assert normalizar([[1, 2], {"x": 3, "y": 4}, (5, 6)]) == [(1.0, 2.0), (3.0, 4.0), (5.0, 6.0)]
    with pytest.raises(ValueError):
        normalizar([[float("nan"), 1]])
