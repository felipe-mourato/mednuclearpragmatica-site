"""Sessão de processamento do esvaziamento gástrico.

Guarda o estado de um exame (arquivos, tempos, ROIs) e responde a comandos
em JSON. A interface web só envia comandos e desenha o que recebe; toda a
lógica (pareamento, validações, geometria, contagens, resultados, exportação)
fica aqui e é testada com pytest.

Uso típico (navegador ou computador)::

    s = Sessao()
    s.adicionar_arquivo("T0_ant.dcm", dados)
    ...
    s.executar('{"acao": "desenhar_roi", "tempo": 0, "pontos": [[10,10],[40,10],[25,40]]}')
    s.executar('{"acao": "resultados", "decaimento": true, "meia_vida": 6.0067}')
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import datetime

import numpy as np

from .. import __version__, versoes
from ..comum import exibicao, roi
from ..comum.contagens import MEIA_VIDA_TC99M_H
from ..comum.dicom import ErroDicom, ImagemDicom, adivinhar_vista, ler_dicom
from ..comum.tabela import fmt_dec, fmt_int
from . import relatorio
from .calculo import calcular_resultados, contagens_regionais
from .segmentacao import Segmentacao, segmentar_roi

__all__ = ["Sessao", "MIN_TEMPOS", "COR_PROXIMAL", "COR_DISTAL"]

MIN_TEMPOS = 3
COR_PROXIMAL = (235, 104, 52)  # laranja (série 2 do gráfico)
COR_DISTAL = (27, 175, 122)  # verde-água (série 3 do gráfico)
OPACIDADE_SOBREPOSICAO = 0.45


@dataclass
class Arquivo:
    id: str
    nome: str
    imagem: ImagemDicom
    vista: str
    quadro: int = 0

    def valores(self) -> np.ndarray:
        return self.imagem.quadro(self.quadro)


@dataclass
class Tempo:
    indice: int
    ant: str | None
    post: str | None
    minutos: float | None
    horario_ausente: bool
    dimensoes_diferentes: bool


@dataclass
class Geometria:
    roi_ant: list
    roi_post: list
    mascara_ant: np.ndarray
    mascara_post: np.ndarray
    seg_ant: Segmentacao
    seg_post: Segmentacao


class ErroSessao(ValueError):
    """Erro de uso com mensagem para o usuário."""


def _hora_curta(img: ImagemDicom) -> str | None:
    if img.data_hora is None:
        return None
    return img.data_hora.strftime("%H:%M")


def _meia_vida(decaimento, meia_vida) -> float | None:
    if not decaimento:
        return None
    if meia_vida is None or str(meia_vida).strip() == "":
        return MEIA_VIDA_TC99M_H
    try:
        valor = float(str(meia_vida).replace(",", "."))
    except ValueError:
        raise ErroSessao("Meia-vida inválida: use um número em horas, como 6,0067.") from None
    if not math.isfinite(valor) or valor <= 0:
        raise ErroSessao("Meia-vida inválida: use um número maior que zero, em horas.")
    return valor


def _pontos_json(pontos) -> list:
    return [[round(x, 3), round(y, 3)] for x, y in pontos]


class Sessao:
    """Estado de um exame de esvaziamento gástrico em processamento."""

    def __init__(self) -> None:
        self.limpar()

    # ------------------------------------------------------------------ estado
    def limpar(self) -> None:
        self.arquivos: dict[str, Arquivo] = {}
        self.tempos: list[Tempo] = []
        self.rois: dict[int, list] = {}
        self.sugestoes: list[str] = []
        self.erros: list[str] = []
        self._contador = 0
        self._cache_geo: dict = {}

    def _novo_id(self) -> str:
        self._contador += 1
        return f"a{self._contador}"

    def _arquivo(self, id_: str) -> Arquivo:
        if id_ not in self.arquivos:
            raise ErroSessao("Arquivo não encontrado na sessão.")
        return self.arquivos[id_]

    def _tempo(self, indice) -> Tempo:
        i = int(indice)
        if not 0 <= i < len(self.tempos):
            raise ErroSessao("Tempo inexistente.")
        return self.tempos[i]

    # --------------------------------------------------------------- arquivos
    def adicionar_arquivo(self, nome: str, dados) -> str:
        """Lê um DICOM e o inclui na sessão. Devolve JSON com o estado."""
        nome = str(nome)
        try:
            imagem = ler_dicom(dados)
        except ErroDicom as erro:
            self.erros.append(f"{nome}: {erro}")
            return self._resposta()
        except Exception:  # noqa: BLE001
            self.erros.append(f"{nome}: erro inesperado ao ler o arquivo.")
            return self._resposta()
        id_ = self._novo_id()
        self.arquivos[id_] = Arquivo(id_, nome, imagem, adivinhar_vista(imagem.descricao))
        if imagem.n_quadros >= 2:
            self.sugestoes.append(id_)
        self._parear()
        return self._resposta()

    def _parear(self) -> None:
        """Agrupa os arquivos em tempos (pares ANT/PÓS) em ordem cronológica.

        Anteriores e posteriores são ordenados pelo horário de aquisição
        (sem horário vão para o fim) e pareados pela posição. T0 é o horário
        mais antigo entre todos os arquivos; o tempo decorrido de cada par é
        o horário da anterior (ou da posterior) menos o T0, em minutos.
        Minutos editados à mão são mantidos enquanto o par não mudar.
        """
        anteriores = [a for a in self.arquivos.values() if a.vista == "anterior"]
        posteriores = [a for a in self.arquivos.values() if a.vista == "posterior"]

        def chave(a: Arquivo):
            dh = a.imagem.data_hora
            return (dh is None, dh or datetime.max, int(a.id[1:]))

        anteriores.sort(key=chave)
        posteriores.sort(key=chave)
        horarios = [a.imagem.data_hora for a in self.arquivos.values() if a.imagem.data_hora]
        t0 = min(horarios) if horarios else None
        anteriores_tempos = self.tempos
        novos = []
        for i in range(max(len(anteriores), len(posteriores))):
            ant = anteriores[i] if i < len(anteriores) else None
            post = posteriores[i] if i < len(posteriores) else None
            ref = (ant.imagem.data_hora if ant else None) or (post.imagem.data_hora if post else None)
            minutos = (ref - t0).total_seconds() / 60.0 if (ref and t0) else None
            dif = bool(
                ant and post and (ant.imagem.linhas, ant.imagem.colunas) != (post.imagem.linhas, post.imagem.colunas)
            )
            novo = Tempo(i, ant.id if ant else None, post.id if post else None, minutos, ref is None, dif)
            if i < len(anteriores_tempos):
                velho = anteriores_tempos[i]
                if (
                    velho.ant == novo.ant
                    and velho.post == novo.post
                    and velho.minutos is not None
                    and velho.horario_ausente == novo.horario_ausente
                ):
                    novo.minutos = velho.minutos
            novos.append(novo)
        self.tempos = novos
        self.rois = {i: p for i, p in self.rois.items() if i < len(novos)}

    def aceitar_multiframe(self, arquivo: str) -> None:
        """Usa o quadro 1 do arquivo como anterior e o quadro 2 como posterior."""
        a = self._arquivo(arquivo)
        if a.imagem.n_quadros < 2:
            raise ErroSessao("O arquivo não tem dois quadros.")
        a.vista, a.quadro = "anterior", 0
        id_ = self._novo_id()
        self.arquivos[id_] = Arquivo(id_, a.nome, a.imagem, "posterior", 1)
        self.sugestoes = [s for s in self.sugestoes if s != arquivo]
        self._parear()

    def dispensar_sugestao(self, arquivo: str) -> None:
        self.sugestoes = [s for s in self.sugestoes if s != arquivo]

    def definir_vista(self, arquivo: str, vista: str) -> None:
        if vista not in ("anterior", "posterior"):
            raise ErroSessao("Vista deve ser anterior ou posterior.")
        self._arquivo(arquivo).vista = vista
        self._parear()

    def definir_quadro(self, arquivo: str, quadro) -> None:
        """Troca o quadro de um arquivo multiframe e descarta a ROI daquele tempo."""
        a = self._arquivo(arquivo)
        q = int(quadro)
        if not 0 <= q < a.imagem.n_quadros:
            raise ErroSessao("Quadro inexistente.")
        a.quadro = q
        self._parear()
        for t in self.tempos:
            if arquivo in (t.ant, t.post):
                self.rois.pop(t.indice, None)

    def remover_arquivo(self, arquivo: str) -> None:
        self._arquivo(arquivo)
        del self.arquivos[arquivo]
        self.sugestoes = [s for s in self.sugestoes if s != arquivo]
        self._parear()

    def definir_minutos(self, tempo, valor) -> None:
        t = self._tempo(tempo)
        if valor is None or str(valor).strip() == "":
            t.minutos = None
            return
        try:
            v = float(str(valor).replace(",", "."))
        except ValueError:
            raise ErroSessao("Tempo decorrido inválido.") from None
        if not math.isfinite(v) or v < 0:
            raise ErroSessao("Tempo decorrido deve ser um número maior ou igual a zero.")
        t.minutos = v

    # ------------------------------------------------------------- validação
    def _bloqueio(self, t: Tempo) -> str | None:
        if not t.ant or not t.post:
            return "Par de imagens incompleto."
        if t.dimensoes_diferentes:
            return "Dimensões ANT/PÓS diferentes: não é possível aplicar a mesma ROI."
        return None

    def _validacao_arquivos(self) -> str | None:
        if len(self.tempos) < MIN_TEMPOS or any(
            not t.ant or not t.post or t.minutos is None for t in self.tempos
        ):
            return (
                f"São necessários pelo menos {MIN_TEMPOS} tempos, cada um com imagem ANTERIOR e "
                "POSTERIOR e tempo decorrido preenchido."
            )
        return None

    def _validacao_rois(self) -> str | None:
        if self._validacao_arquivos():
            return self._validacao_arquivos()
        for t in self.tempos:
            if self._bloqueio(t):
                return f"T{t.indice}: {self._bloqueio(t)}"
            if len(self.rois.get(t.indice, [])) < 3:
                return "Desenhe a ROI em todos os tempos para prosseguir."
        return None

    # ------------------------------------------------------------------- ROIs
    def _dimensoes(self, t: Tempo) -> tuple[int, int]:
        a = self.arquivos[t.ant or t.post]
        return a.imagem.linhas, a.imagem.colunas

    def desenhar_roi(self, tempo, pontos) -> None:
        """Define a ROI de um tempo a partir do traço à mão livre.

        Se for a primeira ROI da sessão, ela é copiada para todos os tempos.
        """
        t = self._tempo(tempo)
        if self._bloqueio(t):
            raise ErroSessao(self._bloqueio(t))
        linhas, colunas = self._dimensoes(t)
        # Traço que escapa da imagem é trazido para a borda.
        dentro = [(min(max(x, 0.0), float(colunas)), min(max(y, 0.0), float(linhas))) for x, y in roi.normalizar(pontos)]
        simplificado = roi.simplificar_trajeto(dentro, 1.5)
        if len(simplificado) < 3:
            raise ErroSessao("ROI pequena demais: desenhe um contorno maior.")
        primeira = not any(len(p) >= 3 for p in self.rois.values())
        self.rois[t.indice] = simplificado
        if primeira:
            for outro in self.tempos:
                if outro.indice != t.indice and not self._bloqueio(outro):
                    self.rois[outro.indice] = list(simplificado)

    def copiar_roi(self, tempo) -> None:
        t = self._tempo(tempo)
        origem = self.rois.get(t.indice)
        if not origem:
            raise ErroSessao("Este tempo ainda não tem ROI.")
        for outro in self.tempos:
            if outro.indice != t.indice and not self._bloqueio(outro):
                self.rois[outro.indice] = list(origem)

    def toca_roi(self, tempo, x, y) -> bool:
        t = self._tempo(tempo)
        r = self.rois.get(t.indice)
        if not r:
            return False
        _, colunas = self._dimensoes(t)
        return roi.ponto_perto_do_poligono((float(x), float(y)), r, max(2.0, colunas / 48.0))

    def arrastar_roi(self, tempo, dx, dy, confirmar: bool) -> dict:
        """Desloca a ROI de um tempo sem sair da imagem; só grava se ``confirmar``."""
        t = self._tempo(tempo)
        r = self.rois.get(t.indice)
        if not r:
            raise ErroSessao("Este tempo ainda não tem ROI.")
        linhas, colunas = self._dimensoes(t)
        ddx, ddy = roi.limitar_translacao(r, float(dx), float(dy), colunas, linhas)
        nova = roi.transladar(r, ddx, ddy)
        if confirmar:
            self.rois[t.indice] = nova
        return {
            "roi": _pontos_json(nova),
            "roi_post": _pontos_json(roi.espelhar_horizontal(nova, colunas)),
        }

    def _geometria(self, t: Tempo) -> Geometria | None:
        r = self.rois.get(t.indice)
        if not r or self._bloqueio(t):
            return None
        a, p = self.arquivos[t.ant], self.arquivos[t.post]
        chave = (t.indice, tuple(r), a.imagem.linhas, a.imagem.colunas)
        if chave in self._cache_geo:
            return self._cache_geo[chave]
        linhas, colunas = a.imagem.linhas, a.imagem.colunas
        roi_post = roi.espelhar_horizontal(r, colunas)
        m_ant = roi.mascara_roi(r, linhas, colunas)
        m_post = roi.mascara_roi(roi_post, linhas, colunas)
        try:
            geo = Geometria(r, roi_post, m_ant, m_post, segmentar_roi(m_ant), segmentar_roi(m_post))
        except ValueError:
            raise ErroSessao(f"T{t.indice}: ROI vazia ou pequena demais para segmentação.") from None
        if len(self._cache_geo) > 64:
            self._cache_geo.clear()
        self._cache_geo[chave] = geo
        return geo

    # ------------------------------------------------------------- resultados
    def contagens(self):
        """Contagens regionais de todos os tempos, na ordem T0, T1, ..."""
        problema = self._validacao_rois()
        if problema:
            raise ErroSessao(problema)
        saida = []
        for t in self.tempos:
            g = self._geometria(t)
            a, p = self.arquivos[t.ant], self.arquivos[t.post]
            try:
                saida.append(
                    contagens_regionais(
                        t.minutos,
                        a.valores(),
                        p.valores(),
                        g.mascara_ant,
                        g.seg_ant.proximal,
                        g.seg_ant.distal,
                        g.mascara_post,
                        g.seg_post.proximal,
                        g.seg_post.distal,
                    )
                )
            except ValueError as erro:
                raise ErroSessao(f"T{t.indice}: {erro}") from None
        if saida[0].mg_total <= 0:
            raise ErroSessao("Contagem do T0 igual a zero: confira a ROI do primeiro tempo.")
        return saida

    def resultados(self, decaimento=True, meia_vida=MEIA_VIDA_TC99M_H):
        return calcular_resultados(self.contagens(), _meia_vida(decaimento, meia_vida))

    def _tempos_info(self) -> list[dict]:
        info = []
        for t in self.tempos:
            a, p = self.arquivos.get(t.ant), self.arquivos.get(t.post)

            def nome(x):
                if x is None:
                    return "—"
                return x.nome + (f" (quadro {x.quadro + 1})" if x.imagem.multiframe else "")

            info.append({"rotulo": f"T{t.indice}", "ant": nome(a), "post": nome(p)})
        return info

    def protocolo(self, decaimento=True, meia_vida=MEIA_VIDA_TC99M_H) -> dict:
        """Tudo o que é preciso para refazer o cálculo em lote no computador.

        Contém nomes e SHA-256 dos arquivos, quadros, vistas, minutos e ROIs.
        Não contém pixels nem dados do paciente (mas os nomes dos arquivos
        podem conter; renomeie-os antes de compartilhar o protocolo).
        """
        mv = _meia_vida(decaimento, meia_vida)
        tempos = []
        for t in self.tempos:
            item = {"rotulo": f"T{t.indice}", "minutos": t.minutos, "roi": _pontos_json(self.rois.get(t.indice, []))}
            for vista, id_ in (("ant", t.ant), ("post", t.post)):
                a = self.arquivos.get(id_) if id_ else None
                item[vista] = (
                    {"nome": a.nome, "sha256": a.imagem.sha256, "quadro": a.quadro} if a else None
                )
            tempos.append(item)
        return {
            "ferramenta": "esvaziamento-gastrico",
            "formato": 1,
            "versao_nucleo": __version__,
            "decaimento": mv is not None,
            "meia_vida_h": mv,
            "tempos": tempos,
        }

    @classmethod
    def de_protocolo(cls, protocolo: dict, ler_arquivo) -> "Sessao":
        """Recria uma sessão a partir de um protocolo salvo pela interface.

        ``ler_arquivo(nome, sha256) -> bytes`` devolve o conteúdo de cada
        DICOM. O pareamento, os quadros, os minutos e as ROIs vêm do
        protocolo, sem nova adivinhação; o SHA-256 de cada arquivo é conferido.
        """
        if protocolo.get("ferramenta") != "esvaziamento-gastrico":
            raise ErroSessao("Protocolo de outra ferramenta.")
        s = cls()
        cache: dict[str, ImagemDicom] = {}
        for i, item in enumerate(protocolo["tempos"]):
            ids = {}
            for vista_chave, vista in (("ant", "anterior"), ("post", "posterior")):
                ref = item.get(vista_chave)
                if not ref:
                    ids[vista_chave] = None
                    continue
                if ref["sha256"] not in cache:
                    img = ler_dicom(ler_arquivo(ref["nome"], ref["sha256"]))
                    if img.sha256 != ref["sha256"]:
                        raise ErroSessao(f"{ref['nome']}: arquivo diferente do usado no protocolo (SHA-256 não confere).")
                    cache[ref["sha256"]] = img
                id_ = s._novo_id()
                s.arquivos[id_] = Arquivo(id_, ref["nome"], cache[ref["sha256"]], vista, int(ref.get("quadro", 0)))
                ids[vista_chave] = id_
            a = s.arquivos.get(ids["ant"]) if ids["ant"] else None
            p = s.arquivos.get(ids["post"]) if ids["post"] else None
            dif = bool(a and p and (a.imagem.linhas, a.imagem.colunas) != (p.imagem.linhas, p.imagem.colunas))
            s.tempos.append(Tempo(i, ids["ant"], ids["post"], item.get("minutos"), False, dif))
            if item.get("roi"):
                s.rois[i] = roi.normalizar(item["roi"])
        return s

    # ---------------------------------------------------------------- imagem
    def imagem(self, pedido) -> bytes:
        """Bytes RGBA de um arquivo, com janela, inversão e (opcional) segmentação.

        ``pedido`` (dict ou JSON): arquivo, nivel, largura, invertido e,
        para pintar proximal/distal, ``segmentacao: {"tempo": i, "vista": "ant"|"post"}``.
        """
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        a = self._arquivo(pedido["arquivo"])
        valores = a.valores()
        jp = exibicao.janela_padrao(valores)
        nivel = float(pedido.get("nivel", jp.nivel) if pedido.get("nivel") is not None else jp.nivel)
        largura = float(pedido.get("largura", jp.largura) if pedido.get("largura") is not None else jp.largura)
        sobre = []
        seg_ped = pedido.get("segmentacao")
        if seg_ped:
            t = self._tempo(seg_ped["tempo"])
            g = self._geometria(t)
            if g is not None:
                s = g.seg_ant if seg_ped.get("vista") == "ant" else g.seg_post
                sobre = [
                    (s.proximal, COR_PROXIMAL, OPACIDADE_SOBREPOSICAO),
                    (s.distal, COR_DISTAL, OPACIDADE_SOBREPOSICAO),
                ]
        return exibicao.renderizar_rgba(valores, nivel, largura, bool(pedido.get("invertido")), sobre)

    # ------------------------------------------------------------- serializar
    def estado(self) -> dict:
        arquivos = []
        for a in self.arquivos.values():
            img = a.imagem
            jp = exibicao.janela_padrao(a.valores())
            arquivos.append(
                {
                    "id": a.id,
                    "nome": a.nome,
                    "vista": a.vista,
                    "quadro": a.quadro,
                    "n_quadros": img.n_quadros,
                    "linhas": img.linhas,
                    "colunas": img.colunas,
                    "horario": _hora_curta(img),
                    "horario_encontrado": img.horario_encontrado,
                    "dimensoes": f"{img.colunas}×{img.linhas}",
                    "contagens": fmt_int(img.contagem_total(a.quadro)),
                    "avisos": list(img.avisos),
                    "janela": {"nivel": jp.nivel, "largura": jp.largura, "faixa": exibicao.faixa_valores(a.valores())},
                }
            )
        tempos = []
        erros_geo = []
        for t in self.tempos:
            r = self.rois.get(t.indice)
            item = {
                "indice": t.indice,
                "rotulo": f"T{t.indice}",
                "ant": t.ant,
                "post": t.post,
                "minutos": t.minutos,
                "minutos_texto": "" if t.minutos is None else fmt_dec(t.minutos, 1),
                "horario_ausente": t.horario_ausente,
                "dimensoes_diferentes": t.dimensoes_diferentes,
                "bloqueio": self._bloqueio(t),
                "roi": _pontos_json(r) if r else None,
                "roi_post": None,
                "segmentacao": None,
            }
            if r and not self._bloqueio(t):
                linhas, colunas = self._dimensoes(t)
                item["roi_post"] = _pontos_json(roi.espelhar_horizontal(r, colunas))
                try:
                    g = self._geometria(t)
                    item["segmentacao"] = {
                        "linha_ant": [list(p) for p in g.seg_ant.linha],
                        "linha_post": [list(p) for p in g.seg_post.linha],
                        "pixels_proximal": int(g.seg_ant.proximal.sum()),
                        "pixels_distal": int(g.seg_ant.distal.sum()),
                    }
                except ErroSessao as erro:
                    erros_geo.append(str(erro))
            tempos.append(item)
        sugestoes = [
            {"arquivo": s, "nome": self.arquivos[s].nome, "n_quadros": self.arquivos[s].imagem.n_quadros}
            for s in self.sugestoes
            if s in self.arquivos
        ]
        return {
            "versao": __version__,
            "arquivos": arquivos,
            "tempos": tempos,
            "sugestoes": sugestoes,
            "erros": list(self.erros),
            "erros_segmentacao": erros_geo,
            "validacao": {
                "arquivos": self._validacao_arquivos(),
                "rois": self._validacao_rois() or (erros_geo[0] if erros_geo else None),
            },
        }

    def _resposta(self, extra: dict | None = None, com_estado: bool = True) -> str:
        r = {"ok": True}
        if extra:
            r.update(extra)
        if com_estado:
            r["estado"] = self.estado()
        return json.dumps(r, ensure_ascii=False)

    def executar(self, comando) -> str:
        """Executa um comando JSON e devolve a resposta em JSON.

        Toda resposta tem ``ok``; em erro, ``erro`` traz a mensagem para o
        usuário. Comandos que mudam o estado devolvem ``estado`` atualizado.
        """
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
                from ..fantomas import fantoma_esvaziamento

                self.limpar()
                f = fantoma_esvaziamento(tamanho=64)
                origem = f.multiframe if c.get("multiframe") else f.arquivos
                for nome, dados in origem.items():
                    self.adicionar_arquivo(f"fantoma_{nome}", dados)
                return self._resposta(
                    {"fantoma": {"retencao": f.retencao, "distribuicao": f.distribuicao, "roi": _pontos_json(f.roi)}}
                )
            if acao == "aceitar_multiframe":
                self.aceitar_multiframe(c["arquivo"])
                return self._resposta()
            if acao == "dispensar_sugestao":
                self.dispensar_sugestao(c["arquivo"])
                return self._resposta()
            if acao == "definir_vista":
                self.definir_vista(c["arquivo"], c["vista"])
                return self._resposta()
            if acao == "definir_quadro":
                self.definir_quadro(c["arquivo"], c["quadro"])
                return self._resposta()
            if acao == "remover_arquivo":
                self.remover_arquivo(c["arquivo"])
                return self._resposta()
            if acao == "definir_minutos":
                self.definir_minutos(c["tempo"], c.get("valor"))
                return self._resposta()
            if acao == "desenhar_roi":
                self.desenhar_roi(c["tempo"], c["pontos"])
                return self._resposta()
            if acao == "copiar_roi":
                self.copiar_roi(c["tempo"])
                return self._resposta()
            if acao == "toca_roi":
                return self._resposta({"toca": self.toca_roi(c["tempo"], c["x"], c["y"])}, com_estado=False)
            if acao == "arrastar_roi":
                confirmar = bool(c.get("confirmar"))
                extra = self.arrastar_roi(c["tempo"], c["dx"], c["dy"], confirmar)
                return self._resposta(extra, com_estado=confirmar)
            if acao == "janela_arraste":
                j = exibicao.ajustar_janela_por_arraste(c["nivel"], c["largura"], c["dx"], c["dy"], c["faixa"])
                return self._resposta({"nivel": j.nivel, "largura": j.largura}, com_estado=False)
            if acao == "resultados":
                mv = _meia_vida(c.get("decaimento", True), c.get("meia_vida"))
                linhas = calcular_resultados(self.contagens(), mv)
                return self._resposta(
                    {
                        "colunas": [{"chave": k, "titulo": t, "ajuda": a} for k, t, a in relatorio.COLUNAS],
                        "linhas": relatorio.linhas_formatadas(linhas),
                        "svg": relatorio.curva_svg(linhas),
                        "notas": list(relatorio.NOTAS_FORMULAS),
                        "meia_vida_h": mv,
                        "versao": __version__,
                    },
                    com_estado=False,
                )
            if acao == "laudo":
                mv = _meia_vida(c.get("decaimento", True), c.get("meia_vida"))
                linhas = calcular_resultados(self.contagens(), mv)
                v = versoes()
                v.update({k: str(x) for k, x in (c.get("versoes_extra") or {}).items()})
                html = relatorio.laudo_html(linhas, mv, v, self._tempos_info(), str(c.get("identificacao") or ""))
                return self._resposta({"html": html}, com_estado=False)
            if acao == "protocolo":
                return self._resposta(
                    {"protocolo": self.protocolo(c.get("decaimento", True), c.get("meia_vida"))}, com_estado=False
                )
            raise ErroSessao(f"Comando desconhecido: {acao!r}.")
        except ErroSessao as erro:
            return json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False)
        except (KeyError, TypeError, ValueError) as erro:
            return json.dumps({"ok": False, "erro": f"Comando inválido ({erro})."}, ensure_ascii=False)

    def exportar(self, pedido) -> bytes:
        """Arquivo para download: ``{"formato": "csv"|"xlsx"|"protocolo", "decaimento", "meia_vida"}``."""
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        mv = _meia_vida(pedido.get("decaimento", True), pedido.get("meia_vida"))
        formato = pedido.get("formato")
        if formato == "protocolo":
            return json.dumps(
                self.protocolo(pedido.get("decaimento", True), pedido.get("meia_vida")), ensure_ascii=False, indent=2
            ).encode("utf-8")
        linhas = calcular_resultados(self.contagens(), mv)
        if formato == "csv":
            return relatorio.csv_resultados(linhas)
        if formato == "xlsx":
            return relatorio.xlsx_resultados(linhas, mv, __version__)
        raise ErroSessao("Formato de exportação desconhecido.")
