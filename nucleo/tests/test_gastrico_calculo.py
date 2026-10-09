import numpy as np
import pytest

from mnp_nucleo.comum.roi import mascara_roi
from mnp_nucleo.gastrico import referencias
from mnp_nucleo.gastrico.calculo import (
    ContagensRegionais,
    calcular_resultados,
    contagens_regionais,
    retencao_percentual,
)
from mnp_nucleo.gastrico.segmentacao import (
    comprimento_trajeto,
    eixo_automatico,
    orientar_eixo,
    ponto_na_fracao,
    preparar_eixo,
    projetar_no_eixo,
    segmentar_por_eixo,
)

RET = [(10, 4), (20, 4), (20, 24), (10, 24)]  # retângulo 10 × 20 pixels


# --------------------------------------------------------------- eixo
def test_comprimento_e_ponto_no_meio():
    eixo = [(0, 0), (3, 4), (3, 10)]  # 5 + 6 = 11
    assert comprimento_trajeto(eixo) == 11
    (mx, my), (tx, ty) = ponto_na_fracao(eixo, 0.5)  # 5,5 do início: 0,5 dentro do 2º segmento
    assert (mx, my) == pytest.approx((3, 4.5))
    assert (tx, ty) == pytest.approx((0, 1))


def test_eixo_orientado_do_fundo_para_o_distal():
    assert orientar_eixo([(5, 30), (5, 2)]) == [(5, 2), (5, 30)]
    assert orientar_eixo([(5, 2), (5, 30)]) == [(5, 2), (5, 30)]
    traco = [(5.0, 30.0 - i) for i in range(29)]  # desenhado de baixo para cima
    eixo = preparar_eixo(traco)
    assert eixo[0][1] < eixo[-1][1] and eixo[-1] == (5.0, 30.0)


def test_projecao_no_eixo():
    xs = np.array([0.0, 5.0, 12.0, -3.0])
    ys = np.array([2.0, 7.0, 3.0, 0.0])
    s = projetar_no_eixo(xs, ys, [(0, 0), (10, 0)])
    assert s.tolist() == pytest.approx([0, 5, 10, 0])


# ----------------------------------------------------------- segmentação
def test_corte_perpendicular_no_meio_do_eixo():
    """Eixo vertical de y=4 a y=24: meio em y=14; proximal = 10 linhas de cima."""
    m = mascara_roi(RET, 30, 30)
    s = segmentar_por_eixo(m, [(15, 4), (15, 24)])
    assert s.proximal.sum() == s.distal.sum() == 100
    assert s.proximal[4:14, 10:20].all() and s.distal[14:24, 10:20].all()
    assert s.comprimento == 20 and s.meio == pytest.approx((15, 14))
    (ax, ay), (bx, by) = s.corte
    assert sorted([ax, bx]) == pytest.approx([10, 20]) and ay == pytest.approx(14) and by == pytest.approx(14)


def test_metade_e_do_comprimento_do_eixo_nao_da_area():
    """Fundo largo e antro fino: o corte fica no meio do eixo, não onde as áreas se igualam."""
    fundo = [(0, 0), (20, 0), (20, 10), (0, 10)]  # 20 × 10 = 200 px
    m = mascara_roi(fundo, 40, 40) | mascara_roi([(8, 10), (12, 10), (12, 30), (8, 30)], 40, 40)  # antro 4 × 20
    s = segmentar_por_eixo(m, [(10, 0), (10, 30)])  # L = 30, meio em y = 15
    assert s.meio == pytest.approx((10, 15))
    assert s.proximal.sum() == 200 + 4 * 5  # fundo inteiro + 5 linhas do antro
    assert s.distal.sum() == 4 * 15


def test_estomago_em_j_corte_nao_atravessa_o_antro():
    """Eixo em L: a perpendicular no meio, se prolongada, cortaria o antro ao comprido.

    Corpo vertical x 30–40, y 0–40; antro horizontal x 0–40, y 30–40.
    Eixo (35,0) → (35,35) → (10,35): L = 35 + 25 = 60, meio em (35, 30).
    A reta y = 30 passa pela borda de cima do antro; o antro (x < 30) tem de
    ficar todo distal, e o corpo acima do corte, todo proximal.
    """
    corpo = mascara_roi([(30, 0), (40, 0), (40, 40), (30, 40)], 50, 50)
    antro = mascara_roi([(0, 30), (40, 30), (40, 40), (0, 40)], 50, 50)
    m = corpo | antro
    s = segmentar_por_eixo(m, [(35, 0), (35, 35), (10, 35)])
    assert s.meio == pytest.approx((35, 30))
    assert not s.proximal[:, :30].any()  # nada do antro no proximal
    assert s.proximal[0:30, 30:40].all()  # corpo acima do corte, proximal


def test_segmentacao_particiona_a_roi():
    rng = np.random.default_rng(7)
    for _ in range(10):
        ang = np.sort(rng.uniform(0, 2 * np.pi, 10))
        r = rng.uniform(5, 14, 10)
        p = [(25 + ri * np.cos(a), 25 + ri * np.sin(a)) for a, ri in zip(ang, r)]
        m = mascara_roi(p, 50, 50)
        s = segmentar_por_eixo(m, [(25 + rng.uniform(-3, 3), 12), (25 + rng.uniform(-3, 3), 38)])
        assert not (s.proximal & s.distal).any()
        assert np.array_equal(s.proximal | s.distal, m)


def test_erros_de_eixo():
    m = mascara_roi(RET, 30, 30)
    with pytest.raises(ValueError):
        segmentar_por_eixo(m, [(15, 4)])
    with pytest.raises(ValueError):
        segmentar_por_eixo(m, [(15, 4), (15, 5)])
    with pytest.raises(ValueError):
        segmentar_por_eixo(np.zeros((30, 30), bool), [(15, 4), (15, 24)])


# ------------------------------------------------------- eixo automático
def _estomago(n=128):
    """Forma de estômago: fundo arredondado e corpo/antro curvo afinando para a esquerda e para baixo."""
    import math

    yy, xx = np.mgrid[0:n, 0:n] + 0.5
    m = (xx - 78) ** 2 / 16**2 + (yy - 34) ** 2 / 18**2 <= 1
    for t in np.linspace(0, 1, 400):
        cx, cy = 78 - 50 * t**1.3, 40 + 52 * math.sin(t * math.pi / 2)
        m |= (xx - cx) ** 2 + (yy - cy) ** 2 <= (13 - 6 * t) ** 2
    return m


def test_eixo_automatico_retangulo_divide_ao_meio():
    m = mascara_roi(RET, 30, 30)
    s = segmentar_por_eixo(m, eixo_automatico(m))
    assert s.proximal.sum() == s.distal.sum() == 100
    assert s.proximal[4:14, 10:20].all()


def test_eixo_automatico_elipse_centrado():
    yy, xx = np.mgrid[0:128, 0:128] + 0.5
    m = (xx - 64) ** 2 / 30**2 + (yy - 64) ** 2 / 45**2 <= 1
    e = eixo_automatico(m)
    s = segmentar_por_eixo(m, e)
    assert s.meio == pytest.approx((64, 64), abs=1.5)
    assert e[0][1] < 22 and e[-1][1] > 106  # vai de ponta a ponta do eixo maior
    assert abs(int(s.proximal.sum()) - int(s.distal.sum())) <= 0.03 * m.sum()


def test_eixo_automatico_estomago_do_fundo_ao_antro():
    m = _estomago()
    e = eixo_automatico(m)
    s = segmentar_por_eixo(m, e)
    assert e[0][1] < 20 and abs(e[0][0] - 78) < 6  # topo do fundo
    assert e[-1][0] < 35 and e[-1][1] > 85  # extremidade distal
    fundo = m[16:30, 70:86]
    assert s.proximal[16:30, 70:86][fundo].all()  # fundo todo proximal
    assert not s.proximal[85:, :40].any()  # antro todo distal
    xs = np.array([p[0] for p in e])
    ys = np.array([p[1] for p in e])
    assert m[np.floor(ys).astype(int).clip(0, 127), np.floor(xs).astype(int).clip(0, 127)].all()  # eixo dentro da ROI


def test_eixo_automatico_em_j():
    corpo = mascara_roi([(30, 0), (40, 0), (40, 40), (30, 40)], 50, 50)
    antro = mascara_roi([(0, 30), (40, 30), (40, 40), (0, 40)], 50, 50)
    m = corpo | antro
    e = eixo_automatico(m)
    s = segmentar_por_eixo(m, e)
    assert e[0][1] < 2 and e[-1][0] < 2  # do topo do corpo à ponta do antro
    assert s.proximal[0:20, 30:40].all() and s.distal[30:40, 0:20].all()


def test_eixo_automatico_acompanha_translacao():
    m = _estomago()
    e1 = eixo_automatico(m)
    e2 = eixo_automatico(np.roll(np.roll(m, 5, axis=0), -7, axis=1))
    assert np.allclose(np.array(e1) + [-7, 5], np.array(e2))


def test_eixo_automatico_roi_minuscula():
    m = np.zeros((10, 10), bool)
    m[4, 4] = True
    with pytest.raises(ValueError):
        eixo_automatico(m)


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


def test_distal_e_total_menos_proximal():
    a = np.full((4, 4), 4.0)
    p = np.full((4, 4), 9.0)
    m = np.ones((4, 4), bool)
    prox = np.zeros((4, 4), bool)
    prox[:1] = True  # 4 de 16 pixels
    c = contagens_regionais(30, a, p, m, prox, m, prox)
    assert (c.total_ant, c.total_post) == (64, 144)
    assert c.mg_total == 96  # √(64 × 144)
    assert c.mg_proximal == 24  # √(16 × 36)
    assert c.mg_distal == 72  # 96 − 24


def _cr(minutos, total, prox):
    return ContagensRegionais(minutos, total, total, prox, prox, total, prox, total - prox)


def test_tabela_valores_esperados():
    linhas = calcular_resultados([_cr(0, 1000, 800), _cr(60, 600, 300), _cr(120, 250, 50)], meia_vida_h=None)
    assert [l.rotulo for l in linhas] == ["T0", "T1", "T2"]
    assert [round(l.retencao, 6) for l in linhas] == [100, 60, 25]
    assert [round(l.esvaziamento, 6) for l in linhas] == [0, 40, 75]
    assert [round(l.distribuicao_proximal, 6) for l in linhas] == [80, 50, 20]
    assert [round(l.razao_pd, 6) for l in linhas] == [4, 1, 0.25]
    assert [round(l.retencao_proximal, 6) for l in linhas] == [80, 30, 5]
    assert [round(l.retencao_distal, 6) for l in linhas] == [20, 30, 20]


def test_razao_nao_avaliavel_abaixo_de_5_porcento():
    linhas = calcular_resultados([_cr(0, 1000, 800), _cr(240, 40, 20)], meia_vida_h=None)
    assert linhas[1].retencao == pytest.approx(4)
    assert linhas[1].razao_pd is None and not linhas[1].regional_avaliavel
    assert linhas[0].regional_avaliavel


def test_invariantes_da_tabela():
    """Retenção + esvaziamento = 100; proximal + distal = retenção; distal = total − proximal; nada negativo."""
    rng = np.random.default_rng(11)
    m = np.zeros((20, 20), bool)
    m[2:18, 5:15] = True
    s = segmentar_por_eixo(m, [(10, 2), (10, 18)])
    for _ in range(20):
        tempos = []
        for t in (0, 60, 120, 240):
            a = rng.uniform(100, 10_000, (20, 20))
            p = a * rng.uniform(0.5, 1.2)
            tempos.append(contagens_regionais(t, a, p, m, s.proximal, m, s.proximal))
        for meia_vida in (None, 6.0067):
            for c, l in zip(tempos, calcular_resultados(tempos, meia_vida)):
                assert l.retencao + l.esvaziamento == pytest.approx(100)
                assert l.retencao_proximal + l.retencao_distal == pytest.approx(l.retencao)
                assert l.mg_proximal + l.mg_distal == pytest.approx(l.mg_total)
                assert 0 <= l.distribuicao_proximal <= 100
                assert l.retencao_proximal >= 0 and l.retencao_distal >= -1e-9


def test_tabela_vazia():
    assert calcular_resultados([], None) == []


# ------------------------------------------------------------ referências
@pytest.mark.parametrize(
    "faixa, refeicao, minutos, retencao, dentro",
    [
        ("adulto", None, 60, 90.0, True),  # p95 inclusivo
        ("adulto", None, 62, 90.5, False),
        ("adulto", None, 120, 60.0, True),
        ("adulto", None, 240, 10.5, False),
        ("pediatrico", "ovo", 60, 89.9, True),  # esvaziamento 10,1% > 10%
        ("pediatrico", "ovo", 60, 90.0, False),  # esvaziamento 10% não é > 10%
        ("pediatrico", "ovo", 60, 29.0, False),  # esvaziamento 71% não é < 70%
        ("pediatrico", "ovo", 120, 59.0, True),  # esvaziamento 41% > 40%
        ("pediatrico", "ovo", 240, 10.0, False),  # esvaziamento 90% não é > 90%
        ("pediatrico", "aveia", 60, 49.0, True),  # esvaziamento 51% > 50%
    ],
)
def test_comparacao_com_referencia(faixa, refeicao, minutos, retencao, dentro):
    assert referencias.comparar(referencias.obter(faixa, refeicao), minutos, retencao)["dentro"] is dentro


def test_fora_da_tolerancia_de_tempo_sem_comparacao():
    ref = referencias.obter("adulto")
    assert referencias.comparar(ref, 90, 50) is None
    assert referencias.comparar(ref, 60 + referencias.TOLERANCIA_MIN, 50) is not None
    assert referencias.comparar(None, 60, 50) is None
    assert referencias.comparar(referencias.obter("pediatrico", "aveia"), 120, 30) is None
