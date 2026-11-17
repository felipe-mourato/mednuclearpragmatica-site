"""Sessão de processamento da cintilografia de perfusão miocárdica (SPECT).

Guarda o estado de um exame (arquivos e tipos, filtro, eixos, escores) e
responde a comandos em JSON. A interface web só envia comandos e desenha o
que recebe; toda a lógica fica aqui e é testada com pytest.

Parte 1: controle de qualidade, reconstrução, eixos, cortes, mapa polar e
escores visuais de perfusão. Parte 2 (gated): cada intervalo reconstruído
com o mesmo filtro e reorientado com o eixo do estudo (estresse ou
repouso), bordas do VE, volumes, FE, TID, mapas de motilidade e
espessamento e escores visuais de função (:mod:`.gated`). Se faltar a
aquisição não sincronizada, a soma dos intervalos do gated serve de imagem
de perfusão.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from .. import __version__, versoes
from ..comum import exibicao
from ..comum.dicom import ErroDicom
from ..comum.tabela import fmt_dec, fmt_int
from . import controle, eixos, figuras, gated, polar, relatorio
from .aquisicao import ROTULOS_TIPO, TIPOS, Aquisicao, adivinhar_tipo, ler_aquisicao
from .escores import calcular_escores, validar_escore
from .reconstrucao import CORTE_PADRAO, ORDEM_PADRAO, Filtro, Volume, butterworth, reconstruir

__all__ = ["Sessao", "ErroSessao", "ESTUDOS", "ROTULO_ESTUDO"]

#: Estudos de perfusão (volumes reconstruídos): os dois principais e as pronas.
ESTUDOS = ("estresse", "repouso", "prona_estresse", "prona_repouso")
ROTULO_ESTUDO = {"estresse": "Estresse", "repouso": "Repouso", "prona_estresse": "Prona do estresse", "prona_repouso": "Prona do repouso"}
PONTUADOS = ("estresse", "repouso")
#: Pares exibidos lado a lado: o eixo curto dos dois usa o mesmo comprimento (o maior).
PARES = (("estresse", "repouso"), ("prona_estresse", "prona_repouso"))
LADO_POLAR = 256
FATOR_CORTES = 4
#: Escores visuais de função (gated): motilidade 0–5 e espessamento 0–3.
TIPOS_FUNCAO = ("motilidade", "espessamento")
TETO_FUNCAO = {"motilidade": gated.MOTILIDADE_MAX, "espessamento": gated.ESPESSAMENTO_MAX}


class ErroSessao(ValueError):
    """Erro de uso com mensagem para o usuário."""


@dataclass
class Arquivo:
    id: str
    nome: str
    aq: Aquisicao
    tipo: str


def _ponto(p) -> tuple[float, float]:
    try:
        x, y = p
        return float(x), float(y)
    except (TypeError, ValueError):
        raise ErroSessao("Ponto inválido.") from None


class Sessao:
    """Estado de um exame de perfusão miocárdica em processamento."""

    def __init__(self) -> None:
        self.limpar()

    # ------------------------------------------------------------------ estado
    def limpar(self) -> None:
        self.arquivos: dict[str, Arquivo] = {}
        self.filtro = Filtro(CORTE_PADRAO, ORDEM_PADRAO)
        self.eixos: dict[str, eixos.Eixo] = {}
        self.escores: dict[str, dict[int, int | None]] = {e: {} for e in PONTUADOS}
        self.tetos: dict[str, float] = {}
        self.mapa = "quente"
        self.erros: list[str] = []
        self._contador = 0
        self._vol: dict = {}
        self._polar: dict = {}
        self._eixo_fonte: dict[str, str] = {}
        self.escores_funcao: dict[str, dict[str, dict[int, int]]] = {t: {e: {} for e in PONTUADOS} for t in TIPOS_FUNCAO}
        self.antropometria: dict[str, float] = {}
        self._vol_gated: dict = {}
        self._gated: dict = {}
        self._cortes_gated: dict = {}
        self._vol_tid: dict = {}

    def _novo_id(self, prefixo: str) -> str:
        self._contador += 1
        return f"{prefixo}{self._contador}"

    def _arquivo(self, id_: str) -> Arquivo:
        if id_ not in self.arquivos:
            raise ErroSessao("Arquivo não encontrado na sessão.")
        return self.arquivos[id_]

    # --------------------------------------------------------------- arquivos
    def adicionar_arquivo(self, nome: str, dados) -> str:
        nome = str(nome)
        try:
            aq = ler_aquisicao(dados)
        except ErroDicom as erro:
            self.erros.append(f"{nome}: {erro}")
            return self._resposta()
        except Exception:  # noqa: BLE001
            self.erros.append(f"{nome}: erro inesperado ao ler o arquivo.")
            return self._resposta()
        if any(a.aq.sha256 == aq.sha256 for a in self.arquivos.values()):
            self.erros.append(f"{nome}: arquivo repetido (já carregado).")
            return self._resposta()
        tipo = adivinhar_tipo(aq.descricao, aq.gated, aq.posicao_paciente)
        if any(a.tipo == tipo for a in self.arquivos.values()):
            tipo = "ignorar"
        id_ = self._novo_id("a")
        self.arquivos[id_] = Arquivo(id_, nome, aq, tipo)
        self._apos_mudanca()
        return self._resposta()

    def definir_tipo(self, arquivo: str, tipo: str) -> None:
        if tipo not in TIPOS:
            raise ErroSessao("Tipo de aquisição desconhecido.")
        a = self._arquivo(arquivo)
        if tipo.startswith("gated") and not a.aq.gated:
            raise ErroSessao("Este arquivo não é sincronizado (gated): escolha estresse, repouso ou prona.")
        a.tipo = tipo
        self._apos_mudanca()

    def remover_arquivo(self, arquivo: str) -> None:
        self._arquivo(arquivo)
        del self.arquivos[arquivo]
        self._apos_mudanca()

    def _apos_mudanca(self) -> None:
        """Descarta volumes, mapas e eixos de estudos cuja fonte mudou."""
        validos = {}
        for e in ESTUDOS:
            f = self._fonte(e)
            if f is not None:
                validos[e] = f[0].id
        for e in list(self.eixos):
            if e not in validos or self._eixo_fonte.get(e) != validos[e]:
                del self.eixos[e]
                self._eixo_fonte.pop(e, None)
        for chave in list(self._vol):
            if chave[0] not in validos or chave[1] != validos[chave[0]]:
                del self._vol[chave]
        self._polar.clear()
        self._limpar_gated()

    def _limpar_gated(self, estudo: str | None = None) -> None:
        """Descarta resultados do gated (todos, ou de um estudo). Os volumes por intervalo só saem com a fonte ou o filtro."""
        for cache in (self._gated, self._cortes_gated, self._vol_tid):
            for chave in list(cache):
                if estudo is None or chave[0] == estudo:
                    del cache[chave]
        validos = {e: a.id for e in PONTUADOS for a in [self._fonte_gated(e)] if a}
        for chave in list(self._vol_gated):
            if validos.get(chave[0]) != chave[1]:
                del self._vol_gated[chave]

    def _por_tipo(self, tipo: str) -> list[Arquivo]:
        return [a for a in self.arquivos.values() if a.tipo == tipo]

    def _fonte(self, estudo: str) -> tuple[Arquivo, bool] | None:
        """Arquivo de onde sai o volume de um estudo e se é a soma de um gated."""
        lista = self._por_tipo(estudo)
        if len(lista) == 1:
            return lista[0], lista[0].aq.gated
        if estudo in PONTUADOS:
            g = self._por_tipo(f"gated_{estudo}")
            if len(g) == 1:
                return g[0], True
        return None

    def estudos_disponiveis(self) -> list[str]:
        return [e for e in ESTUDOS if self._fonte(e) is not None]

    def _fonte_gated(self, estudo: str) -> Arquivo | None:
        """Arquivo do gated de um estudo (estresse ou repouso), se houver um só."""
        if estudo not in PONTUADOS:
            return None
        lista = [a for a in self._por_tipo(f"gated_{estudo}") if a.aq.gated]
        return lista[0] if len(lista) == 1 else None

    def gated_disponiveis(self) -> list[str]:
        return [e for e in PONTUADOS if self._fonte_gated(e) is not None]

    # ------------------------------------------------------------- validação
    def _validacao_arquivos(self) -> str | None:
        if not self.arquivos:
            return "Carregue as projeções do estresse e do repouso (e os gated, se houver)."
        repetidos = sorted({ROTULOS_TIPO[a.tipo] for a in self.arquivos.values() if a.tipo != "ignorar" and len(self._por_tipo(a.tipo)) > 1})
        if repetidos:
            return "Tipo repetido em mais de um arquivo: " + ", ".join(repetidos) + ". Deixe um arquivo por tipo."
        if not any(self._fonte(e) for e in PONTUADOS):
            return "Falta a aquisição de estresse ou de repouso: marque o tipo de cada arquivo."
        return None

    def _validacao_eixos(self) -> str | None:
        if self._validacao_arquivos():
            return self._validacao_arquivos()
        faltam = [ROTULO_ESTUDO[e].lower() for e in self.estudos_disponiveis() if e not in self.eixos]
        if faltam:
            return "Trace o eixo do VE em: " + ", ".join(faltam) + "."
        return None

    def _avisos(self) -> list[str]:
        avisos = []
        for a in self.arquivos.values():
            for x in a.aq.avisos:
                avisos.append(f"{a.nome}: {x}")
        for e in PONTUADOS:
            f = self._fonte(e)
            if f and f[1] and f[0].tipo.startswith("gated"):
                avisos.append(f"{ROTULO_ESTUDO[e]}: sem a aquisição não sincronizada; a perfusão usa a soma dos intervalos do gated.")
        if not self._fonte("repouso") and self._fonte("estresse"):
            avisos.append("Só estresse: sem repouso, não há SRS nem SDS.")
        if not self._fonte("estresse") and self._fonte("repouso"):
            avisos.append("Só repouso: sem estresse, não há SSS nem SDS.")
        dims = {(a.aq.pixel_mm, a.aq.colunas) for e in self.estudos_disponiveis() for a in [self._fonte(e)[0]]}
        if len(dims) > 1:
            avisos.append("As aquisições têm tamanho de pixel ou matriz diferentes: confira o pareamento dos cortes.")
        return avisos

    # ------------------------------------------------------------ reconstrução
    def definir_filtro(self, corte, ordem) -> None:
        try:
            self.filtro = Filtro(float(corte), int(ordem)).validar()
        except ValueError as erro:
            raise ErroSessao(str(erro)) from None
        self._vol.clear()
        self._polar.clear()
        self._vol_gated.clear()
        self._limpar_gated()

    def _vol_chave(self, estudo: str):
        f = self._fonte(estudo)
        return None if f is None else (estudo, f[0].id)

    def volume(self, estudo: str) -> Volume:
        if estudo not in ESTUDOS:
            raise ErroSessao("Estudo desconhecido.")
        chave = self._vol_chave(estudo)
        if chave is None:
            raise ErroSessao(f"Sem aquisição de {ROTULO_ESTUDO[estudo].lower()}.")
        if chave not in self._vol:
            self._vol[chave] = reconstruir(self._fonte(estudo)[0].aq, self.filtro)
        return self._vol[chave]

    def corte_sugerido(self, estudo: str) -> int:
        """Corte transaxial inicial: o do meio do campo, porque a aquisição cardíaca é centrada no coração.

        Buscar o corte mais quente erra com frequência (estômago, alças e
        fígado captam muito MIBI); o usuário escolhe o corte no controle.
        """
        return self.volume(estudo).n_cortes // 2

    def _janela_volume(self, estudo: str) -> dict:
        """Janela inicial do transaxial e do plano vertical (só exibição).

        Fígado e alças costumam captar muito mais que o coração; uma janela
        pelo volume inteiro deixa o VE escuro. O teto é o percentil 99,8 da
        região onde o coração costuma estar: metade direita da imagem (lado
        esquerdo do paciente), da frente até 65% da altura, nos cortes entre
        25% e 75% do campo. O usuário ajusta com o botão do meio.
        """
        v = np.clip(self.volume(estudo).dados, 0, None)
        k, n = v.shape[0], v.shape[1]
        regiao = v[k // 4 : max(k // 4 + 1, 3 * k // 4), : max(1, int(0.65 * n)), n // 2 :]
        teto = float(np.percentile(regiao, 99.8)) or float(v.max()) or 1.0
        return {"nivel": teto / 2.0, "largura": teto, "faixa": float(v.max()) or 1.0}

    # ------------------------------------------------------------------ eixos
    def definir_eixo(self, estudo, corte, base_1, apice_1, base_2=None, apice_2=None) -> None:
        """Eixo pelas duas etapas. Sem a segunda, usa a linha horizontal equivalente no plano vertical."""
        vol = self.volume(estudo)
        k = int(corte)
        if not 0 <= k < vol.n_cortes:
            raise ErroSessao("Corte transaxial fora do volume.")
        b1, a1 = _ponto(base_1), _ponto(apice_1)
        if np.hypot(a1[0] - b1[0], a1[1] - b1[1]) < 2:
            raise ErroSessao("Linha curta demais: marque a base e o ápice do VE.")
        m = (vol.n - 1) / 2.0
        if base_2 is None or apice_2 is None:
            meia = np.hypot(a1[0] - b1[0], a1[1] - b1[1]) / 2.0
            b2, a2 = (m - meia, m), (m + meia, m)
        else:
            b2, a2 = _ponto(base_2), _ponto(apice_2)
        try:
            self.eixos[estudo] = eixos.eixo_de_marcacoes(vol, k, b1, a1, b2, a2)
        except ValueError as erro:
            raise ErroSessao(str(erro)) from None
        self._eixo_fonte[estudo] = self._fonte(estudo)[0].id
        self._polar.pop(estudo, None)
        self._limpar_gated(estudo)

    def copiar_eixo(self, de, para) -> None:
        if de not in self.eixos:
            raise ErroSessao(f"O {ROTULO_ESTUDO.get(de, de).lower()} ainda não tem eixo.")
        vol = self.volume(para)
        src = self.eixos[de]
        self.eixos[para] = eixos.marcacoes_de_eixo(vol, src.base, src.apice)
        self._eixo_fonte[para] = self._fonte(para)[0].id
        self._polar.pop(para, None)
        self._limpar_gated(para)

    def comprimento_par(self, estudo) -> float | None:
        """Comprimento comum do eixo curto no par (estresse e repouso; pronas): o maior dos eixos traçados."""
        for par in PARES:
            if estudo in par:
                comps = [self.eixos[e].comprimento for e in par if e in self.eixos]
                return max(comps) if comps else None
        return self.eixos[estudo].comprimento if estudo in self.eixos else None

    def apagar_eixo(self, estudo) -> None:
        self.eixos.pop(estudo, None)
        self._polar.pop(estudo, None)
        self._limpar_gated(estudo)

    def _eixo(self, estudo) -> eixos.Eixo:
        if estudo not in self.eixos:
            raise ErroSessao(f"Trace o eixo do VE no {ROTULO_ESTUDO.get(estudo, estudo).lower()}.")
        return self.eixos[estudo]

    # ------------------------------------------------------------------ polar
    def mapa_polar(self, estudo) -> polar.MapaPolar:
        if estudo not in self._polar:
            try:
                self._polar[estudo] = polar.amostrar_polar(self.volume(estudo), self._eixo(estudo))
            except ValueError as erro:
                raise ErroSessao(str(erro)) from None
        return self._polar[estudo]

    def mapa_diferenca(self) -> polar.MapaPolar | None:
        """Mapa polar repouso − estresse (pontos percentuais), amostra a amostra; None sem os dois estudos com eixo."""
        if not all(self._fonte(e) and e in self.eixos for e in PONTUADOS):
            return None
        est, rep = self.mapa_polar("estresse"), self.mapa_polar("repouso")
        return polar.MapaPolar(parede=rep.parede - est.parede, apice=rep.apice - est.apice, maximo=1.0, r_c_mm=est.r_c_mm,
                               rho_apice=0.5 * (est.rho_apice + rep.rho_apice), azimutes=est.azimutes)

    def _teto(self, estudo) -> float:
        return self.mapa_polar(estudo).maximo * self.tetos.get(estudo, 100.0) / 100.0

    def definir_teto(self, estudo, teto) -> None:
        if estudo not in ESTUDOS:
            raise ErroSessao("Estudo desconhecido.")
        t = float(teto)
        if not 20.0 <= t <= 200.0:
            raise ErroSessao("O teto da escala deve ficar entre 20% e 200% do máximo do VE.")
        self.tetos[estudo] = t

    def definir_mapa(self, mapa) -> None:
        if mapa not in figuras.MAPAS:
            raise ErroSessao("Escala de cor desconhecida.")
        self.mapa = mapa

    # ---------------------------------------------------------------- escores
    def pontuar(self, estudo, segmento, escore) -> None:
        if estudo not in PONTUADOS:
            raise ErroSessao("Só o estresse e o repouso são pontuados.")
        s = int(segmento)
        if s not in polar.SEGMENTOS:
            raise ErroSessao("Segmento deve ser de 1 a 17.")
        try:
            self.escores[estudo][s] = validar_escore(escore)
        except ValueError as erro:
            raise ErroSessao(str(erro)) from None

    def pontuar_todos(self, estudo, escore) -> None:
        for s in polar.SEGMENTOS:
            self.pontuar(estudo, s, escore)

    def copiar_escores(self, de, para) -> None:
        if de not in PONTUADOS or para not in PONTUADOS:
            raise ErroSessao("Só o estresse e o repouso são pontuados.")
        self.escores[para] = dict(self.escores[de])

    def calcular_escores(self):
        return calcular_escores(self.escores["estresse"], self.escores["repouso"])

    # ------------------------------------------------------------------ gated
    def volumes_gated(self, estudo: str) -> list[Volume]:
        """Um volume por intervalo do gated, com o filtro atual."""
        a = self._fonte_gated(estudo)
        if a is None:
            raise ErroSessao(f"Sem gated do {ROTULO_ESTUDO.get(estudo, estudo).lower()}.")
        chave = (estudo, a.id)
        if chave not in self._vol_gated:
            self._vol_gated[chave] = [reconstruir(a.aq, self.filtro, k) for k in range(a.aq.n_intervalos)]
        return self._vol_gated[chave]

    def funcao(self, estudo: str) -> gated.ResultadoGated:
        """Bordas, volumes e FE do gated do estudo, com o eixo do próprio estudo."""
        chave = (estudo,)
        if chave not in self._gated:
            a = self._fonte_gated(estudo)
            if a is None:
                raise ErroSessao(f"Sem gated do {ROTULO_ESTUDO.get(estudo, estudo).lower()}.")
            vols = self.volumes_gated(estudo)
            totais = a.aq.projecoes.sum(axis=(1, 2, 3))
            try:
                self._gated[chave] = gated.analisar_gated(vols, totais, self._eixo(estudo))
            except ValueError as erro:
                raise ErroSessao(str(erro)) from None
        return self._gated[chave]

    def volume_cavidade_nao_sincronizado(self, estudo: str) -> float:
        chave = (estudo,)
        if chave not in self._vol_tid:
            self._vol_tid[chave] = gated.volume_nao_sincronizado(self.volume(estudo), self._eixo(estudo))
        return self._vol_tid[chave]

    def tid(self) -> dict | None:
        """TID (estresse ÷ repouso) nas imagens não sincronizadas, se os dois estudos tiverem eixo."""
        if not all(self._fonte(e) and e in self.eixos for e in PONTUADOS):
            return None
        ve, vr = (self.volume_cavidade_nao_sincronizado(e) for e in PONTUADOS)
        de_gated = [ROTULO_ESTUDO[e] for e in PONTUADOS if self._fonte(e)[1]]
        return {"estresse_ml": round(ve, 1), "repouso_ml": round(vr, 1), "tid": round(gated.calcular_tid(ve, vr), 2),
                "de_gated": de_gated}

    def superficie_corporal(self) -> float | None:
        a = self.antropometria
        if a.get("peso_kg") and a.get("altura_cm"):
            return gated.superficie_corporal(a["peso_kg"], a["altura_cm"])
        return None

    def definir_antropometria(self, peso, altura) -> None:
        """Peso (kg) e altura (cm), digitados (nunca lidos do DICOM), para indexar os volumes. Vazios apagam."""
        if peso in (None, "") or altura in (None, ""):
            self.antropometria = {}
            return
        p, h = float(peso), float(altura)
        if not (2.0 <= p <= 400.0 and 40.0 <= h <= 250.0):
            raise ErroSessao("Peso entre 2 e 400 kg e altura entre 40 e 250 cm.")
        self.antropometria = {"peso_kg": p, "altura_cm": h}

    def pontuar_funcao(self, tipo, estudo, segmento, escore) -> None:
        if tipo not in TIPOS_FUNCAO:
            raise ErroSessao("Escore de função desconhecido.")
        if estudo not in PONTUADOS:
            raise ErroSessao("Só o estresse e o repouso são pontuados.")
        s = int(segmento)
        if s not in polar.SEGMENTOS:
            raise ErroSessao("Segmento deve ser de 1 a 17.")
        if escore is None:
            self.escores_funcao[tipo][estudo].pop(s, None)
            return
        try:
            self.escores_funcao[tipo][estudo][s] = gated.validar_escore_funcao(tipo, escore)
        except ValueError as erro:
            raise ErroSessao(str(erro)) from None

    def pontuar_funcao_todos(self, tipo, estudo, escore) -> None:
        for s in polar.SEGMENTOS:
            self.pontuar_funcao(tipo, estudo, s, escore)

    def copiar_escores_funcao(self, tipo, de, para) -> None:
        if tipo not in TIPOS_FUNCAO or de not in PONTUADOS or para not in PONTUADOS:
            raise ErroSessao("Escore de função ou estudo desconhecido.")
        self.escores_funcao[tipo][para] = dict(self.escores_funcao[tipo][de])

    def _mapa_funcao(self, estudo: str, tipo: str) -> polar.MapaPolar:
        r = self.funcao(estudo)
        return r.motilidade if tipo == "motilidade" else r.espessamento

    def _somas_funcao(self, estudo: str) -> dict:
        return {
            "sms": gated.escores_funcao(self.escores_funcao["motilidade"][estudo], "motilidade"),
            "sts": gated.escores_funcao(self.escores_funcao["espessamento"][estudo], "espessamento"),
        }

    def funcao_info(self, com_malha: bool = True) -> dict:
        """Resultados do gated para a interface: por estudo (volumes, FE, mapas, escores, malha) e a TID."""
        sc = self.superficie_corporal()
        estudos = {}
        for e in self.gated_disponiveis():
            if e not in self.eixos:
                continue
            r = self.funcao(e)
            item = r.resumo()
            item["rotulo"] = ROTULO_ESTUDO[e]
            item["n_intervalos"] = len(r.volumes_ml)
            item["de_soma"] = bool(self._fonte(e) and self._fonte(e)[1])
            if sc:
                item["indices"] = {"vdf_ml_m2": round(r.vdf_ml / sc, 1), "vsf_ml_m2": round(r.vsf_ml / sc, 1)}
            mapas = {}
            for tipo in TIPOS_FUNCAO:
                mp = self._mapa_funcao(e, tipo)
                mapas[tipo] = {
                    "valores": {str(s): round(v, 1) for s, v in mp.valores_segmentos().items()},
                    "rho_apice": mp.rho_apice,
                    "segmentos": polar.geometria_segmentos(mp.rho_apice, LADO_POLAR),
                    "escores": {str(s): self.escores_funcao[tipo][e].get(s) for s in polar.SEGMENTOS},
                    "teto": TETO_FUNCAO[tipo],
                }
            item["mapas"] = mapas
            item["somas"] = self._somas_funcao(e)
            if com_malha:
                item["malha"] = r.malha()
            estudos[e] = item
        return {
            "estudos": estudos,
            "tid": self.tid(),
            "superficie_corporal": round(sc, 2) if sc else None,
            "antropometria": dict(self.antropometria),
            "lado": LADO_POLAR,
            "metodo": {"fracao_sd": gated.FRACAO_SD, "limiar_valva": gated.LIMIAR_VALVA},
            "contornos": {"largura": 5 * figuras.LADO_CONTORNO + 4 * 4, "altura": figuras.LADO_CONTORNO,
                          "paineis": ["Eixo curto apical", "Eixo curto médio", "Eixo curto basal", "Eixo longo vertical", "Eixo longo horizontal"]},
        }

    def _teto_contornos(self, estudo: str) -> float:
        """Teto da escala dos contornos: percentil 99,5 do eixo curto médio, o maior entre os intervalos (só exibição)."""
        chave = (estudo, "teto_contornos")
        if chave not in self._cortes_gated:
            r = self.funcao(estudo)
            o = np.linspace(-figuras.CAMPO_CONTORNO_MM / 2, figuras.CAMPO_CONTORNO_MM / 2, 71)
            U, V = np.meshgrid(o, o)
            tetos = []
            for t, v in enumerate(self.volumes_gated(estudo)):
                _, c, ex, ey = gated.paineis_contorno(r, t)[1]
                tetos.append(float(np.percentile(v.amostrar(c + U[..., None] * ex + V[..., None] * ey), 99.5)))
            self._cortes_gated[chave] = max(tetos) or 1.0
        return self._cortes_gated[chave]

    def contornos(self, estudo: str, intervalo: int, mapa: str | None = None) -> np.ndarray:
        """RGBA dos 5 cortes de conferência de um intervalo com o endocárdio (azul) e o epicárdio (verde)."""
        r = self.funcao(estudo)
        vols = self.volumes_gated(estudo)
        t = int(np.clip(int(intervalo), 0, len(vols) - 1))
        teto = self._teto_contornos(estudo) * self.tetos.get(estudo, 100.0) / 100.0
        return figuras.contornos_rgba(vols[t], gated.paineis_contorno(r, t), r.malhas_mm[t], teto, mapa or self.mapa)

    def _cortes_gated_teto(self, estudo: str, tipo: str):
        chave = (estudo, tipo)
        if chave not in self._cortes_gated:
            e = self._eixo(estudo)
            pilhas = np.stack([eixos.cortes(v, e, tipo, comprimento=self.comprimento_par(estudo))[1] for v in self.volumes_gated(estudo)])
            teto = float(np.percentile(pilhas, 99.9)) or float(pilhas.max()) or 1.0
            self._cortes_gated[chave] = (pilhas, teto)
        return self._cortes_gated[chave]

    # ----------------------------------------------------------------- imagens
    def _cinza(self, valores, pedido, padrao) -> bytes:
        nivel = float(pedido["nivel"]) if pedido.get("nivel") is not None else padrao["nivel"]
        largura = float(pedido["largura"]) if pedido.get("largura") is not None else padrao["largura"]
        return exibicao.renderizar_rgba(valores, nivel, largura, bool(pedido.get("invertido")))

    @staticmethod
    def _janela(valores) -> dict:
        """Janela inicial das projeções (só exibição).

        Teto no percentil 99,5 dos 60% superiores das linhas, onde fica o
        coração numa aquisição centrada nele; fígado e alças, abaixo, não
        escurecem a imagem. O usuário ajusta com o botão do meio.
        """
        v = np.asarray(valores, dtype=np.float64)
        if not v.size:
            return {"nivel": 0.5, "largura": 1.0, "faixa": 1.0}
        mx = float(v.max())
        parte = v[..., : max(1, int(0.6 * v.shape[-2])), :] if v.ndim >= 2 else v
        teto = float(np.percentile(parte, 99.5)) or mx or 1.0
        return {"nivel": teto / 2.0, "largura": max(teto, 1.0), "faixa": max(mx, 1.0)}

    def imagem(self, pedido) -> bytes:
        """Bytes RGBA de uma imagem. ``pedido['fonte']``:

        * ``projecao`` (arquivo, indice, intervalo opcional): projeção de um ângulo;
        * ``sinograma`` (arquivo, linha) e ``linograma`` (arquivo);
        * ``transaxial`` (estudo, corte) e ``plano_vertical`` (estudo; ou corte, base_1, apice_1);
        * ``faixa`` (estudo, tipo SA | VLA | HLA) e ``previa`` (estudo: SA, VLA e HLA do meio);
        * ``polar`` (estudo; com_escores) e ``polar_diferenca`` (repouso − estresse);
        * ``faixa_gated`` (estudo, tipo, intervalo): cortes de um intervalo do gated;
        * ``polar_funcao`` (estudo, tipo motilidade | espessamento; com_escores);
        * ``contornos`` (estudo, intervalo): eixo curto apical, médio e basal e eixos longos com endo e epicárdio.
        As imagens em cinza aceitam nivel, largura e invertido.
        """
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        fonte = pedido.get("fonte")
        if fonte in ("projecao", "sinograma", "linograma"):
            aq = self._arquivo(pedido["arquivo"]).aq
            soma = aq.somadas()
            if fonte == "projecao":
                i = int(np.clip(int(pedido.get("indice", 0)), 0, aq.n_angulos - 1))
                g = pedido.get("intervalo")
                valores = soma[i] if g is None else aq.projecoes[int(np.clip(int(g), 0, aq.n_intervalos - 1)), i]
                return self._cinza(valores, pedido, self._janela(soma if g is None else aq.projecoes))
            valores = controle.sinograma(aq, int(pedido.get("linha", 0))) if fonte == "sinograma" else controle.linograma(aq)
            return self._cinza(valores, pedido, self._janela(valores))
        estudo = pedido.get("estudo")
        if fonte == "transaxial":
            vol = self.volume(estudo)
            k = int(np.clip(int(pedido.get("corte", vol.n_cortes // 2)), 0, vol.n_cortes - 1))
            return self._cinza(np.clip(vol.dados[k], 0, None), pedido, self._janela_volume(estudo))
        if fonte == "plano_vertical":
            vol = self.volume(estudo)
            if pedido.get("base_1") is not None:
                k, b1, a1 = int(pedido["corte"]), _ponto(pedido["base_1"]), _ponto(pedido["apice_1"])
            else:
                e = self._eixo(estudo)
                k, b1, a1 = e.corte_transaxial, e.base_1, e.apice_1
            try:
                valores = eixos.plano_vertical(vol, k, b1, a1)
            except ValueError as erro:
                raise ErroSessao(str(erro)) from None
            return self._cinza(valores, pedido, self._janela_volume(estudo))
        if fonte == "faixa":
            vol, e = self.volume(estudo), self._eixo(estudo)
            _, ims = eixos.cortes(vol, e, str(pedido.get("tipo", "SA")), comprimento=self.comprimento_par(estudo))
            return figuras.faixa_rgba(ims, self._teto(estudo), pedido.get("mapa") or self.mapa, FATOR_CORTES).tobytes()
        if fonte == "previa":
            vol, e = self.volume(estudo), self._eixo(estudo)
            ims = []
            for tipo in ("SA", "VLA", "HLA"):
                pos = eixos.posicoes(e, vol.pixel_mm, tipo)
                meio = 0.5 * e.comprimento if tipo == "SA" else 0.0
                d = float(pos[np.argmin(np.abs(pos - meio))])
                ims.append(eixos.corte(vol, e, tipo, d))
            return figuras.faixa_rgba(np.stack(ims), self._teto(estudo), self.mapa, FATOR_CORTES, espaco=6).tobytes()
        if fonte == "faixa_gated":
            tipo = str(pedido.get("tipo", "SA"))
            pilhas, teto = self._cortes_gated_teto(estudo, tipo)
            k = int(np.clip(int(pedido.get("intervalo", 0)), 0, pilhas.shape[0] - 1))
            fator = self.tetos.get(estudo, 100.0) / 100.0
            return figuras.faixa_rgba(pilhas[k], teto * fator, pedido.get("mapa") or self.mapa, FATOR_CORTES).tobytes()
        if fonte == "contornos":
            return self.contornos(estudo, pedido.get("intervalo", 0), pedido.get("mapa")).tobytes()
        if fonte == "polar_funcao":
            tipo = pedido.get("tipo")
            if tipo not in TIPOS_FUNCAO:
                raise ErroSessao("Mapa de função desconhecido.")
            mp = self._mapa_funcao(estudo, tipo)
            esc = self.escores_funcao[tipo][estudo] if pedido.get("com_escores") else None
            return figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, pedido.get("mapa") or self.mapa, esc,
                                      teto=TETO_FUNCAO[tipo]).tobytes()
        if fonte == "polar_diferenca":
            dif = self.mapa_diferenca()
            if dif is None:
                raise ErroSessao("Trace o eixo do estresse e do repouso para ver as diferenças.")
            return figuras.polar_rgba(dif.imagem(LADO_POLAR), dif.rho_apice, pedido.get("mapa") or self.mapa, None,
                                      teto=relatorio.TETO_DIFERENCA).tobytes()
        if fonte == "polar":
            mp = self.mapa_polar(estudo)
            esc = self.escores.get(estudo) if pedido.get("com_escores") and estudo in PONTUADOS else None
            return figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, pedido.get("mapa") or self.mapa, esc).tobytes()
        raise ErroSessao("Imagem desconhecida.")

    # --------------------------------------------------------------- consultas
    def qc(self, arquivo) -> dict:
        a = self._arquivo(arquivo)
        aq = a.aq
        por_proj = controle.contagens_por_projecao(aq)
        saida = {
            "arquivo": a.id,
            "angulos": [round(float(x), 2) for x in aq.angulos],
            "contagens_projecao": [float(x) for x in por_proj],
            "linha_sugerida": controle.linha_do_coracao(aq),
            "pixel_mm": aq.pixel_mm,
            "referencia_movimento": "Deslocamento de 2 pixels ou mais costuma causar artefato importante (Germano, 2001).",
        }
        if aq.gated:
            saida["intervalos"] = controle.contagens_por_intervalo(aq)
            saida["info_gated"] = aq.info_gated
        return saida

    def cortes_info(self) -> dict:
        saida = {}
        for est in self.estudos_disponiveis():
            if est not in self.eixos:
                continue
            vol, e = self.volume(est), self.eixos[est]
            lado = int(round(eixos.LADO_CORTE_MM / vol.pixel_mm))
            tipos = {}
            for tipo in ("SA", "VLA", "HLA"):
                pos = eixos.posicoes(e, vol.pixel_mm, tipo, self.comprimento_par(est))
                n = len(pos)
                tipos[tipo] = {
                    "n": n,
                    "lado": lado * FATOR_CORTES,
                    "largura": n * lado * FATOR_CORTES + (n - 1) * 2,
                    "altura": lado * FATOR_CORTES,
                    "posicoes_mm": [round(float(x), 1) for x in pos],
                }
            saida[est] = {"tipos": tipos, "teto": self.tetos.get(est, 100.0), "comprimento_mm": round(e.comprimento, 1)}
        return saida

    def polar_info(self) -> dict:
        estudos = {}
        for est in self.estudos_disponiveis():
            if est not in self.eixos:
                continue
            mp = self.mapa_polar(est)
            estudos[est] = {
                "valores": {str(s): round(v, 1) for s, v in mp.valores_segmentos().items()},
                "rho_apice": mp.rho_apice,
                "segmentos": polar.geometria_segmentos(mp.rho_apice, LADO_POLAR),
                "escores": {str(s): self.escores[est].get(s) for s in polar.SEGMENTOS} if est in PONTUADOS else None,
            }
        dif = self.mapa_diferenca()
        diferenca = None if dif is None else {
            "valores": {str(s): round(v, 1) for s, v in dif.valores_segmentos().items()},
            "rho_apice": dif.rho_apice,
            "segmentos": polar.geometria_segmentos(dif.rho_apice, LADO_POLAR),
            "teto": relatorio.TETO_DIFERENCA,
        }
        return {"lado": LADO_POLAR, "estudos": estudos, "diferenca": diferenca, "nomes": {str(k): v for k, v in polar.NOMES.items()},
                "territorio": {str(k): v for k, v in polar.TERRITORIO_DO_SEGMENTO.items()}}

    def _resultados(self) -> dict:
        problema = self._validacao_eixos()
        if problema:
            raise ErroSessao(problema)
        r = self.calcular_escores()
        valores = {e: self.mapa_polar(e).valores_segmentos() for e in PONTUADOS if self._fonte(e)}
        fun = self._funcao_relatorio()
        return {
            "funcao": fun,
            "segmentos": relatorio.tabela_segmentos(r, valores),
            "resumo": relatorio.resumo_escores(r),
            "territorios": relatorio.tabela_territorios(r),
            "avisos": r.avisos,
            "tabelas_html": relatorio.tabelas_html(r, valores) + relatorio.funcao_tabelas_html(fun),
            "tabelas_texto": relatorio.tabelas_texto(r, valores) + relatorio.funcao_texto(fun),
            "versao": __version__,
        }

    # ----------------------------------------------------------- serializar
    def _arquivo_json(self, a: Arquivo) -> dict:
        aq = a.aq
        soma = aq.somadas()
        return {
            "id": a.id,
            "nome": a.nome,
            "tipo": a.tipo,
            "gated": aq.gated,
            "info": {k: v for k, v in aq.info.items() if k != "sigma"},
            "info_gated": aq.info_gated,
            "avisos": list(aq.avisos),
            "contagens": fmt_int(float(soma.sum())),
            "dims": {
                "linhas": aq.linhas,
                "colunas": aq.colunas,
                "angulos": aq.n_angulos,
                "intervalos": aq.n_intervalos,
            },
            "janela": self._janela(soma),
            "filtro_cm": round(self.filtro.ciclos_cm(aq.pixel_mm), 3),
        }

    def estado(self) -> dict:
        estudos = []
        for e in self.estudos_disponiveis():
            a, de_gated = self._fonte(e)
            item = {
                "estudo": e,
                "rotulo": ROTULO_ESTUDO[e],
                "arquivo": a.id,
                "de_gated": bool(de_gated and a.tipo.startswith("gated")),
                "n_cortes": a.aq.linhas,
                "n": a.aq.colunas,
                "eixo": self.eixos[e].como_dict() if e in self.eixos else None,
                "pontuado": e in PONTUADOS,
            }
            chave = self._vol_chave(e)
            if chave in self._vol:
                item["janela"] = self._janela_volume(e)
                item["corte_sugerido"] = self.corte_sugerido(e)
            estudos.append(item)
        pixel = next((a.aq.pixel_mm for a in self.arquivos.values()), None)
        r = self.calcular_escores()
        return {
            "versao": __version__,
            "arquivos": [self._arquivo_json(a) for a in self.arquivos.values()],
            "tipos": [{"valor": t, "rotulo": ROTULOS_TIPO[t]} for t in TIPOS],
            "estudos": estudos,
            "filtro": {
                "corte": self.filtro.corte_nyquist,
                "ordem": self.filtro.ordem,
                "ciclos_pixel": round(self.filtro.ciclos_pixel(), 4),
                "ciclos_cm": round(self.filtro.ciclos_cm(pixel), 3) if pixel else None,
                "pixel_mm": pixel,
                "padrao": {"corte": CORTE_PADRAO, "ordem": ORDEM_PADRAO},
            },
            "mapa": self.mapa,
            "tetos": dict(self.tetos),
            "escores": {e: {str(s): self.escores[e].get(s) for s in polar.SEGMENTOS} for e in PONTUADOS},
            "somas": {"sss": r.sss, "srs": r.srs, "sds": r.sds},
            "gated": self.gated_disponiveis(),
            "escores_funcao": {t: {e: {str(s): self.escores_funcao[t][e].get(s) for s in polar.SEGMENTOS} for e in PONTUADOS} for t in TIPOS_FUNCAO},
            "antropometria": dict(self.antropometria),
            "reconstruido": all(self._vol_chave(e) in self._vol for e in self.estudos_disponiveis()) and bool(self.estudos_disponiveis()),
            "avisos": self._avisos(),
            "erros": list(self.erros),
            "validacao": {"arquivos": self._validacao_arquivos(), "eixos": self._validacao_eixos()},
        }

    def _resposta(self, extra: dict | None = None, com_estado: bool = True) -> str:
        r = {"ok": True}
        if extra:
            r.update(extra)
        if com_estado:
            r["estado"] = self.estado()
        return json.dumps(r, ensure_ascii=False)

    # ---------------------------------------------------------------- laudo
    def _arquivos_info(self) -> list[dict]:
        saida = []
        for a in self.arquivos.values():
            if a.tipo == "ignorar":
                continue
            info = a.aq.info
            saida.append(
                {
                    "rotulo": ROTULOS_TIPO[a.tipo],
                    "nome": a.nome,
                    "detalhe": (
                        f"{info.get('fabricante', '')} {info.get('modelo', '')}".strip()
                        + f" · {info['projecoes']} projeções em {fmt_dec(info['arco_graus'], 0)}°"
                        + f" · matriz {info['matriz']} · pixel {fmt_dec(info['pixel_mm'], 2)} mm"
                        + (f" · {fmt_dec(info['duracao_vista_s'], 1)} s por vista" if info.get("duracao_vista_s") else "")
                        + (f" · {a.aq.n_intervalos} intervalos" if a.aq.gated else "")
                    ),
                    "gated": a.aq.info_gated if a.aq.gated else None,
                    "intervalos": controle.contagens_por_intervalo(a.aq)["percentual_da_media"] if a.aq.gated else None,
                }
            )
        return saida

    def _funcao_relatorio(self) -> dict | None:
        """Dados do gated para laudo, tabelas e planilha (sem malha)."""
        info = self.funcao_info(com_malha=False)
        if not info["estudos"] and not info["tid"]:
            return None
        return info

    def _imagens_funcao(self, malhas=None) -> dict:
        polares = []
        for e in self.gated_disponiveis():
            if e not in self.eixos:
                continue
            for tipo in TIPOS_FUNCAO:
                mp = self._mapa_funcao(e, tipo)
                png = figuras.png(figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, self.mapa, self.escores_funcao[tipo][e], teto=TETO_FUNCAO[tipo]))
                polares.append((f"{ROTULO_ESTUDO[e]} · {'motilidade (0–10 mm)' if tipo == 'motilidade' else 'espessamento (0–100%)'}", png))
        imgs = []
        for m in malhas or []:
            try:
                rot, url = str(m["rotulo"]), str(m["png"])
            except (KeyError, TypeError):
                continue
            prefixo = "data:image/png;base64,"
            if url.startswith(prefixo) and len(url) < 3_000_000:
                import base64

                try:
                    imgs.append((rot, base64.b64decode(url[len(prefixo):], validate=True)))
                except ValueError:
                    continue
        contornos = []
        for e in self.gated_disponiveis():
            if e not in self.eixos:
                continue
            r = self.funcao(e)
            for t, nome in ((r.ed, "diástole final"), (r.es, "sístole final")):
                contornos.append((f"{ROTULO_ESTUDO[e]} · {nome} (intervalo {t + 1})", figuras.png(self.contornos(e, t))))
        return {"polares": polares, "malhas": imgs, "contornos": contornos}

    def imagens_laudo(self) -> dict:
        """PNGs do laudo: faixas de cortes por tipo e estudo, e mapas polares com os escores."""
        cortes: dict = {}
        for tipo in ("SA", "VLA", "HLA"):
            cortes[tipo] = []
            for e in self.estudos_disponiveis():
                if e not in self.eixos:
                    continue
                _, ims = eixos.cortes(self.volume(e), self.eixos[e], tipo, comprimento=self.comprimento_par(e))
                cortes[tipo].append((ROTULO_ESTUDO[e], figuras.png(figuras.faixa_rgba(ims, self._teto(e), self.mapa, 3))))
        polares = []
        for e in PONTUADOS:
            if self._fonte(e) and e in self.eixos:
                mp = self.mapa_polar(e)
                polares.append((ROTULO_ESTUDO[e], figuras.png(figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, self.mapa, self.escores[e]))))
        dif = self.mapa_diferenca()
        if dif is not None:
            polares.append((f"Repouso − estresse (0 a {relatorio.TETO_DIFERENCA:.0f} pontos)",
                            figuras.png(figuras.polar_rgba(dif.imagem(LADO_POLAR), dif.rho_apice, self.mapa, None, teto=relatorio.TETO_DIFERENCA))))
        return {"cortes": cortes, "polares": polares}

    def laudo(self, paciente: str = "", data_exame: str = "", versoes_extra: dict | None = None, com_imagens: bool = True, malhas=None) -> str:
        res = self._resultados()
        v = versoes()
        v.update({k: str(x) for k, x in (versoes_extra or {}).items()})
        r = self.calcular_escores()
        valores = {e: self.mapa_polar(e).valores_segmentos() for e in PONTUADOS if self._fonte(e)}
        return relatorio.laudo_html(
            r,
            valores,
            self.filtro,
            v,
            self._arquivos_info(),
            paciente=paciente,
            data_exame=data_exame,
            imagens=self.imagens_laudo() if com_imagens else None,
            avisos=self._avisos() + res["avisos"] + [f"{d['rotulo']} (gated): {x}" for d in ((res["funcao"] or {}).get("estudos") or {}).values() for x in d["avisos"]],
            mapa=self.mapa,
            pixel_mm=next((a.aq.pixel_mm for a in self.arquivos.values()), None),
            funcao=res["funcao"],
            imagens_funcao=self._imagens_funcao(malhas) if com_imagens and res["funcao"] else None,
        )

    # ------------------------------------------------------------- protocolo
    def protocolo(self) -> dict:
        """Tudo para refazer em lote: arquivos (nome, SHA-256, tipo), filtro, eixos, escores e exibição."""
        return {
            "ferramenta": "perfusao",
            "formato": 1,
            "versao_nucleo": __version__,
            "arquivos": [{"nome": a.nome, "sha256": a.aq.sha256, "tipo": a.tipo} for a in self.arquivos.values()],
            "filtro": {"corte_nyquist": self.filtro.corte_nyquist, "ordem": self.filtro.ordem},
            "eixos": {e: x.como_dict() for e, x in self.eixos.items()},
            "escores": {e: {str(s): v for s, v in self.escores[e].items()} for e in PONTUADOS},
            "escores_funcao": {t: {e: {str(s): v for s, v in self.escores_funcao[t][e].items()} for e in PONTUADOS} for t in TIPOS_FUNCAO},
            "exibicao": {"mapa": self.mapa, "tetos": dict(self.tetos)},
        }

    @classmethod
    def de_protocolo(cls, protocolo: dict, ler_arquivo) -> "Sessao":
        if protocolo.get("ferramenta") != "perfusao":
            raise ErroSessao("Protocolo de outra ferramenta.")
        s = cls()
        for item in protocolo["arquivos"]:
            aq = ler_aquisicao(ler_arquivo(item["nome"], item["sha256"]))
            if aq.sha256 != item["sha256"]:
                raise ErroSessao(f"{item['nome']}: arquivo diferente do usado no protocolo (SHA-256 não confere).")
            aid = s._novo_id("a")
            s.arquivos[aid] = Arquivo(aid, item["nome"], aq, item["tipo"])
        f = protocolo.get("filtro") or {}
        s.filtro = Filtro(float(f.get("corte_nyquist", CORTE_PADRAO)), int(f.get("ordem", ORDEM_PADRAO))).validar()
        for e, d in (protocolo.get("eixos") or {}).items():
            if s._fonte(e) is None:
                continue
            s._eixo_fonte[e] = s._fonte(e)[0].id
            s.eixos[e] = eixos.Eixo(
                np.asarray(d["base_mm"], dtype=np.float64),
                np.asarray(d["apice_mm"], dtype=np.float64),
                int(d["corte_transaxial"]),
                tuple(d["base_1"]),
                tuple(d["apice_1"]),
                tuple(d["base_2"]),
                tuple(d["apice_2"]),
            )
        for e, d in (protocolo.get("escores") or {}).items():
            if e in PONTUADOS:
                s.escores[e] = {int(k): validar_escore(v) for k, v in d.items()}
        for tipo, por_estudo in (protocolo.get("escores_funcao") or {}).items():
            if tipo in TIPOS_FUNCAO:
                for e, d in por_estudo.items():
                    if e in PONTUADOS:
                        s.escores_funcao[tipo][e] = {int(k): gated.validar_escore_funcao(tipo, v) for k, v in d.items()}
        ex = protocolo.get("exibicao") or {}
        s.mapa = ex.get("mapa", s.mapa)
        s.tetos = {k: float(v) for k, v in (ex.get("tetos") or {}).items()}
        return s

    # ---------------------------------------------------------------- comandos
    def executar(self, comando) -> str:
        """Executa um comando JSON e devolve a resposta em JSON (``ok``, ``erro``, ``estado``)."""
        try:
            c = json.loads(comando) if isinstance(comando, str) else dict(comando)
            acao = c.get("acao")
            if acao == "estado":
                return self._resposta()
            if acao == "limpar":
                self.limpar()
                return self._resposta()
            if acao == "limpar_erros":
                self.erros = []
                return self._resposta()
            if acao == "carregar_fantoma":
                from ..fantomas import fantoma_perfusao

                self.limpar()
                f = fantoma_perfusao()
                for nome, dados in f.arquivos.items():
                    self.adicionar_arquivo(f"fantoma_{nome}", dados)
                return self._resposta({"fantoma": {"eixo": f.eixo, "segmentos_defeito": list(f.segmentos_defeito), "descricao": f.descricao}})
            if acao == "eixo_fantoma":
                # Só para conferência com o fantoma: coloca o eixo verdadeiro (marcações equivalentes).
                from ..fantomas import fantoma_perfusao

                f = fantoma_perfusao(ruido=False)
                for e in self.estudos_disponiveis():
                    vol = self.volume(e)
                    self.eixos[e] = eixos.marcacoes_de_eixo(vol, np.asarray(f.eixo["base"]), np.asarray(f.eixo["apice"]))
                    self._eixo_fonte[e] = self._fonte(e)[0].id
                    self._polar.pop(e, None)
                return self._resposta()
            if acao == "definir_tipo":
                self.definir_tipo(c["arquivo"], c["tipo"])
                return self._resposta()
            if acao == "remover_arquivo":
                self.remover_arquivo(c["arquivo"])
                return self._resposta()
            if acao == "qc":
                return self._resposta({"qc": self.qc(c["arquivo"])}, com_estado=False)
            if acao == "definir_filtro":
                self.definir_filtro(c["corte"], c["ordem"])
                return self._resposta()
            if acao == "curva_filtro":
                f = Filtro(float(c.get("corte", self.filtro.corte_nyquist)), int(c.get("ordem", self.filtro.ordem)))
                try:
                    f = f.validar()
                except ValueError as erro:
                    raise ErroSessao(str(erro)) from None
                freq = np.linspace(0.0, 0.5, 101)
                b = butterworth(freq, f.ciclos_pixel(), f.ordem)
                rb = freq * b
                return self._resposta(
                    {"curva": {"f": freq.round(4).tolist(), "butterworth": b.round(4).tolist(), "rampa_butterworth": (rb / (rb.max() or 1)).round(4).tolist(),
                               "corte_ciclos_pixel": f.ciclos_pixel()}},
                    com_estado=False,
                )
            if acao == "reconstruir":
                for e in self.estudos_disponiveis():
                    self.volume(e)
                return self._resposta()
            if acao == "definir_eixo":
                self.definir_eixo(c["estudo"], c["corte"], c["base_1"], c["apice_1"], c.get("base_2"), c.get("apice_2"))
                return self._resposta()
            if acao == "copiar_eixo":
                self.copiar_eixo(c["de"], c["para"])
                return self._resposta()
            if acao == "apagar_eixo":
                self.apagar_eixo(c["estudo"])
                return self._resposta()
            if acao == "definir_teto":
                self.definir_teto(c["estudo"], c["teto"])
                return self._resposta()
            if acao == "definir_mapa":
                self.definir_mapa(c["mapa"])
                return self._resposta()
            if acao == "cortes":
                return self._resposta({"cortes": self.cortes_info()}, com_estado=False)
            if acao == "polar":
                return self._resposta({"polar": self.polar_info()}, com_estado=False)
            if acao == "pontuar":
                self.pontuar(c["estudo"], c["segmento"], c.get("escore"))
                return self._resposta()
            if acao == "pontuar_todos":
                self.pontuar_todos(c["estudo"], c.get("escore"))
                return self._resposta()
            if acao == "copiar_escores":
                self.copiar_escores(c["de"], c["para"])
                return self._resposta()
            if acao == "janela_arraste":
                j = exibicao.ajustar_janela_por_arraste(c["nivel"], c["largura"], c["dx"], c["dy"], c["faixa"])
                return self._resposta({"nivel": j.nivel, "largura": j.largura}, com_estado=False)
            if acao == "funcao":
                return self._resposta({"funcao": self.funcao_info(bool(c.get("com_malha", True)))}, com_estado=False)
            if acao == "pontuar_funcao":
                self.pontuar_funcao(c["tipo"], c["estudo"], c["segmento"], c.get("escore"))
                return self._resposta()
            if acao == "pontuar_funcao_todos":
                self.pontuar_funcao_todos(c["tipo"], c["estudo"], c.get("escore"))
                return self._resposta()
            if acao == "copiar_escores_funcao":
                self.copiar_escores_funcao(c["tipo"], c["de"], c["para"])
                return self._resposta()
            if acao == "definir_antropometria":
                self.definir_antropometria(c.get("peso"), c.get("altura"))
                return self._resposta()
            if acao == "resultados":
                return self._resposta(self._resultados(), com_estado=False)
            if acao == "laudo":
                html = self.laudo(str(c.get("paciente") or ""), str(c.get("data_exame") or ""), c.get("versoes_extra"), c.get("com_imagens", True),
                                  c.get("malhas"))
                return self._resposta({"html": html}, com_estado=False)
            if acao == "protocolo":
                return self._resposta({"protocolo": self.protocolo()}, com_estado=False)
            raise ErroSessao(f"Comando desconhecido: {acao!r}.")
        except ErroSessao as erro:
            return json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False)
        except (KeyError, TypeError, ValueError) as erro:
            return json.dumps({"ok": False, "erro": f"Comando inválido ({erro})."}, ensure_ascii=False)

    def exportar(self, pedido) -> bytes:
        """Arquivo para download: csv, xlsx, protocolo, png_cortes (estudo, tipo) ou png_polar (estudo)."""
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        formato = pedido.get("formato")
        if formato == "protocolo":
            return json.dumps(self.protocolo(), ensure_ascii=False, indent=2).encode("utf-8")
        if formato == "png_polar":
            e = pedido["estudo"]
            mp = self.mapa_polar(e)
            return figuras.png(figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, self.mapa, self.escores.get(e) if e in PONTUADOS else None))
        if formato == "png_polar_funcao":
            e, tipo = pedido["estudo"], pedido["tipo"]
            if tipo not in TIPOS_FUNCAO:
                raise ErroSessao("Mapa de função desconhecido.")
            mp = self._mapa_funcao(e, tipo)
            return figuras.png(figuras.polar_rgba(mp.imagem(LADO_POLAR), mp.rho_apice, self.mapa, self.escores_funcao[tipo][e], teto=TETO_FUNCAO[tipo]))
        if formato == "png_cortes":
            e = pedido["estudo"]
            _, ims = eixos.cortes(self.volume(e), self._eixo(e), pedido.get("tipo", "SA"), comprimento=self.comprimento_par(e))
            return figuras.png(figuras.faixa_rgba(ims, self._teto(e), self.mapa, FATOR_CORTES))
        self._resultados()
        r = self.calcular_escores()
        valores = {e: self.mapa_polar(e).valores_segmentos() for e in PONTUADOS if self._fonte(e)}
        fun = self._funcao_relatorio()
        if formato == "csv":
            return relatorio.csv_resultados(r, valores, fun)
        if formato == "xlsx":
            return relatorio.xlsx_resultados(r, valores, self.filtro, __version__, fun)
        raise ErroSessao("Formato de exportação desconhecido.")
