"""Sessão de processamento da cintilografia renal com ⁹⁹ᵐTc-DMSA.

Guarda o estado de um exame (arquivos, quadros e incidências, ROIs dos
rins, fundo) e responde a comandos em JSON. A interface web só envia
comandos e desenha o que recebe; toda a lógica (incidências, validações,
espelhamento, máscaras, fundo, contagens, resultados, figuras, exportação)
fica aqui e é testada com pytest.

Uso típico (navegador ou computador)::

    s = Sessao()
    s.adicionar_arquivo("post.dcm", dados)
    s.executar('{"acao": "desenhar_roi", "rim": "D", "pontos": [[40,20],[48,20],[48,40],[40,40]]}')
    s.executar('{"acao": "resultados"}')
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import numpy as np

from .. import __version__, versoes
from ..comum import exibicao, roi
from ..comum.dicom import ErroDicom, ImagemDicom, ler_dicom
from ..comum.morfologia import rle_codificar, rle_decodificar
from ..comum.tabela import fmt_int
from . import figuras, relatorio
from .calculo import ResultadoDMSA, calcular, contagens_rim
from .fundo import LARGURA_ANEL_PX, anel_perirrenal
from .incidencias import IGNORAR, INCIDENCIAS, OBLIQUAS, ROTULOS, adivinhar_incidencia

__all__ = ["Sessao", "ErroSessao", "RINS", "VISTAS"]

RINS = ("D", "E")
VISTAS = ("post", "ant")
NOME_RIM = {"D": "rim direito", "E": "rim esquerdo"}
NOME_VISTA = {"post": "posterior", "ant": "anterior"}
METODOS_FUNDO = ("anel", "nenhum")


class ErroSessao(ValueError):
    """Erro de uso com mensagem para o usuário."""


@dataclass
class Arquivo:
    id: str
    nome: str
    imagem: ImagemDicom


@dataclass
class Slot:
    """Um quadro de um arquivo, com a incidência atribuída (um arquivo multiframe gera um slot por quadro)."""

    id: str
    arquivo: str
    quadro: int
    incidencia: str
    aviso: str | None = None


def _pontos_json(pontos) -> list:
    return [[round(float(x), 3), round(float(y), 3)] for x, y in pontos]


def _rim(valor) -> str:
    if valor not in RINS:
        raise ErroSessao("Rim deve ser D (direito) ou E (esquerdo).")
    return valor


def _vista(valor) -> str:
    if valor not in VISTAS:
        raise ErroSessao("Vista deve ser post ou ant.")
    return valor


class Sessao:
    """Estado de um exame de DMSA em processamento."""

    def __init__(self) -> None:
        self.limpar()

    # ------------------------------------------------------------------ estado
    def limpar(self) -> None:
        self.arquivos: dict[str, Arquivo] = {}
        self.slots: dict[str, Slot] = {}
        self.rois: dict[str, list | None] = {"D": None, "E": None}
        self.deslocamento_ant: dict[str, tuple[float, float]] = {"D": (0.0, 0.0), "E": (0.0, 0.0)}
        self.metodo_fundo = "anel"
        self.fundos_manuais: dict[tuple[str, str], list] = {}
        # Máscaras de fundo vindas de um protocolo (lote): usadas exatamente como gravadas.
        self._fundo_fixo: dict[tuple[str, str], np.ndarray] = {}
        self.erros: list[str] = []
        self._contador = 0
        self._ref_post: str | None = None
        self._ref_ant: str | None = None
        self._cache: dict = {}

    def _novo_id(self, prefixo: str) -> str:
        self._contador += 1
        return f"{prefixo}{self._contador}"

    def _slot(self, id_: str) -> Slot:
        if id_ not in self.slots:
            raise ErroSessao("Imagem não encontrada na sessão.")
        return self.slots[id_]

    def _valores(self, s: Slot) -> np.ndarray:
        return self.arquivos[s.arquivo].imagem.quadro(s.quadro)

    def _imagem(self, s: Slot) -> ImagemDicom:
        return self.arquivos[s.arquivo].imagem

    # --------------------------------------------------------------- arquivos
    def adicionar_arquivo(self, nome: str, dados) -> str:
        """Lê um DICOM e cria um slot por quadro. Devolve JSON com o estado."""
        nome = str(nome)
        try:
            imagem = ler_dicom(dados)
        except ErroDicom as erro:
            self.erros.append(f"{nome}: {erro}")
            return self._resposta()
        except Exception:  # noqa: BLE001
            self.erros.append(f"{nome}: erro inesperado ao ler o arquivo.")
            return self._resposta()
        id_ = self._novo_id("a")
        self.arquivos[id_] = Arquivo(id_, nome, imagem)
        if imagem.n_quadros >= 2:
            # Sugestão inicial: quadro 1 posterior, quadro 2 anterior; os demais ficam de fora.
            for q in range(imagem.n_quadros):
                inc = "POST" if q == 0 else "ANT" if q == 1 else IGNORAR
                sid = self._novo_id("s")
                self.slots[sid] = Slot(sid, id_, q, inc)
        else:
            inc, aviso = adivinhar_incidencia(imagem.descricao)
            sid = self._novo_id("s")
            self.slots[sid] = Slot(sid, id_, 0, inc, aviso)
        self._apos_mudanca()
        return self._resposta()

    def definir_incidencia(self, slot: str, incidencia: str) -> None:
        if incidencia not in INCIDENCIAS and incidencia != IGNORAR:
            raise ErroSessao("Incidência desconhecida.")
        s = self._slot(slot)
        s.incidencia = incidencia
        s.aviso = None
        self._apos_mudanca()

    def remover_arquivo(self, arquivo: str) -> None:
        if arquivo not in self.arquivos:
            raise ErroSessao("Arquivo não encontrado na sessão.")
        del self.arquivos[arquivo]
        self.slots = {k: s for k, s in self.slots.items() if s.arquivo != arquivo}
        self._apos_mudanca()

    def _apos_mudanca(self) -> None:
        """Descarta a geometria que dependia de uma imagem que mudou."""
        post, ant = self._unico("POST"), self._unico("ANT")
        id_post = post.id if post else None
        id_ant = ant.id if ant else None
        if id_post != self._ref_post:
            self.rois = {"D": None, "E": None}
            self.deslocamento_ant = {"D": (0.0, 0.0), "E": (0.0, 0.0)}
            self.fundos_manuais.clear()
            self._fundo_fixo.clear()
        if id_ant != self._ref_ant:
            self.deslocamento_ant = {"D": (0.0, 0.0), "E": (0.0, 0.0)}
            for chave in [k for k in self.fundos_manuais if k[0] == "ant"]:
                del self.fundos_manuais[chave]
            for chave in [k for k in self._fundo_fixo if k[0] == "ant"]:
                del self._fundo_fixo[chave]
        self._ref_post, self._ref_ant = id_post, id_ant
        self._cache.clear()

    def _com_incidencia(self, inc: str) -> list[Slot]:
        return [s for s in self.slots.values() if s.incidencia == inc]

    def _unico(self, inc: str) -> Slot | None:
        lista = self._com_incidencia(inc)
        return lista[0] if len(lista) == 1 else None

    # ------------------------------------------------------------- validação
    def _validacao_arquivos(self) -> str | None:
        n_post = len(self._com_incidencia("POST"))
        if n_post == 0:
            return "Falta a imagem POSTERIOR, obrigatória: marque um quadro como POSTERIOR."
        if n_post > 1:
            return f"Há {n_post} imagens marcadas como POSTERIOR: deixe só uma."
        n_ant = len(self._com_incidencia("ANT"))
        if n_ant > 1:
            return f"Há {n_ant} imagens marcadas como ANTERIOR: deixe só uma ou nenhuma."
        return None

    def _validacao_rois(self) -> str | None:
        if self._validacao_arquivos():
            return self._validacao_arquivos()
        faltam = [NOME_RIM[k] for k in RINS if not self.rois.get(k)]
        if faltam:
            return "Desenhe na posterior a ROI do " + " e do ".join(faltam) + "."
        for vista in self._vistas_quantificadas():
            for k in RINS:
                if not self._mascara_rim(vista, k).any():
                    return f"ROI do {NOME_RIM[k]} sem nenhum pixel na {NOME_VISTA[vista]}: redesenhe ou arraste."
            if (self._mascara_rim(vista, "D") & self._mascara_rim(vista, "E")).any():
                return f"As ROIs dos dois rins se sobrepõem na {NOME_VISTA[vista]}: separe-as."
        return None

    def _validacao_fundo(self) -> str | None:
        if self._validacao_rois():
            return self._validacao_rois()
        if self.metodo_fundo == "nenhum":
            return None
        for vista in self._vistas_quantificadas():
            for k in RINS:
                if not self._mascara_fundo(vista, k).any():
                    return f"Região de fundo vazia para o {NOME_RIM[k]} na {NOME_VISTA[vista]}: desenhe uma à mão."
        return None

    def _avisos(self) -> list[str]:
        avisos = []
        for inc in OBLIQUAS:
            n = len(self._com_incidencia(inc))
            if n > 1:
                avisos.append(f"Há {n} imagens marcadas como {inc}: confira as incidências.")
        post, ant = self._unico("POST"), self._unico("ANT")
        if post and ant:
            ip, ia = self._imagem(post), self._imagem(ant)
            if (ip.linhas, ip.colunas) != (ia.linhas, ia.colunas):
                avisos.append(
                    f"Posterior ({ip.colunas}×{ip.linhas}) e anterior ({ia.colunas}×{ia.linhas}) com dimensões "
                    "diferentes: as ROIs da anterior foram espelhadas em escala; confira e arraste se preciso."
                )
        if post and self.rois["D"] and self.rois["E"]:
            xd = float(np.mean([p[0] for p in self.rois["D"]]))
            xe = float(np.mean([p[0] for p in self.rois["E"]]))
            if xd < xe:
                avisos.append(
                    "Na posterior, a ROI do rim direito está à esquerda da do rim esquerdo. Na posterior, o rim "
                    "direito costuma ficar à direita da imagem: confira se os rins não foram trocados."
                )
        for s in self.slots.values():
            if s.aviso:
                avisos.append(f"{self._rotulo_slot(s)}: {s.aviso}")
        return avisos

    def _vistas_quantificadas(self) -> tuple[str, ...]:
        return ("post", "ant") if self._unico("ANT") else ("post",)

    # ------------------------------------------------------------------- ROIs
    def _slot_vista(self, vista: str) -> Slot:
        s = self._unico("POST" if vista == "post" else "ANT")
        if s is None:
            raise ErroSessao(f"Sem imagem {NOME_VISTA[vista].upper()} definida.")
        return s

    def _dim(self, vista: str) -> tuple[int, int]:
        img = self._imagem(self._slot_vista(vista))
        return img.linhas, img.colunas

    def roi_vista(self, vista: str, rim: str) -> list | None:
        """Polígono do rim numa vista: o desenhado (posterior) ou o espelhado e deslocado (anterior).

        Anterior: x' = largura_ant − x × (largura_ant ÷ largura_post) e
        y' = y × (altura_ant ÷ altura_post) (escala 1 quando as dimensões são
        iguais), mais o deslocamento próprio da anterior, limitado à imagem.
        """
        base = self.rois.get(rim)
        if not base:
            return None
        if vista == "post":
            return list(base)
        lp, cp = self._dim("post")
        la, ca = self._dim("ant")
        sx, sy = ca / cp, la / lp
        escalado = [(x * sx, y * sy) for x, y in base]
        espelhado = roi.espelhar_horizontal(escalado, ca)
        dx, dy = self.deslocamento_ant[rim]
        dx, dy = roi.limitar_translacao(espelhado, dx, dy, ca, la)
        return roi.transladar(espelhado, dx, dy)

    def _guardar(self, chave, valor):
        if len(self._cache) > 96:
            self._cache.clear()
        self._cache[chave] = valor
        return valor

    def _mascara_rim(self, vista: str, rim: str) -> np.ndarray:
        poligono = self.roi_vista(vista, rim)
        linhas, colunas = self._dim(vista)
        chave = ("rim", vista, tuple(poligono or ()), linhas, colunas)
        if chave not in self._cache:
            return self._guardar(
                chave, roi.mascara_roi(poligono, linhas, colunas) if poligono else np.zeros((linhas, colunas), dtype=bool)
            )
        return self._cache[chave]

    def desenhar_roi(self, rim, pontos) -> None:
        """Define a ROI de um rim na posterior (traço à mão livre, fechado ao soltar).

        Redesenhar um rim zera o deslocamento dele na anterior e descarta o
        fundo desenhado à mão para ele.
        """
        rim = _rim(rim)
        linhas, colunas = self._dim("post")
        dentro = [(min(max(x, 0.0), float(colunas)), min(max(y, 0.0), float(linhas))) for x, y in roi.normalizar(pontos)]
        simplificado = roi.simplificar_trajeto(dentro, 1.0)
        if len(simplificado) < 3 or roi.area_poligono(simplificado) < 4.0:
            raise ErroSessao("ROI pequena demais: desenhe um contorno maior.")
        self.rois[rim] = simplificado
        self.deslocamento_ant[rim] = (0.0, 0.0)
        for vista in VISTAS:
            self.fundos_manuais.pop((vista, rim), None)
            self._fundo_fixo.pop((vista, rim), None)

    def apagar_roi(self, rim) -> None:
        rim = _rim(rim)
        self.rois[rim] = None
        self.deslocamento_ant[rim] = (0.0, 0.0)
        for vista in VISTAS:
            self.fundos_manuais.pop((vista, rim), None)
            self._fundo_fixo.pop((vista, rim), None)

    def toca_roi(self, vista, x, y) -> str | None:
        """Rim cuja ROI está sob o ponto (ou a poucos pixels da borda), para arrastar."""
        vista = _vista(vista)
        _, colunas = self._dim(vista)
        tol = max(1.5, colunas / 64.0)
        p = (float(x), float(y))
        for rim in RINS:
            pol = self.roi_vista(vista, rim)
            if pol and roi.ponto_no_poligono(p[0], p[1], pol):
                return rim
        for rim in RINS:
            pol = self.roi_vista(vista, rim)
            if pol and roi.ponto_perto_do_poligono(p, pol, tol):
                return rim
        return None

    def arrastar_roi(self, vista, rim, dx, dy, confirmar: bool) -> dict:
        """Desloca a ROI de um rim sem sair da imagem; só grava se ``confirmar``.

        Na posterior, move a ROI desenhada (a anterior acompanha, espelhada).
        Na anterior, move só a ROI da anterior (deslocamento próprio).
        """
        vista, rim = _vista(vista), _rim(rim)
        atual = self.roi_vista(vista, rim)
        if not atual:
            raise ErroSessao("Este rim ainda não tem ROI.")
        linhas, colunas = self._dim(vista)
        ddx, ddy = roi.limitar_translacao(atual, float(dx), float(dy), colunas, linhas)
        nova = roi.transladar(atual, ddx, ddy)
        if confirmar and (ddx or ddy):
            if vista == "post":
                self.rois[rim] = nova
            else:
                ox, oy = self.deslocamento_ant[rim]
                self.deslocamento_ant[rim] = (ox + ddx, oy + ddy)
            self._fundo_fixo.clear()
        saida = {"roi": _pontos_json(nova)}
        if vista == "post" and self._unico("ANT"):
            guardado = self.rois[rim]
            self.rois[rim] = nova
            try:
                saida["roi_ant"] = _pontos_json(self.roi_vista("ant", rim))
            finally:
                if not confirmar:
                    self.rois[rim] = guardado
        return saida

    def restaurar_espelho(self, rim=None) -> None:
        """Volta a ROI da anterior ao espelho exato da posterior (de um rim ou dos dois)."""
        for k in RINS if rim is None else (_rim(rim),):
            self.deslocamento_ant[k] = (0.0, 0.0)
        self._fundo_fixo.clear()

    # ------------------------------------------------------------------ fundo
    def definir_fundo(self, metodo) -> None:
        if metodo not in METODOS_FUNDO:
            raise ErroSessao("Método de fundo deve ser anel ou nenhum.")
        self.metodo_fundo = metodo

    def desenhar_fundo(self, vista, rim, pontos) -> None:
        """Substitui o anel automático de um rim numa vista por uma região desenhada à mão."""
        vista, rim = _vista(vista), _rim(rim)
        linhas, colunas = self._dim(vista)
        dentro = [(min(max(x, 0.0), float(colunas)), min(max(y, 0.0), float(linhas))) for x, y in roi.normalizar(pontos)]
        simplificado = roi.simplificar_trajeto(dentro, 1.0)
        if len(simplificado) < 3 or roi.area_poligono(simplificado) < 2.0:
            raise ErroSessao("Região de fundo pequena demais: desenhe um contorno maior.")
        self.fundos_manuais[(vista, rim)] = simplificado
        self._fundo_fixo.pop((vista, rim), None)
        if not self._mascara_fundo(vista, rim).any():
            del self.fundos_manuais[(vista, rim)]
            raise ErroSessao("A região desenhada fica toda dentro das ROIs renais: desenhe o fundo fora dos rins.")

    def fundo_automatico(self, vista=None, rim=None) -> None:
        """Descarta o fundo desenhado à mão (de uma vista e rim, ou de todos) e volta ao anel."""
        for chave in list(self.fundos_manuais):
            if (vista is None or chave[0] == vista) and (rim is None or chave[1] == rim):
                del self.fundos_manuais[chave]
        self._fundo_fixo.clear()

    def _mascara_fundo(self, vista: str, rim: str) -> np.ndarray:
        """Região de fundo de um rim numa vista.

        Fundo à mão: o polígono desenhado, sem os pixels das ROIs dos dois rins.
        Automático: anel perirrenal (ver :func:`fundo.anel_perirrenal`).
        """
        if (vista, rim) in self._fundo_fixo:
            return self._fundo_fixo[(vista, rim)]
        outro = "E" if rim == "D" else "D"
        m_rim, m_outro = self._mascara_rim(vista, rim), self._mascara_rim(vista, outro)
        manual = self.fundos_manuais.get((vista, rim))
        linhas, colunas = self._dim(vista)
        if manual:
            chave = ("fundo-manual", vista, rim, tuple(manual), m_rim.tobytes(), m_outro.tobytes())
            if chave not in self._cache:
                return self._guardar(chave, roi.mascara_roi(manual, linhas, colunas) & ~m_rim & ~m_outro)
            return self._cache[chave]
        chave = ("anel", vista, rim, m_rim.tobytes(), m_outro.tobytes())
        if chave not in self._cache:
            return self._guardar(chave, anel_perirrenal(m_rim, m_outro, LARGURA_ANEL_PX))
        return self._cache[chave]

    def _origem_fundo(self, vista: str, rim: str) -> str:
        if (vista, rim) in self.fundos_manuais:
            return "manual"
        return "automatico"

    def _manuais_texto(self) -> list[str]:
        return [f"{NOME_RIM[r]} na {NOME_VISTA[v]}" for v in VISTAS for r in RINS if (v, r) in self.fundos_manuais]

    # ------------------------------------------------------------- resultados
    def calcular(self) -> ResultadoDMSA:
        problema = self._validacao_fundo()
        if problema:
            raise ErroSessao(problema)
        grupos = {}
        for vista in self._vistas_quantificadas():
            valores = self._valores(self._slot_vista(vista))
            grupos[vista] = {}
            for rim in RINS:
                fundo = None if self.metodo_fundo == "nenhum" else self._mascara_fundo(vista, rim)
                try:
                    grupos[vista][rim] = contagens_rim(valores, self._mascara_rim(vista, rim), fundo, rim, vista)
                except ValueError as erro:
                    raise ErroSessao(str(erro)) from None
        try:
            return calcular(grupos["post"], grupos.get("ant"))
        except ValueError as erro:
            raise ErroSessao(
                f"{erro} Confira as ROIs (as contagens corrigidas pelo fundo ficaram em zero)."
            ) from None

    def _rotulo_slot(self, s: Slot) -> str:
        a = self.arquivos[s.arquivo]
        return a.nome + (f" · quadro {s.quadro + 1}" if a.imagem.multiframe else "")

    def _arquivos_info(self) -> list[dict]:
        saida = []
        for inc in INCIDENCIAS:
            for s in self._com_incidencia(inc):
                saida.append({"rotulo": ROTULOS[inc], "nome": self._rotulo_slot(s)})
        return saida

    def _quadros_laudo(self) -> list[Slot]:
        """Slots da grade do laudo, na ordem POST, ANT, oblíquas."""
        return [s for inc in INCIDENCIAS for s in self._com_incidencia(inc)]

    def _camadas(self, s: Slot) -> tuple[list, list]:
        """ROIs e fundos a desenhar sobre um slot (só na posterior e na anterior definidas)."""
        vista = None
        if s is self._unico("POST"):
            vista = "post"
        elif s is self._unico("ANT"):
            vista = "ant"
        if vista is None:
            return [], []
        rois = [(k, self.roi_vista(vista, k)) for k in RINS if self.rois.get(k)]
        fundos = []
        if self.metodo_fundo == "anel" and not self._validacao_rois():
            fundos = [(k, self._mascara_fundo(vista, k)) for k in RINS]
        return rois, fundos

    def figura_png(self, slot: str, invertido: bool = False, janela: dict | None = None) -> bytes:
        s = self._slot(slot)
        valores = self._valores(s)
        jp = exibicao.janela_padrao(valores)
        nivel = float((janela or {}).get("nivel", jp.nivel))
        largura = float((janela or {}).get("largura", jp.largura))
        rois, fundos = self._camadas(s)
        return figuras.quadro_png(valores, nivel, largura, invertido, rois, fundos)

    def _imagens_laudo(self, invertido: bool, janelas: dict | None) -> list[tuple[str, bytes]]:
        return [
            (ROTULOS[s.incidencia], self.figura_png(s.id, invertido, (janelas or {}).get(s.id)))
            for s in self._quadros_laudo()
        ]

    def protocolo(self) -> dict:
        """Tudo o que é preciso para refazer o cálculo em lote no computador.

        Nomes e SHA-256 dos arquivos, quadros e incidências, ROIs (desenhadas
        e as da anterior já espelhadas e deslocadas), método de fundo e cada
        região de fundo usada, inclusive o anel automático (máscara em
        trechos [início, comprimento], linha a linha). Não contém pixels nem
        dados do paciente (mas os nomes dos arquivos podem conter).
        """
        imagens = [
            {
                "incidencia": s.incidencia,
                "nome": self.arquivos[s.arquivo].nome,
                "sha256": self._imagem(s).sha256,
                "quadro": s.quadro,
            }
            for s in self._quadros_laudo()
        ]
        regioes: dict = {}
        if not self._validacao_rois() and self.metodo_fundo == "anel":
            for vista in self._vistas_quantificadas():
                regioes[vista] = {}
                for rim in RINS:
                    item = {"origem": self._origem_fundo(vista, rim)}
                    if (vista, rim) in self.fundos_manuais:
                        item["poligono"] = _pontos_json(self.fundos_manuais[(vista, rim)])
                    item["mascara_rle"] = rle_codificar(self._mascara_fundo(vista, rim))
                    regioes[vista][rim] = item
        rois_ant = {}
        if self._unico("ANT"):
            rois_ant = {k: _pontos_json(self.roi_vista("ant", k) or []) for k in RINS}
        return {
            "ferramenta": "dmsa",
            "formato": 1,
            "versao_nucleo": __version__,
            "imagens": imagens,
            "rois_post": {k: _pontos_json(self.rois[k] or []) for k in RINS},
            "deslocamento_ant": {k: list(self.deslocamento_ant[k]) for k in RINS},
            "rois_ant": rois_ant,
            "fundo": {"metodo": self.metodo_fundo, "largura_anel_px": LARGURA_ANEL_PX, "regioes": regioes},
        }

    @classmethod
    def de_protocolo(cls, protocolo: dict, ler_arquivo) -> "Sessao":
        """Recria uma sessão a partir de um protocolo salvo pela interface.

        ``ler_arquivo(nome, sha256) -> bytes`` devolve cada DICOM; o SHA-256 é
        conferido. As regiões de fundo são as gravadas no protocolo, mesmo
        que o algoritmo automático mude em versões futuras.
        """
        if protocolo.get("ferramenta") != "dmsa":
            raise ErroSessao("Protocolo de outra ferramenta.")
        s = cls()
        por_sha: dict[str, str] = {}
        for item in protocolo["imagens"]:
            sha = item["sha256"]
            if sha not in por_sha:
                img = ler_dicom(ler_arquivo(item["nome"], sha))
                if img.sha256 != sha:
                    raise ErroSessao(f"{item['nome']}: arquivo diferente do usado no protocolo (SHA-256 não confere).")
                aid = s._novo_id("a")
                s.arquivos[aid] = Arquivo(aid, item["nome"], img)
                por_sha[sha] = aid
            sid = s._novo_id("s")
            s.slots[sid] = Slot(sid, por_sha[sha], int(item.get("quadro", 0)), item["incidencia"])
        s._apos_mudanca()
        for k in RINS:
            pts = protocolo.get("rois_post", {}).get(k)
            s.rois[k] = roi.normalizar(pts) if pts else None
            dx, dy = protocolo.get("deslocamento_ant", {}).get(k, (0.0, 0.0))
            s.deslocamento_ant[k] = (float(dx), float(dy))
        fundo = protocolo.get("fundo", {})
        s.metodo_fundo = fundo.get("metodo", "anel")
        for vista, por_rim in (fundo.get("regioes") or {}).items():
            linhas, colunas = s._dim(vista)
            for rim, item in por_rim.items():
                if item.get("poligono"):
                    s.fundos_manuais[(vista, rim)] = roi.normalizar(item["poligono"])
                if "mascara_rle" in item:
                    s._fundo_fixo[(vista, rim)] = rle_decodificar(item["mascara_rle"], linhas, colunas)
        return s

    # ---------------------------------------------------------------- imagem
    def imagem(self, pedido) -> bytes:
        """Bytes RGBA de um slot, com janela, inversão e (opcional) o fundo pintado.

        ``pedido`` (dict ou JSON): slot, nivel, largura, invertido, fundo (bool).
        """
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        s = self._slot(pedido["slot"])
        valores = self._valores(s)
        jp = exibicao.janela_padrao(valores)
        nivel = float(pedido["nivel"]) if pedido.get("nivel") is not None else jp.nivel
        largura = float(pedido["largura"]) if pedido.get("largura") is not None else jp.largura
        sobre = []
        if pedido.get("fundo"):
            try:
                _, fundos = self._camadas(s)
            except ErroSessao:
                fundos = []
            sobre = [(m, figuras.COR_RIM[k], 0.45) for k, m in fundos]
        return exibicao.renderizar_rgba(valores, nivel, largura, bool(pedido.get("invertido")), sobre)

    # ------------------------------------------------------------- serializar
    def estado(self) -> dict:
        slots = []
        for s in self.slots.values():
            img = self._imagem(s)
            valores = self._valores(s)
            jp = exibicao.janela_padrao(valores)
            slots.append(
                {
                    "id": s.id,
                    "arquivo": s.arquivo,
                    "nome": self.arquivos[s.arquivo].nome,
                    "rotulo": self._rotulo_slot(s),
                    "quadro": s.quadro,
                    "n_quadros": img.n_quadros,
                    "incidencia": s.incidencia,
                    "linhas": img.linhas,
                    "colunas": img.colunas,
                    "dimensoes": f"{img.colunas}×{img.linhas}",
                    "contagens": fmt_int(float(valores.sum())),
                    "horario": img.data_hora.strftime("%H:%M") if img.data_hora else None,
                    "avisos": list(img.avisos) + ([s.aviso] if s.aviso else []),
                    "janela": {"nivel": jp.nivel, "largura": jp.largura, "faixa": exibicao.faixa_valores(valores)},
                }
            )
        post, ant = self._unico("POST"), self._unico("ANT")
        duplicadas = sorted(
            {s.incidencia for s in self.slots.values() if s.incidencia != IGNORAR and len(self._com_incidencia(s.incidencia)) > 1}
        )
        rois: dict = {"post": {}, "ant": {}}
        if post:
            rois["post"] = {k: (_pontos_json(self.rois[k]) if self.rois[k] else None) for k in RINS}
        if post and ant:
            rois["ant"] = {k: (_pontos_json(self.roi_vista("ant", k)) if self.rois[k] else None) for k in RINS}
        deslocada = {k: self.deslocamento_ant[k] != (0.0, 0.0) for k in RINS}
        fundo = {"metodo": self.metodo_fundo, "largura_px": LARGURA_ANEL_PX, "regioes": {}, "texto": relatorio.descrever_fundo(self.metodo_fundo, self._manuais_texto())}
        if not self._validacao_rois():
            for vista in self._vistas_quantificadas():
                fundo["regioes"][vista] = {}
                for k in RINS:
                    m = self._mascara_fundo(vista, k)
                    manual = self.fundos_manuais.get((vista, k))
                    fundo["regioes"][vista][k] = {
                        "pixels": int(m.sum()),
                        "origem": self._origem_fundo(vista, k),
                        "poligono": _pontos_json(manual) if manual else None,
                    }
        return {
            "versao": __version__,
            "slots": slots,
            "incidencias": [{"valor": v, "rotulo": ROTULOS[v]} for v in (*INCIDENCIAS, IGNORAR)],
            "duplicadas": duplicadas,
            "post": post.id if post else None,
            "ant": ant.id if ant else None,
            "grade": [{"slot": s.id, "incidencia": s.incidencia, "rotulo": ROTULOS[s.incidencia]} for s in self._quadros_laudo()],
            "rois": rois,
            "deslocada": deslocada,
            "fundo": fundo,
            "avisos": self._avisos(),
            "erros": list(self.erros),
            "validacao": {
                "arquivos": self._validacao_arquivos(),
                "rois": self._validacao_rois(),
                "fundo": self._validacao_fundo(),
            },
        }

    def _resposta(self, extra: dict | None = None, com_estado: bool = True) -> str:
        r = {"ok": True}
        if extra:
            r.update(extra)
        if com_estado:
            r["estado"] = self.estado()
        return json.dumps(r, ensure_ascii=False)

    def _resultados(self) -> dict:
        r = self.calcular()
        return {
            "funcao": relatorio.tabela_funcao(r),
            "contagens": {
                "colunas": [{"chave": k, "titulo": t, "ajuda": a} for k, t, a in relatorio.COLUNAS_CONTAGENS],
                "linhas": relatorio.tabela_contagens(r),
            },
            "tem_anterior": r.ant is not None,
            "notas": list(relatorio.NOTAS_FORMULAS),
            "fundo_texto": relatorio.descrever_fundo(self.metodo_fundo, self._manuais_texto()),
            "tabelas_html": relatorio.tabelas_html(r),
            "tabelas_texto": relatorio.tabelas_texto(r),
            "versao": __version__,
        }

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
                from ..fantomas import fantoma_dmsa

                self.limpar()
                f = fantoma_dmsa()
                origem = f.multiframe if c.get("multiframe") else f.arquivos
                for nome, dados in origem.items():
                    self.adicionar_arquivo(f"fantoma_{nome}", dados)
                return self._resposta({"fantoma": {"rois": {k: _pontos_json(v) for k, v in f.rois.items()}, "esperado": f.esperado}})
            if acao == "definir_incidencia":
                self.definir_incidencia(c["slot"], c["incidencia"])
                return self._resposta()
            if acao == "remover_arquivo":
                self.remover_arquivo(c["arquivo"])
                return self._resposta()
            if acao == "desenhar_roi":
                self.desenhar_roi(c["rim"], c["pontos"])
                return self._resposta()
            if acao == "apagar_roi":
                self.apagar_roi(c["rim"])
                return self._resposta()
            if acao == "toca_roi":
                return self._resposta({"rim": self.toca_roi(c["vista"], c["x"], c["y"])}, com_estado=False)
            if acao == "arrastar_roi":
                confirmar = bool(c.get("confirmar"))
                extra = self.arrastar_roi(c["vista"], c["rim"], c["dx"], c["dy"], confirmar)
                return self._resposta(extra, com_estado=confirmar)
            if acao == "restaurar_espelho":
                self.restaurar_espelho(c.get("rim"))
                return self._resposta()
            if acao == "definir_fundo":
                self.definir_fundo(c["metodo"])
                return self._resposta()
            if acao == "desenhar_fundo":
                self.desenhar_fundo(c["vista"], c["rim"], c["pontos"])
                return self._resposta()
            if acao == "fundo_automatico":
                self.fundo_automatico(c.get("vista"), c.get("rim"))
                return self._resposta()
            if acao == "janela_arraste":
                j = exibicao.ajustar_janela_por_arraste(c["nivel"], c["largura"], c["dx"], c["dy"], c["faixa"])
                return self._resposta({"nivel": j.nivel, "largura": j.largura}, com_estado=False)
            if acao == "resultados":
                return self._resposta(self._resultados(), com_estado=False)
            if acao == "laudo":
                r = self.calcular()
                v = versoes()
                v.update({k: str(x) for k, x in (c.get("versoes_extra") or {}).items()})
                imagens = self._imagens_laudo(bool(c.get("invertido")), c.get("janelas")) if c.get("com_imagens", True) else []
                html = relatorio.laudo_html(
                    r,
                    self.metodo_fundo,
                    self._manuais_texto(),
                    v,
                    self._arquivos_info(),
                    paciente=str(c.get("paciente") or ""),
                    data_exame=str(c.get("data_exame") or ""),
                    imagens=imagens,
                    avisos=self._avisos(),
                )
                return self._resposta({"html": html}, com_estado=False)
            if acao == "protocolo":
                return self._resposta({"protocolo": self.protocolo()}, com_estado=False)
            raise ErroSessao(f"Comando desconhecido: {acao!r}.")
        except ErroSessao as erro:
            return json.dumps({"ok": False, "erro": str(erro)}, ensure_ascii=False)
        except (KeyError, TypeError, ValueError) as erro:
            return json.dumps({"ok": False, "erro": f"Comando inválido ({erro})."}, ensure_ascii=False)

    def exportar(self, pedido) -> bytes:
        """Arquivo para download: ``{"formato": "csv"|"xlsx"|"protocolo"|"png", ...}``.

        Para "png": ``slot``, ``invertido`` e, opcional, ``janela`` {nivel, largura}.
        """
        if isinstance(pedido, str):
            pedido = json.loads(pedido)
        formato = pedido.get("formato")
        if formato == "protocolo":
            return json.dumps(self.protocolo(), ensure_ascii=False, indent=2).encode("utf-8")
        if formato == "png":
            return self.figura_png(pedido["slot"], bool(pedido.get("invertido")), pedido.get("janela"))
        r = self.calcular()
        if formato == "csv":
            return relatorio.csv_resultados(r)
        if formato == "xlsx":
            return relatorio.xlsx_resultados(r, self.metodo_fundo, self._manuais_texto(), __version__)
        raise ErroSessao("Formato de exportação desconhecido.")
