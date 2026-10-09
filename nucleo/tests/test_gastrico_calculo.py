import math

import numpy as np
import pytest

from mnp_nucleo.comum.roi import mascara_roi
from mnp_nucleo.gastrico.calculo import (
    ContagensRegionais,
    calcular_resultados,
    contagens_regionais,
    retencao_percentual,
)
from mnp_nucleo.gastrico.segmentacao import segmentar_roi


# ------------------------------------------------------------ segmentação
def test_segmentacao_retangulo_vertical_metades_superior_inferior():
    m = mascara_roi([(10, 4), (20, 4), (20, 24), (10, 24)], 30, 30)
    s = segmentar_roi(m)
    assert s.proximal.sum() == s.distal.sum() == 100
    assert s.proximal[4:14, 10:20].all() and s.distal[14:24, 10:20].all()
    assert abs(s.eixo[0]) < 1e-9 and abs(abs(s.eixo[1]) - 1) < 1e-9
    assert s.centroide_proximal[1] < s.centroide_distal[1]


def test_segmentacao_particiona_a_roi():
    rng = np.random.default_rng(7)
    for _ in range(10):
        ang = np.sort(rng.uniform(0, 2 * np.pi, 10))
        r = rng.uniform(5, 14, 10)
        p = [(25 + ri * np.cos(a), 25 + ri * np.sin(a)) for a, ri in zip(ang, r)]
        m = mascara_roi(p, 50, 50)
        s = segmentar_roi(m)
        assert not (s.proximal & s.distal).any()
        assert np.array_equal(s.proximal | s.distal, m)
        # mesmo número de pixels, a menos de empates na mediana
        assert abs(int(s.proximal.sum()) - int(s.distal.sum())) <= max(2, m.sum() // 10)
        assert s.centroide_proximal[1] <= s.centroide_distal[1]


def test_segmentacao_eixo_obliquo():
    # elipse alongada a 45°: o eixo principal deve sair a ±45°
    l, c = np.mgrid[0:60, 0:60] + 0.5
    u, v = (c - 30 + l - 30) / math.sqrt(2), (c - 30 - (l - 30)) / math.sqrt(2)
    m = (u / 20) ** 2 + (v / 6) ** 2 <= 1
    s = segmentar_roi(m)
    assert abs(abs(s.eixo[0]) - abs(s.eixo[1])) < 0.02
    assert s.proximal.sum() == s.distal.sum()


def test_segmentacao_roi_minuscula():
    m = np.zeros((5, 5), bool)
    m[2, 2] = True
    with pytest.raises(ValueError):
        segmentar_roi(m)


# --------------------------------------------------------------- cálculos
def test_retencao_valor_esperado_sem_decaimento():
    assert retencao_percentual(500, 1000, 120, None) == 50


def test_retencao_valor_esperado_com_decaimento():
    # 50% medidos após 1 meia-vida = 100% da atividade biológica
    assert retencao_percentual(500, 1000, 6.0067 * 60, 6.0067) == pytest.approx(100)
    # 2 h de Tc-99m: 2^(120/360,402) = 1,259596
    assert retencao_percentual(400, 1000, 120, 6.0067) == pytest.approx(40 * 1.259596, rel=1e-6)


def test_retencao_t0_zero():
    with pytest.raises(ValueError):
        retencao_percentual(1, 0, 10, None)


def _cr(minutos, total, prox, dist):
    return ContagensRegionais(minutos, total, total, prox, prox, dist, dist, total, prox, dist)


def test_tabela_valores_esperados():
    linhas = calcular_resultados(
        [_cr(0, 1000, 800, 200), _cr(60, 600, 300, 300), _cr(120, 250, 50, 200)], meia_vida_h=None
    )
    assert [l.rotulo for l in linhas] == ["T0", "T1", "T2"]
    assert [round(l.retencao, 6) for l in linhas] == [100, 60, 25]
    assert [round(l.esvaziamento, 6) for l in linhas] == [0, 40, 75]
    assert [round(l.distribuicao_proximal, 6) for l in linhas] == [80, 50, 20]
    assert [round(l.retencao_proximal, 6) for l in linhas] == [80, 30, 5]
    assert [round(l.retencao_distal, 6) for l in linhas] == [20, 30, 20]


def test_invariantes_da_tabela():
    """Retenção + esvaziamento = 100; proximal + distal = retenção; nada negativo."""
    rng = np.random.default_rng(11)
    for _ in range(20):
        tempos = []
        for i, t in enumerate((0, 60, 120, 240)):
            a = rng.uniform(100, 10_000, (20, 20))
            p = a * rng.uniform(0.5, 1.2)
            m = np.zeros((20, 20), bool)
            m[2:18, 5:15] = True
            s = segmentar_roi(m)
            tempos.append(contagens_regionais(t, a, p, m, s.proximal, s.distal, m, s.proximal, s.distal))
        for meia_vida in (None, 6.0067):
            for l in calcular_resultados(tempos, meia_vida):
                assert l.retencao + l.esvaziamento == pytest.approx(100)
                assert l.retencao_proximal + l.retencao_distal == pytest.approx(l.retencao)
                assert 0 <= l.distribuicao_proximal <= 100
                assert l.retencao_proximal >= 0 and l.retencao_distal >= -1e-9
                assert l.mg_proximal <= l.mg_total + 1e-9


def test_contagens_regionais_media_geometrica():
    a = np.full((4, 4), 4.0)
    p = np.full((4, 4), 9.0)
    m = np.ones((4, 4), bool)
    prox = np.zeros((4, 4), bool)
    prox[:2] = True
    c = contagens_regionais(30, a, p, m, prox, ~prox, m, prox, ~prox)
    assert (c.total_ant, c.total_post) == (64, 144)
    assert c.mg_total == 96  # √(64 × 144)
    assert c.mg_proximal == c.mg_distal == 48


def test_tabela_vazia():
    assert calcular_resultados([], None) == []


def test_linha_divisoria_dentro_do_retangulo_da_roi():
    m = mascara_roi([(10, 4), (20, 4), (20, 24), (10, 24)], 30, 30)
    (ax, ay), (bx, by) = segmentar_roi(m).linha
    assert sorted([ax, bx]) == [10, 20] and ay == pytest.approx(14) and by == pytest.approx(14)
