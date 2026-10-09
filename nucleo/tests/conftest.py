import json

import pytest

from mnp_nucleo.fantomas import fantoma_esvaziamento
from mnp_nucleo.gastrico.sessao import Sessao


@pytest.fixture
def fantoma():
    return fantoma_esvaziamento()


def comando(sessao, **kw):
    """Executa um comando na sessão e devolve a resposta já como dict."""
    return json.loads(sessao.executar(kw))


@pytest.fixture
def sessao_pronta(fantoma):
    """Sessão com o fantoma carregado, ROI e eixo desenhados no T0 (copiados para os demais)."""
    s = Sessao()
    for nome, dados in fantoma.arquivos.items():
        s.adicionar_arquivo(nome, dados)
    r = comando(s, acao="desenhar_roi", tempo=0, pontos=fantoma.roi)
    assert r["ok"], r
    r = comando(s, acao="desenhar_eixo", tempo=0, pontos=fantoma.eixo)
    assert r["ok"], r
    return s
