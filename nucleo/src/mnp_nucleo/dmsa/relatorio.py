"""Saídas da cintilografia renal com DMSA: tabelas, CSV, XLSX e laudo HTML.

Nada aqui depende do navegador: o mesmo laudo sai em lote no computador
(ver :mod:`mnp_nucleo.dmsa.lote`).
"""

from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from typing import Sequence

from ..comum.tabela import fmt_dec, fmt_int, gerar_csv, gerar_xlsx
from . import referencias as refs
from .calculo import ResultadoDMSA
from .fundo import LARGURA_ANEL_PX

__all__ = [
    "AVISO",
    "COLUNAS_CONTAGENS",
    "AJUDA_PARAMETROS",
    "NOTAS_FORMULAS",
    "tabela_funcao",
    "tabela_contagens",
    "tabelas_html",
    "tabelas_texto",
    "descrever_fundo",
    "csv_resultados",
    "xlsx_resultados",
    "laudo_html",
]

AVISO = (
    "Ferramenta de pesquisa e ensino, ainda não validada para uso clínico. Auxílio ao cálculo; "
    "a interpretação é de responsabilidade do médico nuclear. Processamento 100% local: nenhum "
    "dado sai do seu computador."
)

NOME_RIM = {"D": "Rim direito", "E": "Rim esquerdo"}
NOME_VISTA = {"post": "posterior", "ant": "anterior"}

COLUNAS_CONTAGENS = (
    ("linha", "Rim e vista", "Rim e projeção em que as contagens foram medidas."),
    ("bruta", "Contagens na ROI", "Soma dos valores dos pixels da ROI do rim (com rescale do DICOM)."),
    ("area_px", "Área (pixels)", "Número de pixels da ROI do rim."),
    ("fundo_por_pixel", "Fundo (contagens/pixel)", "Média das contagens por pixel na região de fundo."),
    ("fundo_pixels", "Pixels do fundo", "Número de pixels da região de fundo."),
    ("fundo_no_rim", "Fundo subtraído", "Fundo por pixel × área da ROI do rim."),
    ("corrigida", "Contagens corrigidas", "Contagens na ROI − fundo subtraído (nunca abaixo de zero)."),
)

AJUDA_PARAMETROS = {
    "frr_post": "Contagens corrigidas do rim ÷ soma dos dois rins, na posterior. Suficiente na rotina (Vali 2022).",
    "frr_mg": "Como acima, com a média geométrica √(ANT × PÓS) de cada rim. Indicada em hidronefrose grave ou anomalia de posição (Vali 2022).",
    "area_post": "Área da ROI do rim ÷ soma das áreas, na posterior.",
    "area_mg": "Como acima, com a média geométrica das áreas √(A_ANT × A_PÓS).",
    "tam_post": "Contagem por pixel (contagens corrigidas ÷ área) de cada rim, normalizada para 100%, na posterior (Estorch 2004).",
    "tam_mg": "Como acima, com a média geométrica das contagens por pixel.",
}

NOTAS_FORMULAS = (
    "Contagem corrigida = contagens na ROI − (contagens do fundo ÷ pixels do fundo) × pixels da ROI; "
    "valor negativo vira zero.",
    "Função relativa do rim = contagem corrigida do rim ÷ (soma dos dois rins) × 100.",
    "Média geométrica de cada rim = √(contagem corrigida anterior × contagem corrigida posterior).",
    "Área relativa = pixels da ROI do rim ÷ (soma dos dois rins) × 100; com anterior, também pela média geométrica das áreas.",
    "Função corrigida pelo tamanho = (contagem ÷ área) do rim ÷ soma dos dois × 100; com anterior, também pela "
    "média geométrica √((C_ant ÷ A_ant) × (C_post ÷ A_post)).",
    "Os percentuais aparecem com uma casa decimal; o do rim esquerdo é 100 menos o do direito arredondado, "
    "para o par somar 100,0%.",
    "Na anterior, as ROIs da posterior são espelhadas (x' = largura − x; y igual) e podem ser deslocadas à parte.",
)


def _situacao(p) -> dict | None:
    if not p.comparar or not p.disponivel:
        return None
    return refs.comparar_funcao(p.d_arred)


def tabela_funcao(r: ResultadoDMSA) -> list[dict]:
    """Linhas da tabela de função relativa, com valores brutos, textos e a comparação (quando houver)."""
    saida = []
    for p in r.parametros:
        cmp_ = _situacao(p)
        saida.append(
            {
                "chave": p.chave,
                "titulo": p.titulo,
                "ajuda": AJUDA_PARAMETROS[p.chave],
                "d": p.d,
                "e": p.e,
                "d_arred": p.d_arred,
                "e_arred": p.e_arred,
                "texto_d": "—" if not p.disponivel else fmt_dec(p.d_arred, 1),
                "texto_e": "—" if not p.disponivel else fmt_dec(p.e_arred, 1),
                "referencia": cmp_,
            }
        )
    return saida


def tabela_contagens(r: ResultadoDMSA) -> list[dict]:
    """Linhas da tabela de contagens (rim × vista), mais a média geométrica de cada rim."""
    saida = []
    for rim in ("D", "E"):
        for vista, grupo in (("post", r.post), ("ant", r.ant)):
            if grupo is None:
                continue
            c = grupo[rim]
            fundo_no_rim = c.fundo_por_pixel * c.area_px
            valores = {
                "bruta": c.bruta,
                "area_px": c.area_px,
                "fundo_por_pixel": c.fundo_por_pixel,
                "fundo_pixels": c.fundo_pixels,
                "fundo_no_rim": fundo_no_rim,
                "corrigida": c.corrigida,
            }
            textos = {
                "linha": f"{NOME_RIM[rim]} · {NOME_VISTA[vista]}",
                "bruta": fmt_int(c.bruta),
                "area_px": fmt_int(c.area_px),
                "fundo_por_pixel": fmt_dec(c.fundo_por_pixel, 1) if c.fundo_pixels else "sem fundo",
                "fundo_pixels": fmt_int(c.fundo_pixels) if c.fundo_pixels else "—",
                "fundo_no_rim": fmt_int(fundo_no_rim) if c.fundo_pixels else "—",
                "corrigida": fmt_int(c.corrigida),
            }
            saida.append({"rim": rim, "vista": vista, "valores": valores, "textos": textos})
        if r.mg_contagens is not None:
            saida.append(
                {
                    "rim": rim,
                    "vista": "mg",
                    "valores": {"corrigida": r.mg_contagens[rim]},
                    "textos": {
                        "linha": f"{NOME_RIM[rim]} · média geométrica",
                        "bruta": "",
                        "area_px": "",
                        "fundo_por_pixel": "",
                        "fundo_pixels": "",
                        "fundo_no_rim": "",
                        "corrigida": fmt_int(r.mg_contagens[rim]),
                    },
                }
            )
    return saida


def descrever_fundo(metodo: str, manuais: Sequence[str] = ()) -> str:
    """Frase sobre o fundo usado, para a tela, as exportações e o laudo."""
    if metodo == "nenhum":
        return "Sem correção de fundo (opção para comparação; a diretriz recomenda subtrair o fundo)."
    texto = (
        f"Anel perirrenal circunferencial de {LARGURA_ANEL_PX} pixels em volta de cada rim, sem invadir a ROI do "
        "outro rim (Civan et al., 2022)."
    )
    if manuais:
        texto += " Fundo desenhado à mão em: " + ", ".join(manuais) + "."
    return texto


def _linhas_exportacao(r: ResultadoDMSA) -> list[list]:
    linhas: list[list] = [["Parâmetro", "Rim direito (%)", "Rim esquerdo (%)", "Referência", "Situação"]]
    for l in tabela_funcao(r):
        cmp_ = l["referencia"]
        linhas.append(
            [
                l["titulo"],
                l["d_arred"] if l["d_arred"] is not None else "—",
                l["e_arred"] if l["e_arred"] is not None else "—",
                cmp_["criterio"] if cmp_ else "",
                ("dentro" if cmp_["dentro"] else "fora") if cmp_ else "",
            ]
        )
    linhas.append([])
    linhas.append([t for _, t, _ in COLUNAS_CONTAGENS])
    for l in tabela_contagens(r):
        v = l["valores"]
        if l["vista"] == "mg":
            linhas.append([l["textos"]["linha"], "", "", "", "", "", round(v["corrigida"], 1)])
            continue
        tem_fundo = v["fundo_pixels"] > 0
        linhas.append(
            [
                l["textos"]["linha"],
                round(v["bruta"], 1),
                int(v["area_px"]),
                round(v["fundo_por_pixel"], 3) if tem_fundo else "sem fundo",
                int(v["fundo_pixels"]),
                round(v["fundo_no_rim"], 1),
                round(v["corrigida"], 1),
            ]
        )
    return linhas


def csv_resultados(r: ResultadoDMSA) -> bytes:
    """Resultados em CSV (separador ";" e vírgula decimal): função relativa e contagens."""
    linhas = _linhas_exportacao(r)
    return gerar_csv(linhas[0], linhas[1:])


def xlsx_resultados(r: ResultadoDMSA, metodo_fundo: str, manuais: Sequence[str], versao: str) -> bytes:
    """Resultados em Excel, com o método de fundo, a versão do núcleo, as fórmulas e o aviso."""
    corpo = [
        ["Cintilografia renal com 99mTc-DMSA"],
        [f"Fundo: {descrever_fundo(metodo_fundo, manuais)}"],
        [f"Núcleo mnp-nucleo {versao}"],
        [],
        *_linhas_exportacao(r),
        [],
        *[[n] for n in NOTAS_FORMULAS],
        [],
        *[[f.citacao + (f" doi:{f.doi}" if f.doi else "")] for f in refs.BIBLIOGRAFIA],
        [],
        [AVISO],
    ]
    cabecalhos = (0, 4, 4 + len(r.parametros) + 2)
    return gerar_xlsx(corpo, nome_planilha="DMSA", linhas_negrito=cabecalhos, largura_colunas=22)


def _tabela_funcao_html(r: ResultadoDMSA) -> str:
    corpo = []
    for l in tabela_funcao(r):
        cmp_ = l["referencia"]
        situacao = ("dentro" if cmp_["dentro"] else "fora") if cmp_ else ""
        corpo.append(
            f'<tr><th scope="row">{escape(l["titulo"])}</th><td>{escape(l["texto_d"])}</td>'
            f'<td>{escape(l["texto_e"])}</td><td>{escape(situacao)}</td></tr>'
        )
    return (
        '<table class="laudo-funcao"><thead><tr><th scope="col">Parâmetro</th><th scope="col">Rim direito (%)</th>'
        '<th scope="col">Rim esquerdo (%)</th><th scope="col">Faixa 45–55%</th></tr></thead>'
        f"<tbody>{''.join(corpo)}</tbody></table>"
    )


def _tabela_contagens_html(r: ResultadoDMSA) -> str:
    cab = "".join(f'<th scope="col">{escape(t)}</th>' for _, t, _ in COLUNAS_CONTAGENS)
    corpo = "".join(
        "<tr>"
        + "".join(
            (f'<th scope="row">{escape(l["textos"][k])}</th>' if k == "linha" else f"<td>{escape(l['textos'][k])}</td>")
            for k, _, _ in COLUNAS_CONTAGENS
        )
        + "</tr>"
        for l in tabela_contagens(r)
    )
    return f'<table class="laudo-contagens"><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table>'


def tabelas_html(r: ResultadoDMSA) -> str:
    """As duas tabelas de resultados em HTML simples (para copiar e colar no Word)."""
    return _tabela_funcao_html(r) + _tabela_contagens_html(r)


def tabelas_texto(r: ResultadoDMSA) -> str:
    """As tabelas em texto com tabulação (alternativa quando a área de transferência não aceita HTML)."""
    linhas = ["Parâmetro\tRim direito (%)\tRim esquerdo (%)\tFaixa 45–55%"]
    for l in tabela_funcao(r):
        cmp_ = l["referencia"]
        situacao = ("dentro" if cmp_["dentro"] else "fora") if cmp_ else ""
        linhas.append(f"{l['titulo']}\t{l['texto_d']}\t{l['texto_e']}\t{situacao}")
    linhas.append("")
    linhas.append("\t".join(t for _, t, _ in COLUNAS_CONTAGENS))
    for l in tabela_contagens(r):
        linhas.append("\t".join(l["textos"][k] for k, _, _ in COLUNAS_CONTAGENS))
    return "\n".join(linhas) + "\n"


def _figuras_html(imagens: Sequence[tuple[str, bytes]]) -> str:
    if not imagens:
        return ""
    itens = "".join(
        f'<figure class="laudo-quadro"><img src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" '
        f'alt="{escape(rotulo)}" width="220" height="220"><figcaption>{escape(rotulo)}</figcaption></figure>'
        for rotulo, png in imagens
    )
    return (
        '<section class="laudo-imagens"><h3>Imagens do estudo</h3>'
        f'<div class="laudo-grade">{itens}</div>'
        '<p class="laudo-legenda">Contorno âmbar: rim direito. Contorno verde-azulado: rim esquerdo. '
        "Região translúcida: fundo.</p></section>"
    )


def laudo_html(
    r: ResultadoDMSA,
    metodo_fundo: str,
    manuais: Sequence[str],
    versoes: dict,
    arquivos_info: Sequence[dict],
    paciente: str = "",
    data_exame: str = "",
    imagens: Sequence[tuple[str, bytes]] = (),
    avisos: Sequence[str] = (),
    gerado_em: datetime | None = None,
) -> str:
    """Laudo de processamento em HTML (fragmento), para exibir, imprimir e colar no Word.

    Traz identificação digitada pelo usuário (nunca lida do DICOM), imagens
    com ROIs e fundo, as tabelas, o método, as fórmulas, as fontes, as
    versões do software e o aviso de uso.
    """
    gerado_em = gerado_em or datetime.now()
    v = versoes
    ident = ""
    if paciente.strip() or data_exame.strip():
        ident = (
            '<dl class="laudo-param laudo-ident">'
            + (f"<div><dt>Paciente</dt><dd>{escape(paciente)}</dd></div>" if paciente.strip() else "")
            + (f"<div><dt>Data do exame</dt><dd>{escape(data_exame)}</dd></div>" if data_exame.strip() else "")
            + "</dl>"
        )
    alertas = "".join(f"<li>{escape(a)}</li>" for a in avisos)
    alertas = f'<section class="laudo-alertas"><h3>Atenção</h3><ul>{alertas}</ul></section>' if avisos else ""
    arquivos = "".join(f"<li>{escape(a['rotulo'])}: {escape(a['nome'])}</li>" for a in arquivos_info)
    notas = "".join(f"<li>{escape(n)}</li>" for n in NOTAS_FORMULAS)
    bib = "".join(f"<li>{escape(f.citacao)}{escape(f' doi:{f.doi}') if f.doi else ''}</li>" for f in refs.BIBLIOGRAFIA)
    pyodide = f" · Pyodide {escape(str(v['pyodide']))}" if v.get("pyodide") else ""
    vistas = "posterior e anterior" if r.ant is not None else "posterior"
    return f"""<article class="laudo">
<header class="laudo-cab">
<p class="mnp-eyebrow">Laudo de processamento</p>
<h2>Cintilografia renal com <span class="radiofarmaco">⁹⁹ᵐTc-DMSA</span></h2>
{ident}
<dl class="laudo-param">
<div><dt>Vistas quantificadas</dt><dd>{escape(vistas)}</dd></div>
<div><dt>Fundo</dt><dd>{"anel perirrenal" if metodo_fundo == "anel" else "sem correção"}</dd></div>
<div><dt>Processado em</dt><dd>{gerado_em.strftime('%d/%m/%Y %H:%M')}</dd></div>
<div><dt>Núcleo</dt><dd>mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))}</dd></div>
</dl>
</header>
{alertas}
{_figuras_html(imagens)}
<section><h3>Função renal relativa</h3>{_tabela_funcao_html(r)}
<p class="laudo-nota">Faixa normal: {escape(refs.CRITERIO)}. A comparação usa o valor arredondado a uma casa. Área relativa e função corrigida pelo tamanho não têm faixa de normalidade conferida: servem de apoio à interpretação.</p></section>
<section><h3>Contagens</h3><div class="laudo-tabela">{_tabela_contagens_html(r)}</div></section>
<section><h3>Método</h3>
<p><strong>ROIs:</strong> desenhadas à mão sobre cada rim inteiro na posterior; na anterior, espelhadas. Na rotina, a função pela posterior basta; a média geométrica é a indicada em hidronefrose grave e em rim pélvico, ectópico, em ferradura ou fundido (Vali et al., 2022).</p>
<p><strong>Fundo:</strong> {escape(descrever_fundo(metodo_fundo, manuais))} A diretriz manda subtrair o fundo medido perto do rim, fora do parênquima e de áreas de captação aumentada, sem fixar a forma da região (Vali et al., 2022). A ferramenta usa o anel em volta do rim inteiro porque, em 212 pacientes, só esse fundo não diferiu da função medida no SPECT; sem fundo e com crescente ínfero-lateral, a diferença foi significativa (Civan et al., 2022). A largura de {LARGURA_ANEL_PX} pixels é escolha desta ferramenta. Contexto: na auditoria do Reino Unido, a forma de subtrair o fundo foi uma das fontes de diferença entre hospitais (Fleming et al., 1998); regiões de fundo diferentes mudam o resultado sobretudo abaixo de 45%, e no seguimento o fundo deve ser feito sempre do mesmo jeito (Girotto et al., 2008).</p>
<p><strong>Correção pelo tamanho:</strong> quando um rim é pequeno, a função relativa cai mesmo que o parênquima seja normal; corrigir pelo tamanho ajuda a separar o rim pequeno e normal do hipofuncionante (Estorch et al., 2004). Aqui o tamanho é a área da ROI na imagem planar, uma projeção: a área cresce menos que o volume, e a correção por área aproxima, mas não iguala, a correção por volume.</p>
<p><strong>Faixa normal:</strong> vem de diretriz pediátrica (Vali et al., 2022) e é aplicada aqui a qualquer idade.</p>
</section>
<section><h3>Fórmulas</h3><ul>{notas}</ul></section>
<section><h3>Arquivos</h3><ul class="laudo-arquivos">{arquivos}</ul></section>
<section class="laudo-refs"><h3>Referências</h3><ol>{bib}</ol></section>
<footer class="laudo-rodape">
<p class="laudo-versoes">mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))} · pydicom {escape(str(v.get('pydicom', '?')))} · NumPy {escape(str(v.get('numpy', '?')))} · Python {escape(str(v.get('python', '?')))}{pyodide}</p>
<p class="laudo-aviso">{escape(AVISO)}</p>
</footer>
</article>"""
