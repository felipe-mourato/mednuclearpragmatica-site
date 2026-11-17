"""Testes da função do VE no gated (mnp_nucleo.perfusao.gated) e da integração na sessão.

Referência: o fantoma batendo (mnp_nucleo.fantomas.fantoma_perfusao) tem
volumes verdadeiros calculados pela fórmula do elipsoide truncado.
"""

import json

import numpy as np
import pytest

from mnp_nucleo.fantomas import GEOMETRIA_DIASTOLE, fantoma_perfusao, geometria_no_ciclo, volume_elipsoide_truncado
from mnp_nucleo.perfusao import eixos, gated
from mnp_nucleo.perfusao.aquisicao import ler_aquisicao
from mnp_nucleo.perfusao.reconstrucao import Filtro, reconstruir
from mnp_nucleo.perfusao.sessao import Sessao


def cmd(s, **kw):
    return json.loads(s.executar(kw))


@pytest.fixture(scope="module")
def fp():
    return fantoma_perfusao()


def _analise(fp, estudo):
    aq = ler_aquisicao(fp.arquivos[f"gated_{estudo}.dcm"])
    vols = [reconstruir(aq, Filtro(), k) for k in range(aq.n_intervalos)]
    e = eixos.marcacoes_de_eixo(vols[0], np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
    return gated.analisar_gated(vols, aq.projecoes.sum(axis=(1, 2, 3)), e), e


@pytest.fixture(scope="module")
def repouso(fp):
    return _analise(fp, "repouso")[0]


@pytest.fixture(scope="module")
def estresse(fp):
    return _analise(fp, "estresse")[0]


# ------------------------------------------------------------- fantoma
def test_volume_elipsoide_truncado_formula():
    # sem truncar (s_b = −L): elipsoide inteiro 4/3 π R² L
    assert volume_elipsoide_truncado(40, 20, -40) == pytest.approx(4 / 3 * np.pi * 400 * 40)
    # metade (s_b = 0)
    assert volume_elipsoide_truncado(40, 20, 0) == pytest.approx(2 / 3 * np.pi * 400 * 40)


def test_fantoma_massa_constante_e_fe():
    d = GEOMETRIA_DIASTOLE
    for g in (0.0, 0.5, 1.0):
        assert geometria_no_ciclo(g).miocardio_ml == pytest.approx(d.miocardio_ml, rel=1e-9)
    fe = 100 * (1 - geometria_no_ciclo(1.0).cavidade_ml / d.cavidade_ml)
    assert 55 < fe < 65


def test_fantoma_verdade(fp):
    v = fp.verdade
    assert v["repouso"]["vdf_ml"] == pytest.approx(70.6, abs=0.2)
    assert v["tid"] > 1.1
    assert np.argmax(v["repouso"]["volumes_ml"]) == 0 and np.argmin(v["repouso"]["volumes_ml"]) == 3


# ------------------------------------------------------------- núcleo
@pytest.mark.parametrize("nome", ["repouso", "estresse"])
def test_fe_e_volumes_no_fantoma(fp, repouso, estresse, nome):
    r = {"repouso": repouso, "estresse": estresse}[nome]
    v = fp.verdade[nome]
    assert r.ed == 0 and r.es == 3
    assert r.fe == pytest.approx(v["fe"], abs=6.0)
    # O método do QGS, com a resolução do fantoma (filtro padrão), subestima os volumes; a FE, razão, fica perto.
    assert 0.55 * v["vdf_ml"] < r.vdf_ml < 1.05 * v["vdf_ml"]
    assert 0.40 * v["vsf_ml"] < r.vsf_ml < 1.10 * v["vsf_ml"]
    assert not r.avisos
    # curva com a forma do ciclo: cai até a sístole e volta
    vol = r.volumes_ml
    assert vol[0] > vol[1] > vol[3] < vol[5] < vol[7]


def test_plano_valvar(repouso, estresse):
    for r in (repouso, estresse):
        assert r.limiar_valva is not None and 0.25 <= r.limiar_valva <= 0.75
        ed, es = r.planos_mm[r.ed][0], r.planos_mm[r.es][0]
        assert es <= ed + 1.0  # o plano não sobe para a base na sístole (verdade: desce 8 mm)
        assert 40.0 < ed < 90.0


def test_motilidade_e_espessamento_plausiveis(repouso):
    seg = repouso.segmentos()
    mot = np.array([seg[s]["motilidade_mm"] for s in range(1, 18)])
    esp = np.array([seg[s]["espessamento"] for s in range(1, 18)])
    assert np.all(mot > 2) and np.all(mot < 14)
    # verdade no equador: parede de ~9 para ~14 mm (≈ 50%)
    assert 25 < np.median(esp) < 80
    assert np.all(esp > 0)


def test_tid_maior_no_estresse_dilatado(fp):
    e_est = _analise(fp, "estresse")[1]
    v_est = gated.volume_nao_sincronizado(reconstruir(ler_aquisicao(fp.arquivos["estresse.dcm"]), Filtro()), e_est)
    v_rep = gated.volume_nao_sincronizado(reconstruir(ler_aquisicao(fp.arquivos["repouso.dcm"]), Filtro()), e_est)
    assert gated.calcular_tid(v_est, v_rep) > 1.04
    assert gated.calcular_tid(v_rep, v_rep) == 1.0
    with pytest.raises(ValueError):
        gated.calcular_tid(10, 0)


def test_malha_formato(repouso):
    m = repouso.malha()
    linhas, az = m["linhas"], m["azimutes"]
    assert len(m["endo"]) == 8
    assert np.array(m["endo"][0]).shape == (linhas, az, 3)
    assert np.array(m["epi_ed"]).shape == (linhas, az, 3)
    # o epicárdio fica fora do endocárdio
    endo, epi = np.array(m["endo"][0]), np.array(m["epi_ed"])
    r_endo = np.hypot(endo[gated.N_APICE:, :, 0], endo[gated.N_APICE:, :, 1])
    r_epi = np.hypot(epi[gated.N_APICE:, :, 0], epi[gated.N_APICE:, :, 1])
    assert np.all(r_epi > r_endo)


def test_gated_curto_recusado(fp):
    aq = ler_aquisicao(fp.arquivos["gated_repouso.dcm"])
    v = reconstruir(aq, Filtro(), 0)
    e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
    with pytest.raises(ValueError):
        gated.analisar_gated([v, v, v], [1, 1, 1], e)


def test_escores_de_funcao():
    assert gated.escores_funcao({1: 0}, "motilidade") is None
    todos = {s: 1 for s in range(1, 18)}
    assert gated.escores_funcao(todos, "motilidade") == {"soma": 17, "percentual": 20.0}
    assert gated.escores_funcao({str(s): 3 for s in range(1, 18)}, "espessamento") == {"soma": 51, "percentual": 100.0}
    assert gated.validar_escore_funcao("motilidade", 5) == 5
    with pytest.raises(ValueError):
        gated.validar_escore_funcao("espessamento", 4)
    with pytest.raises(ValueError):
        gated.validar_escore_funcao("motilidade", -1)


def test_superficie_corporal_mosteller():
    assert gated.superficie_corporal(70, 170) == pytest.approx(np.sqrt(70 * 170 / 3600))
    with pytest.raises(ValueError):
        gated.superficie_corporal(0, 170)


# ------------------------------------------------------------- sessão
@pytest.fixture(scope="module")
def sessao(fp):
    s = Sessao()
    for nome, dados in fp.arquivos.items():
        s.adicionar_arquivo(nome, dados)
    assert set(s.gated_disponiveis()) == {"estresse", "repouso"}
    cmd(s, acao="eixo_fantoma")
    return s


def test_sessao_funcao(sessao, fp):
    r = cmd(sessao, acao="funcao")
    assert r["ok"], r
    f = r["funcao"]
    for e in ("estresse", "repouso"):
        d = f["estudos"][e]
        assert d["fe"] == pytest.approx(fp.verdade[e]["fe"], abs=6.0)
        assert set(d["mapas"]) == {"motilidade", "espessamento"}
        assert len(d["mapas"]["motilidade"]["segmentos"]) == 17
        assert len(d["malha"]["endo"]) == 8
    assert f["tid"]["tid"] > 1.03
    assert f["superficie_corporal"] is None


def test_sessao_antropometria_e_indices(sessao):
    assert cmd(sessao, acao="definir_antropometria", peso=70, altura=170)["ok"]
    f = cmd(sessao, acao="funcao", com_malha=False)["funcao"]
    sc = np.sqrt(70 * 170 / 3600)
    d = f["estudos"]["repouso"]
    assert d["indices"]["vdf_ml_m2"] == pytest.approx(d["vdf_ml"] / sc, abs=0.15)
    assert "malha" not in d
    assert not cmd(sessao, acao="definir_antropometria", peso=1, altura=170)["ok"]
    cmd(sessao, acao="definir_antropometria", peso=None, altura=None)
    assert cmd(sessao, acao="funcao", com_malha=False)["funcao"]["superficie_corporal"] is None


def test_sessao_escores_funcao(sessao):
    assert cmd(sessao, acao="pontuar_funcao_todos", tipo="motilidade", estudo="estresse", escore=0)["ok"]
    assert cmd(sessao, acao="pontuar_funcao", tipo="motilidade", estudo="estresse", segmento=5, escore=3)["ok"]
    assert not cmd(sessao, acao="pontuar_funcao", tipo="espessamento", estudo="estresse", segmento=5, escore=4)["ok"]
    assert cmd(sessao, acao="copiar_escores_funcao", tipo="motilidade", de="estresse", para="repouso")["ok"]
    f = cmd(sessao, acao="funcao", com_malha=False)["funcao"]
    assert f["estudos"]["repouso"]["somas"]["sms"] == {"soma": 3, "percentual": round(300 / 85, 1)}
    assert f["estudos"]["estresse"]["somas"]["sts"] is None
    assert cmd(sessao, acao="pontuar_funcao", tipo="motilidade", estudo="repouso", segmento=5, escore=None)["ok"]
    assert cmd(sessao, acao="funcao", com_malha=False)["funcao"]["estudos"]["repouso"]["somas"]["sms"] is None


def test_sessao_imagens_gated(sessao):
    info = cmd(sessao, acao="cortes")["cortes"]["repouso"]["tipos"]["SA"]
    b = sessao.imagem({"fonte": "faixa_gated", "estudo": "repouso", "tipo": "SA", "intervalo": 3})
    assert len(b) == info["largura"] * info["altura"] * 4
    p = sessao.imagem({"fonte": "polar_funcao", "estudo": "repouso", "tipo": "espessamento", "com_escores": True})
    assert len(p) == 256 * 256 * 4
    with pytest.raises(Exception):
        sessao.imagem({"fonte": "polar_funcao", "estudo": "repouso", "tipo": "outro"})


def test_sessao_laudo_e_exportacao_com_gated(sessao):
    pixel = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    r = cmd(sessao, acao="laudo", paciente="Teste", malhas=[{"rotulo": "Repouso", "png": "data:image/png;base64," + pixel},
                                                             {"rotulo": "ruim", "png": "javascript:alert(1)"}])
    assert r["ok"], r
    h = r["html"]
    assert "Função ventricular (gated)" in h and "TID" in h and "Germano G, Erel J" in h
    assert h.count('class="laudo-malha-img"') == 1
    assert "javascript:" not in h
    csv = sessao.exportar({"formato": "csv"}).decode("utf-8")
    assert "FE (%)" in csv and "TID" in csv
    assert sessao.exportar({"formato": "xlsx"})[:2] == b"PK"
    png = sessao.exportar({"formato": "png_polar_funcao", "estudo": "estresse", "tipo": "motilidade"})
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


def test_protocolo_guarda_escores_de_funcao(sessao, fp):
    prot = sessao.protocolo()
    assert prot["escores_funcao"]["motilidade"]["estresse"]["5"] == 3
    s2 = Sessao.de_protocolo(prot, lambda n, h: fp.arquivos[n])
    assert s2.escores_funcao["motilidade"]["estresse"][5] == 3
    assert "peso_kg" not in json.dumps(prot)


def test_eixo_novo_descarta_resultado_do_gated(sessao):
    antes = sessao.funcao("repouso")
    e = sessao.eixos["repouso"]
    cmd(sessao, acao="definir_eixo", estudo="repouso", corte=e.corte_transaxial, base_1=e.base_1, apice_1=e.apice_1,
        base_2=e.base_2, apice_2=e.apice_2)
    assert sessao.funcao("repouso") is not antes


def test_sem_gated_funcao_vazia(fp):
    s = Sessao()
    for n in ("estresse.dcm", "repouso.dcm"):
        s.adicionar_arquivo(n, fp.arquivos[n])
    cmd(s, acao="eixo_fantoma")
    f = cmd(s, acao="funcao")["funcao"]
    assert f["estudos"] == {}
    assert f["tid"]["tid"] > 1.0


def test_elipsoide_recupera_semieixos():
    rng = np.random.default_rng(1)
    u = rng.normal(size=(800, 3))
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    R = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    pts = (u * [40.0, 25.0, 20.0]) @ R.T + [10.0, -5.0, 3.0]
    pts = pts[pts @ R[:, 0] - np.array([10.0, -5.0, 3.0]) @ R[:, 0] > -25]  # base aberta, como o VE
    c, Q, semi, vec = gated.ajustar_elipsoide(pts)
    assert np.allclose(sorted(semi), [20.0, 25.0, 40.0], atol=0.5)
    assert np.allclose(c, [10.0, -5.0, 3.0], atol=0.5)


def test_detector_segunda_derivada():
    x = np.arange(-30, 31, 1.0)
    k = gated._detector(x)
    assert abs(k.sum()) < 1e-3 and np.argmax(k) == 30
    assert k[30] > 0 and k[0] < 0.01


def test_gaussiana_assimetrica_recupera_sigmas():
    x = np.arange(-20, 21, 1.0)
    y = 5.0 + 100.0 * np.exp(-((x - 1.5) ** 2) / (2 * np.where(x < 1.5, 4.0, 7.0) ** 2))
    th = gated._gaussiana_assimetrica(np.stack([y, y * 2]), x)
    assert np.allclose(th[:, 2], 4.0, atol=0.05) and np.allclose(th[:, 3], 7.0, atol=0.05)
    assert np.allclose(th[:, 1], 1.5, atol=0.05)


def test_segmentacao_do_fantoma(fp):
    v = reconstruir(ler_aquisicao(fp.arquivos["repouso.dcm"]), Filtro())
    e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
    m, cubo, avisos = gated.segmentar(v, e)
    ml = m.sum() * cubo.passo**3 / 1000.0
    assert 60 < ml < 300 and not avisos  # miocárdio verdadeiro ≈ 92 mL, borrado pela resolução


def test_contornos_na_sessao(sessao):
    info = cmd(sessao, acao="funcao", com_malha=False)["funcao"]["contornos"]
    b = sessao.imagem({"fonte": "contornos", "estudo": "repouso", "intervalo": 0})
    assert len(b) == info["largura"] * info["altura"] * 4
