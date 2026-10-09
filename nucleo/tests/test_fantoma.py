"""Ponta a ponta com fantomas sintéticos de contagens conhecidas."""

import numpy as np
import pytest

from mnp_nucleo.comum.contagens import soma_contagens
from mnp_nucleo.comum.dicom import ler_dicom
from mnp_nucleo.comum.roi import espelhar_horizontal, mascara_roi
from mnp_nucleo.fantomas import fantoma_esvaziamento
from mnp_nucleo.gastrico.sessao import Sessao

from .conftest import comando

TOL = 0.05  # pontos percentuais (arredondamento dos pixels para inteiros)


@pytest.mark.parametrize("decaimento", [True])
def test_retencao_e_distribuicao_recuperadas(sessao_pronta, fantoma, decaimento):
    linhas = sessao_pronta.resultados(decaimento, 6.0067)
    for l, r, d in zip(linhas, fantoma.retencao, fantoma.distribuicao):
        assert l.retencao == pytest.approx(r, abs=TOL)
        assert l.distribuicao_proximal == pytest.approx(d, abs=TOL)
        assert l.retencao_proximal == pytest.approx(r * d / 100, abs=TOL)


def test_sem_correcao_de_decaimento_subestima_pelo_fator_fisico(sessao_pronta, fantoma):
    linhas = sessao_pronta.resultados(False, None)
    for l, r, t in zip(linhas, fantoma.retencao, fantoma.minutos):
        assert l.retencao == pytest.approx(r * 2 ** (-t / (6.0067 * 60)), abs=TOL)


def test_independe_da_atenuacao_posterior():
    for att in (0.3, 0.8, 1.0):
        f = fantoma_esvaziamento(atenuacao_post=att)
        s = Sessao()
        for n, d in f.arquivos.items():
            s.adicionar_arquivo(n, d)
        s.desenhar_roi(0, f.roi)
        assert [round(l.retencao, 1) for l in s.resultados(True, 6.0067)] == [100.0, 60.0, 30.0, 8.0]


def test_espelhamento_posterior_obrigatorio(fantoma):
    """Sem espelhar, a ROI não pega nada na posterior; espelhada, pega o valor esperado."""
    post = ler_dicom(fantoma.arquivos["T0_post.dcm"]).quadro(0)
    m_direta = mascara_roi(fantoma.roi, 64, 64)
    m_espelho = mascara_roi(espelhar_horizontal(fantoma.roi, 64), 64, 64)
    assert soma_contagens(post, m_direta) == 0
    esperado = post.sum()  # todo o estômago posterior, fundo zero
    assert soma_contagens(post, m_espelho) == esperado > 0


def test_multiframe_frames_1_e_2_como_ant_pos(fantoma):
    s = Sessao()
    for n, d in fantoma.multiframe.items():
        s.adicionar_arquivo(n, d)
    e = comando(s, acao="estado")["estado"]
    assert len(e["sugestoes"]) == 4
    for sug in e["sugestoes"]:
        assert comando(s, acao="aceitar_multiframe", arquivo=sug["arquivo"])["ok"]
    e = comando(s, acao="estado")["estado"]
    assert len(e["tempos"]) == 4 and e["validacao"]["arquivos"] is None
    s.desenhar_roi(0, fantoma.roi)
    assert [round(l.retencao, 1) for l in s.resultados(True, 6.0067)] == [100.0, 60.0, 30.0, 8.0]


def test_rescale_nao_altera_resultado_relativo():
    """Inclinação de rescale multiplica todas as contagens: retenção não muda."""
    from mnp_nucleo.fantomas import gerar_dicom

    f = fantoma_esvaziamento()
    s = Sessao()
    for n, d in f.arquivos.items():
        img = ler_dicom(d)
        s.adicionar_arquivo(
            n, gerar_dicom(img.quadros[0].astype(np.int64), img.data_hora, img.descricao, bits=32, inclinacao=0.25)
        )
    s.desenhar_roi(0, f.roi)
    assert [round(l.retencao, 1) for l in s.resultados(True, 6.0067)] == [100.0, 60.0, 30.0, 8.0]
