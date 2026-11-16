"""Testes da perfusão miocárdica (núcleo mnp_nucleo.perfusao) e do JPEG sem perdas.

Valores esperados calculados à mão a partir da geometria dos fantomas e
das fórmulas das diretrizes (ver mnp_nucleo/perfusao/referencias.py).
"""

import io
import json
import math

import numpy as np
import pytest
from pydicom import dcmread

from mnp_nucleo.comum.dicom import ErroDicom, ler_dicom
from mnp_nucleo.comum.jpeg_sem_perdas import ErroJpeg, decodificar_jpeg_sem_perdas
from mnp_nucleo.fantomas import codificar_jpeg_sem_perdas, fantoma_perfusao, fantoma_ponto, gerar_dicom, gerar_dicom_nm
from mnp_nucleo.perfusao import controle, eixos, escores, figuras, polar
from mnp_nucleo.perfusao.aquisicao import adivinhar_tipo, direcao_coluna, ler_aquisicao
from mnp_nucleo.perfusao.lote import main as lote_main
from mnp_nucleo.perfusao.reconstrucao import Filtro, butterworth, fbp, filtrar_projecoes, nucleo_rampa, reconstruir
from mnp_nucleo.perfusao.sessao import Sessao


def cmd(s, **kw):
    return json.loads(s.executar(kw))


@pytest.fixture(scope="module")
def fp():
    return fantoma_perfusao()


@pytest.fixture(scope="module")
def sem_ruido():
    return fantoma_perfusao(ruido=False)


# ----------------------------------------------------------- JPEG sem perdas
@pytest.mark.parametrize("forma", [(1, 1), (5, 7), (64, 64)])
def test_jpeg_ida_e_volta_exata(forma):
    rng = np.random.default_rng(1)
    q = rng.integers(0, 65536, size=forma)
    assert np.array_equal(decodificar_jpeg_sem_perdas(codificar_jpeg_sem_perdas(q)), q)


def test_jpeg_diferencas_extremas():
    # diferença de −32768 (categoria 16) e saltos máximos
    q = np.array([[0, 32768, 0, 65535, 0], [65535, 0, 65535, 1, 32767]])
    assert np.array_equal(decodificar_jpeg_sem_perdas(codificar_jpeg_sem_perdas(q)), q)


def test_jpeg_igual_ao_pylibjpeg_quando_disponivel():
    pytest.importorskip("pylibjpeg")
    pytest.importorskip("libjpeg")
    dados = gerar_dicom_nm(np.random.default_rng(3).poisson(40, size=(64, 16, 16)), "Teste", comprimir=True)
    ds = dcmread(io.BytesIO(dados))
    ref = ds.pixel_array
    from pydicom.encaps import generate_frames

    meus = np.stack([decodificar_jpeg_sem_perdas(f) for f in generate_frames(ds.PixelData, number_of_frames=64)])
    assert np.array_equal(meus, ref)


def test_jpeg_erros_claros():
    with pytest.raises(ErroJpeg, match="SOI"):
        decodificar_jpeg_sem_perdas(b"\x00\x01\x02\x03")
    bom = codificar_jpeg_sem_perdas(np.zeros((4, 4), dtype=int))
    with pytest.raises(ErroJpeg):
        decodificar_jpeg_sem_perdas(bom.replace(b"\xff\xc3", b"\xff\xc0"))


def test_ler_dicom_comprimido_sem_perdas_nas_outras_ferramentas():
    """A leitura comum (gástrico e DMSA) passa a aceitar JPEG sem perdas, com os mesmos pixels."""
    q = np.arange(64 * 64).reshape(64, 64) % 1000
    nm = gerar_dicom_nm(np.stack([q] * 64)[None].repeat(1, axis=0)[0], "x", comprimir=True)
    img = ler_dicom(nm)
    assert img.n_quadros == 64
    assert np.array_equal(img.quadros[0], q.astype(float))


# ---------------------------------------------------------------- aquisição
def test_angulos_e_direcoes(fp):
    aq = ler_aquisicao(fp.arquivos["repouso.dcm"])
    # detector 1 começa em 225° e o 2 em 135°, 32 vistas de 2,8125° cada, sentido horário (ângulo diminui)
    esperados = sorted([(225 - v * 2.8125) % 360 for v in range(32)] + [(135 - v * 2.8125) % 360 for v in range(32)])
    assert np.allclose(aq.angulos, esperados)
    assert aq.angulos[0] == pytest.approx(47.8125) and aq.angulos[-1] == pytest.approx(225.0)
    assert aq.info["arco_graus"] == pytest.approx(180.0)
    # u(225°) = (−cos 225°, sen 225°) = (0,7071; −0,7071): coluna cresce para a esquerda e para a frente
    assert np.allclose(direcao_coluna(225.0), [math.sqrt(0.5), -math.sqrt(0.5)])
    assert np.allclose(aq.u[-1], [math.sqrt(0.5), -math.sqrt(0.5)])
    assert aq.passo_z == -1.0 and not aq.gated and aq.n_intervalos == 1


def test_gated_lido_por_intervalo(fp):
    aq = ler_aquisicao(fp.arquivos["gated_estresse.dcm"])
    assert aq.gated and aq.n_intervalos == 8 and aq.n_angulos == 64
    g = aq.info_gated
    assert g["batimentos_aceitos"] == 610 and g["batimentos_rejeitados"] == 95
    assert g["percentual_rejeitado"] == pytest.approx(round(100 * 95 / 705, 1))
    pct = controle.contagens_por_intervalo(aq)["percentual_da_media"]
    # pesos 1,1,1,1,1,1,0,9,0,6 (média 0,9375): último ≈ 64%, primeiros ≈ 106,7%
    assert pct[-1] == pytest.approx(100 * 0.6 / 0.9375, abs=1.0)
    assert pct[0] == pytest.approx(100 * 1 / 0.9375, abs=1.0)


def test_estresse_comprimido_igual_ao_sem_compressao(sem_ruido):
    a = ler_aquisicao(sem_ruido.arquivos["estresse.dcm"])  # JPEG sem perdas
    assert "JPEG" in a.sintaxe
    assert a.somadas().sum() > 0


@pytest.mark.parametrize(
    "descricao, gated, posicao, esperado",
    [("Stress", False, "FFS", "estresse"), ("REST", False, "FFS", "repouso"), ("Repouso gated", True, "HFS", "gated_repouso"),
     ("Stress", False, "FFP", "prona_estresse"), ("Prone rest", False, "FFS", "prona_repouso"), ("", True, "FFS", "gated_estresse")],
)
def test_adivinhar_tipo(descricao, gated, posicao, esperado):
    assert adivinhar_tipo(descricao, gated, posicao) == esperado


def test_recusa_reconstruido_e_sem_vetores():
    q = np.zeros((4, 4), dtype=np.uint16)
    with pytest.raises(ErroDicom, match="projeções"):
        ler_aquisicao(gerar_dicom([q, q]))  # Secondary Capture sem vetores
    dados = gerar_dicom_nm(np.zeros((64, 8, 8)), "x")
    ds = dcmread(io.BytesIO(dados))
    ds.ImageType = ["DERIVED", "SECONDARY", "RECON TOMO", "EMISSION"]
    b = io.BytesIO()
    ds.save_as(b)
    with pytest.raises(ErroDicom, match="reconstruído"):
        ler_aquisicao(b.getvalue())


# ------------------------------------------------------------- reconstrução
def test_butterworth_valores():
    assert butterworth(0.0, 0.2, 5) == pytest.approx(1.0)
    assert butterworth(0.2, 0.2, 5) == pytest.approx(0.5)
    assert butterworth(0.4, 0.2, 1) == pytest.approx(1 / (1 + 4))
    f = Filtro(0.45, 11)
    assert f.ciclos_pixel() == pytest.approx(0.225)
    assert f.ciclos_cm(6.4) == pytest.approx(0.225 / 0.64)


def test_filtro_preserva_soma_das_projecoes():
    rng = np.random.default_rng(0)
    p = rng.poisson(50, size=(3, 32, 32)).astype(float)
    q = filtrar_projecoes(p, Filtro(0.4, 8))
    assert q.sum(axis=(1, 2)) == pytest.approx(p.sum(axis=(1, 2)), rel=1e-9)


def test_filtro_validacao():
    with pytest.raises(ValueError):
        Filtro(1.5, 5).validar()
    with pytest.raises(ValueError):
        Filtro(0.5, 0).validar()


def test_rampa_sem_componente_continua():
    h = nucleo_rampa(128)
    assert abs(h[0]) < 5e-3 and h[-1] == pytest.approx(0.5, abs=0.02)


def test_fonte_pontual_no_lugar_certo_e_do_lado_certo():
    """Ponto em x = +40 mm (esquerda), y = −30 (anterior), z = +20 (cabeça)."""
    v = reconstruir(ler_aquisicao(fantoma_ponto((40.0, -30.0, 20.0))), Filtro(0.8, 10))
    k, i, j = np.unravel_index(np.argmax(v.dados), v.dados.shape)
    pos = v.para_mm(k, i, j)
    assert np.all(np.abs(pos - [40, -30, 20]) <= 6.4)  # até 1 pixel
    c = (v.n - 1) / 2
    assert j > c  # lado esquerdo do paciente à direita da imagem
    assert i < c  # anterior em cima


def test_disco_uniforme_reconstruido_plano():
    n = 64
    ang = np.arange(128) * 180.0 / 128
    u = direcao_coluna(ang)
    raio = 20.0
    t = np.arange(n) - (n - 1) / 2
    corda = 2 * np.sqrt(np.clip(raio**2 - t**2, 0, None))
    proj = np.tile(corda, (len(ang), 1, 1))
    v = fbp(proj, u, 1.0)[0]
    c = (n - 1) / 2
    yy, xx = np.mgrid[0:n, 0:n] - c
    dentro = np.hypot(xx, yy) < raio - 4
    assert v[dentro].std() / v[dentro].mean() < 0.03
    assert v[dentro].mean() == pytest.approx(1.0, rel=0.05)


# --------------------------------------------------------------------- eixos
def test_base_vetorial_ortonormal_e_orientacao():
    a, w, h = eixos.base_vetorial([0, 0, 0], [1, -1, -0.5])
    m = np.stack([a, w, h])
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert w[2] > 0  # anterior/superior em cima
    assert h[0] > 0 and h[1] > 0  # lateral: para a esquerda e para trás


def test_eixo_ida_e_volta(fp):
    v = reconstruir(ler_aquisicao(fp.arquivos["repouso.dcm"]), Filtro())
    b, a = np.array(fp.eixo["base"]), np.array(fp.eixo["apice"])
    e = eixos.marcacoes_de_eixo(v, b, a)
    e2 = eixos.eixo_de_marcacoes(v, e.corte_transaxial, e.base_1, e.apice_1, e.base_2, e.apice_2)
    assert np.allclose(e2.base, b, atol=1e-6) and np.allclose(e2.apice, a, atol=1e-6)


def test_exibicao_nao_muda_volume(fp):
    v = reconstruir(ler_aquisicao(fp.arquivos["repouso.dcm"]), Filtro())
    antes = v.dados.copy()
    e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
    _, ims = eixos.cortes(v, e, "SA")
    figuras.faixa_rgba(ims, 1.0, "quente")
    assert np.array_equal(antes, v.dados)


# --------------------------------------------------------------------- polar
@pytest.mark.parametrize(
    "rho, ang, esperado",
    [(0.05, 10, 17), (0.5, 90, 7), (0.5, 150, 8), (0.5, 210, 9), (0.5, 270, 10), (0.5, 330, 11), (0.5, 30, 12),
     (0.95, 90, 1), (0.95, 150, 2), (0.95, 210, 3), (0.95, 270, 4), (0.95, 330, 5), (0.95, 30, 6),
     (0.3, 90, 13), (0.3, 180, 14), (0.3, 270, 15), (0.3, 0, 16)],
)
def test_segmentos_no_mapa(rho, ang, esperado):
    # ápice até 0,2; apical 0,2–0,467; médio até 0,733; basal até 1
    assert polar.segmento_em(rho, ang, 0.2) == esperado


def test_territorios():
    assert polar.TERRITORIOS["DA"] == (1, 2, 7, 8, 13, 14, 17)
    assert polar.TERRITORIOS["CD"] == (3, 4, 9, 10, 15)
    assert polar.TERRITORIOS["Cx"] == (5, 6, 11, 12, 16)
    assert sorted(s for t in polar.TERRITORIOS.values() for s in t) == list(range(1, 18))


def test_defeito_lateral_aparece_nos_segmentos_certos(fp):
    """Estresse: lateral basal e médio a 50% (5, 6, 11, 12). Espelhamento poria o defeito no septo."""
    val = {}
    for nome in ("estresse.dcm", "repouso.dcm"):
        v = reconstruir(ler_aquisicao(fp.arquivos[nome]), Filtro())
        e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
        val[nome] = polar.amostrar_polar(v, e).valores_segmentos()
    est, rep = val["estresse.dcm"], val["repouso.dcm"]
    for s in (5, 6, 11, 12):
        assert est[s] < 0.8 * rep[s], s
    for s in (2, 3, 8, 9, 14, 17):  # septo e ápice: iguais ao repouso
        assert est[s] == pytest.approx(rep[s], abs=8), s
    assert min(est[s] for s in (5, 6, 11, 12)) < min(est[s] for s in (2, 3, 8, 9))


def test_imagem_polar_e_contornos():
    mp = polar.MapaPolar(np.full((24, 72), 80.0), np.full((12, 72), 100.0), 1.0, 20.0, 0.25, (np.arange(72) + 0.5) * 5)
    img = mp.imagem(64)
    assert np.isnan(img[0, 0]) and img[32, 32] == pytest.approx(100.0) and img[32, 60] == pytest.approx(80.0)
    geo = polar.geometria_segmentos(0.25)
    assert [g["segmento"] for g in geo] == list(range(1, 18))
    vals = mp.valores_segmentos()
    assert vals[17] == 100.0 and vals[1] == 80.0


# -------------------------------------------------------------------- escores
def test_escores_a_mao():
    est = {s: 0 for s in range(1, 18)} | {5: 2, 6: 3, 11: 2, 12: 1}
    rep = {s: 0 for s in range(1, 18)} | {6: 1}
    r = escores.calcular_escores(est, rep)
    assert (r.sss, r.srs, r.sds) == (8, 1, 7)
    assert r.percentual(r.sss) == pytest.approx(800 / 68)
    assert r.territorios["Cx"]["estresse"] == 8 and r.territorios["Cx"]["repouso"] == 1
    assert r.territorios["DA"]["estresse"] == 0
    assert escores.faixa_sss(3).startswith("normal") and escores.faixa_sss(4).startswith("discretamente")
    assert escores.faixa_sss(13).startswith("moderadamente") and escores.faixa_sss(14).startswith("francamente")


def test_escores_incompletos_e_invalidos():
    r = escores.calcular_escores({1: 2}, {})
    assert r.sss is None and len(r.faltam_estresse) == 16 and r.avisos
    with pytest.raises(ValueError):
        escores.validar_escore(5)
    with pytest.raises(ValueError):
        escores.validar_escore(1.5)
    assert escores.calcular_escores({s: 0 for s in range(1, 18)} | {3: 1}, {s: 0 for s in range(1, 18)} | {3: 2}).avisos


# -------------------------------------------------------------------- sessão
@pytest.fixture(scope="module")
def sessao_pronta(fp):
    s = Sessao()
    for nome, dados in fp.arquivos.items():
        s.adicionar_arquivo(nome, dados)
    assert cmd(s, acao="reconstruir")["ok"]
    for estudo in ("estresse", "repouso"):
        v = s.volume(estudo)
        e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
        r = cmd(s, acao="definir_eixo", estudo=estudo, corte=e.corte_transaxial, base_1=e.base_1, apice_1=e.apice_1, base_2=e.base_2, apice_2=e.apice_2)
        assert r["ok"], r
    for seg in range(1, 18):
        cmd(s, acao="pontuar", estudo="estresse", segmento=seg, escore=2 if seg in (5, 6, 11, 12) else 0)
    cmd(s, acao="pontuar_todos", estudo="repouso", escore=0)
    return s


def test_sessao_tipos_e_validacao(fp):
    s = Sessao()
    r = json.loads(s.adicionar_arquivo("e.dcm", fp.arquivos["estresse.dcm"]))
    assert r["estado"]["arquivos"][0]["tipo"] == "estresse"
    r = json.loads(s.adicionar_arquivo("e2.dcm", fp.arquivos["estresse.dcm"]))
    assert "repetido" in r["estado"]["erros"][0]
    s.adicionar_arquivo("g.dcm", fp.arquivos["gated_repouso.dcm"])
    est = cmd(s, acao="estado")["estado"]
    assert [e["estudo"] for e in est["estudos"]] == ["estresse", "repouso"]
    assert est["estudos"][1]["de_gated"] and any("soma dos intervalos" in a for a in est["avisos"])
    r = cmd(s, acao="definir_tipo", arquivo=est["arquivos"][0]["id"], tipo="gated_estresse")
    assert not r["ok"] and "não é sincronizado" in r["erro"]


def test_sessao_resultados(sessao_pronta):
    r = cmd(sessao_pronta, acao="resultados")
    assert r["ok"], r
    resumo = {l["chave"]: l["valor"] for l in r["resumo"]}
    assert resumo == {"sss": 8, "srs": 0, "sds": 8}
    assert any(l["territorio"] == "Cx" and l["estresse"] == "8" for l in r["territorios"])
    p = cmd(sessao_pronta, acao="polar")["polar"]
    assert set(p["estudos"]) == {"estresse", "repouso"}
    c = cmd(sessao_pronta, acao="cortes")["cortes"]["estresse"]["tipos"]["SA"]
    b = sessao_pronta.imagem({"fonte": "faixa", "estudo": "estresse", "tipo": "SA"})
    assert len(b) == c["largura"] * c["altura"] * 4


def test_sessao_imagens_e_exportacoes(sessao_pronta):
    s = sessao_pronta
    a = cmd(s, acao="estado")["estado"]["arquivos"][0]
    assert len(s.imagem({"fonte": "projecao", "arquivo": a["id"], "indice": 3})) == 64 * 64 * 4
    assert len(s.imagem({"fonte": "sinograma", "arquivo": a["id"], "linha": 30})) == 64 * 64 * 4
    assert len(s.imagem({"fonte": "linograma", "arquivo": a["id"]})) == 64 * 64 * 4
    assert len(s.imagem({"fonte": "transaxial", "estudo": "estresse", "corte": 30})) == 64 * 64 * 4
    assert len(s.imagem({"fonte": "plano_vertical", "estudo": "estresse"})) == 64 * 64 * 4
    assert len(s.imagem({"fonte": "polar", "estudo": "estresse", "com_escores": True})) == 256 * 256 * 4
    assert s.exportar({"formato": "png_polar", "estudo": "estresse"}).startswith(b"\x89PNG")
    csv = s.exportar({"formato": "csv"}).decode("utf-8-sig")
    assert "SSS (estresse);8;11,8" in csv
    from openpyxl import load_workbook

    wb = load_workbook(io.BytesIO(s.exportar({"formato": "xlsx"})))
    assert wb.active["A1"].value.startswith("Cintilografia de perfusão")
    html = cmd(s, acao="laudo", paciente="Fulano", data_exame="16/11/2026")["html"]
    assert "Fulano" in html and "Desvio declarado" in html and "data:image/png;base64" in html
    assert "FANTOMA" not in html  # nada do cabeçalho do paciente


def test_qc_comando(sessao_pronta):
    est = cmd(sessao_pronta, acao="estado")["estado"]
    g = next(a for a in est["arquivos"] if a["tipo"] == "gated_estresse")
    q = cmd(sessao_pronta, acao="qc", arquivo=g["id"])["qc"]
    assert len(q["intervalos"]["contagens"]) == 8 and len(q["contagens_projecao"]) == 64


def test_filtro_muda_e_invalida_volumes(sessao_pronta, fp):
    s = Sessao()
    s.adicionar_arquivo("r.dcm", fp.arquivos["repouso.dcm"])
    v1 = s.volume("repouso").dados.copy()
    assert cmd(s, acao="definir_filtro", corte=0.3, ordem=5)["ok"]
    assert not np.allclose(v1, s.volume("repouso").dados)
    assert not cmd(s, acao="definir_filtro", corte=2, ordem=5)["ok"]


def test_copiar_eixo(fp):
    s = Sessao()
    for n in ("estresse.dcm", "repouso.dcm"):
        s.adicionar_arquivo(n, fp.arquivos[n])
    assert not cmd(s, acao="copiar_eixo", de="estresse", para="repouso")["ok"]
    v = s.volume("estresse")
    e = eixos.marcacoes_de_eixo(v, np.array(fp.eixo["base"]), np.array(fp.eixo["apice"]))
    cmd(s, acao="definir_eixo", estudo="estresse", corte=e.corte_transaxial, base_1=e.base_1, apice_1=e.apice_1, base_2=e.base_2, apice_2=e.apice_2)
    assert cmd(s, acao="copiar_eixo", de="estresse", para="repouso")["ok"]
    assert np.allclose(s.eixos["repouso"].base, s.eixos["estresse"].base)


def test_protocolo_e_lote(sessao_pronta, fp, tmp_path):
    for nome, dados in fp.arquivos.items():
        (tmp_path / nome).write_bytes(dados)
    prot = cmd(sessao_pronta, acao="protocolo")["protocolo"]
    (tmp_path / "p.json").write_text(json.dumps(prot), encoding="utf-8")
    assert lote_main([str(tmp_path / "p.json"), "--pasta", str(tmp_path), "--csv", str(tmp_path / "o.csv"), "--laudo", str(tmp_path / "l.html")]) == 0
    texto = (tmp_path / "o.csv").read_text(encoding="utf-8")
    assert "SSS" in texto and ",8,0,8," in texto
    original = sessao_pronta.mapa_polar("estresse").valores_segmentos()
    s2 = Sessao.de_protocolo(prot, lambda n, h: fp.arquivos[n])
    assert s2.mapa_polar("estresse").valores_segmentos() == original


def test_escala_fria_monotonica():
    t = np.linspace(0, 1, 11)
    rgb = figuras.colorir(t, 1.0, "fria").astype(float)
    lum = rgb @ [0.2126, 0.7152, 0.0722]
    assert np.all(np.diff(lum) > 0)
    assert tuple(rgb[0]) == (0, 0, 0) and tuple(rgb[-1]) == (255, 255, 255)
    assert rgb[5, 2] > rgb[5, 0]  # meio da escala: azul predomina


def test_sessao_aceita_mapa_fria(sessao_pronta):
    assert cmd(sessao_pronta, acao="definir_mapa", mapa="fria")["ok"]
    assert len(sessao_pronta.imagem({"fonte": "polar", "estudo": "estresse"})) == 256 * 256 * 4
    assert not cmd(sessao_pronta, acao="definir_mapa", mapa="arco-iris")["ok"]
    cmd(sessao_pronta, acao="definir_mapa", mapa="quente")
