"""Saídas da perfusão miocárdica: tabelas, CSV, XLSX e laudo HTML.

O mesmo laudo sai em lote no computador (:mod:`mnp_nucleo.perfusao.lote`).
"""

from __future__ import annotations

import base64
from datetime import datetime
from html import escape
from typing import Sequence

from ..comum.tabela import fmt_dec, gerar_csv, gerar_xlsx
from . import referencias as refs
from .escores import ESCALA, ESCORE_MAXIMO, Escores, faixa_sss
from .polar import NOME_TERRITORIO, NOMES, SEGMENTOS, TERRITORIO_DO_SEGMENTO, TERRITORIOS
from .reconstrucao import Filtro

__all__ = [
    "AVISO",
    "NOTAS_METODO",
    "tabela_segmentos",
    "resumo_escores",
    "tabela_territorios",
    "tabelas_html",
    "tabelas_texto",
    "csv_resultados",
    "xlsx_resultados",
    "descrever_filtro",
    "laudo_html",
]

AVISO = (
    "Ferramenta de pesquisa e ensino, ainda não validada para uso clínico. Auxílio ao cálculo; "
    "a interpretação é de responsabilidade do médico nuclear. Processamento 100% local: nenhum "
    "dado sai do seu computador."
)

NOTAS_METODO = (
    "Escala por segmento: 0 normal; 1 hipocaptação discreta; 2 moderada; 3 acentuada; 4 ausência de captação (SBC 2020; ASNC 2017).",
    "SSS = soma dos 17 escores do estresse; SRS = soma do repouso; SDS = SSS − SRS (ASNC 2017, Tabela 12).",
    "Percentual do VE = escore somado ÷ 68 × 100, porque 68 = 4 × 17 é o máximo (ASNC 2017).",
    "Faixas do SSS: < 4 normal; 4 a 8 discretamente anormal; 9 a 13 moderadamente anormal; > 13 francamente anormal (SBC 2020, citando Hachamovitch).",
    "Captação no mapa polar: perfil de contagem máxima ao longo de raios a partir do eixo, em % do máximo do VE; o valor do segmento é a média das amostras dele. Sem banco de normalidade: os valores apoiam a pontuação visual, não classificam.",
)


def _txt(v) -> str:
    return "—" if v is None else str(v)


def _pct(v) -> str:
    return "—" if v is None else fmt_dec(100.0 * v / ESCORE_MAXIMO, 1) + "%"


def tabela_segmentos(r: Escores, valores: dict) -> list[dict]:
    """Uma linha por segmento: nome, território, escores e captação (% do máximo) no estresse e no repouso."""
    saida = []
    for s in SEGMENTOS:
        e, p = r.estresse.get(s), r.repouso.get(s)
        ve = valores.get("estresse", {}).get(s)
        vr = valores.get("repouso", {}).get(s)
        saida.append(
            {
                "segmento": s,
                "nome": NOMES[s],
                "territorio": TERRITORIO_DO_SEGMENTO[s],
                "estresse": e,
                "repouso": p,
                "diferenca": None if e is None or p is None else e - p,
                "captacao_estresse": None if ve is None else round(ve, 1),
                "captacao_repouso": None if vr is None else round(vr, 1),
                "textos": {
                    "estresse": _txt(e),
                    "repouso": _txt(p),
                    "diferenca": _txt(None if e is None or p is None else e - p),
                    "captacao_estresse": "—" if ve is None else fmt_dec(ve, 0) + "%",
                    "captacao_repouso": "—" if vr is None else fmt_dec(vr, 0) + "%",
                },
            }
        )
    return saida


def resumo_escores(r: Escores) -> list[dict]:
    return [
        {"chave": "sss", "titulo": "SSS (estresse)", "valor": r.sss, "texto": _txt(r.sss), "percentual": _pct(r.sss),
         "faixa": faixa_sss(r.sss) if r.sss is not None else ""},
        {"chave": "srs", "titulo": "SRS (repouso)", "valor": r.srs, "texto": _txt(r.srs), "percentual": _pct(r.srs), "faixa": ""},
        {"chave": "sds", "titulo": "SDS (estresse − repouso)", "valor": r.sds, "texto": _txt(r.sds), "percentual": _pct(r.sds), "faixa": ""},
    ]


def tabela_territorios(r: Escores) -> list[dict]:
    return [
        {
            "territorio": t,
            "nome": NOME_TERRITORIO[t],
            "segmentos": ", ".join(str(s) for s in TERRITORIOS[t]),
            "estresse": _txt(d["estresse"]),
            "repouso": _txt(d["repouso"]),
            "diferenca": _txt(d["diferenca"]),
        }
        for t, d in r.territorios.items()
    ]


def descrever_filtro(f: Filtro, pixel_mm: float | None) -> str:
    cm = f" = {fmt_dec(f.ciclos_cm(pixel_mm), 2)} ciclos/cm (pixel de {fmt_dec(pixel_mm, 2)} mm)" if pixel_mm else ""
    return (
        f"Butterworth de ordem {f.ordem}, corte em {fmt_dec(f.corte_nyquist, 2)} da frequência de Nyquist "
        f"({fmt_dec(f.ciclos_pixel(), 3)} ciclos/pixel{cm}), nas projeções, antes da FBP com filtro rampa. "
        "Sem correção de atenuação ou de espalhamento."
    )


def _tabela_resumo_html(r: Escores) -> str:
    linhas = "".join(
        f'<tr><th scope="row">{escape(l["titulo"])}</th><td>{escape(l["texto"])}</td><td>{escape(l["percentual"])}</td><td>{escape(l["faixa"])}</td></tr>'
        for l in resumo_escores(r)
    )
    return ('<table class="laudo-resumo"><thead><tr><th scope="col">Escore</th><th scope="col">Valor</th>'
            '<th scope="col">% do VE</th><th scope="col">Faixa</th></tr></thead>'
            f"<tbody>{linhas}</tbody></table>")


def _tabela_territorios_html(r: Escores) -> str:
    linhas = "".join(
        f'<tr><th scope="row">{escape(l["nome"])} ({escape(l["territorio"])})</th><td>{escape(l["segmentos"])}</td>'
        f'<td>{escape(l["estresse"])}</td><td>{escape(l["repouso"])}</td><td>{escape(l["diferenca"])}</td></tr>'
        for l in tabela_territorios(r)
    )
    return ('<table class="laudo-territorios"><thead><tr><th scope="col">Território</th><th scope="col">Segmentos</th>'
            '<th scope="col">Soma estresse</th><th scope="col">Soma repouso</th><th scope="col">Diferença</th></tr></thead>'
            f"<tbody>{linhas}</tbody></table>")


def _tabela_segmentos_html(r: Escores, valores: dict) -> str:
    linhas = "".join(
        f'<tr><th scope="row">{l["segmento"]}. {escape(l["nome"])}</th><td>{escape(l["territorio"])}</td>'
        f'<td>{escape(l["textos"]["estresse"])}</td><td>{escape(l["textos"]["repouso"])}</td><td>{escape(l["textos"]["diferenca"])}</td>'
        f'<td>{escape(l["textos"]["captacao_estresse"])}</td><td>{escape(l["textos"]["captacao_repouso"])}</td></tr>'
        for l in tabela_segmentos(r, valores)
    )
    return ('<table class="laudo-segmentos"><thead><tr><th scope="col">Segmento</th><th scope="col">Território</th>'
            '<th scope="col">Escore estresse</th><th scope="col">Escore repouso</th><th scope="col">Diferença</th>'
            '<th scope="col">Captação estresse</th><th scope="col">Captação repouso</th></tr></thead>'
            f"<tbody>{linhas}</tbody></table>")


def tabelas_html(r: Escores, valores: dict) -> str:
    """Tabelas de resultados em HTML simples (para colar no Word)."""
    return _tabela_resumo_html(r) + _tabela_territorios_html(r) + _tabela_segmentos_html(r, valores)


def tabelas_texto(r: Escores, valores: dict) -> str:
    linhas = ["Escore\tValor\t% do VE\tFaixa"]
    for l in resumo_escores(r):
        linhas.append(f"{l['titulo']}\t{l['texto']}\t{l['percentual']}\t{l['faixa']}")
    linhas += ["", "Território\tSegmentos\tSoma estresse\tSoma repouso\tDiferença"]
    for l in tabela_territorios(r):
        linhas.append(f"{l['nome']} ({l['territorio']})\t{l['segmentos']}\t{l['estresse']}\t{l['repouso']}\t{l['diferenca']}")
    linhas += ["", "Segmento\tTerritório\tEscore estresse\tEscore repouso\tDiferença\tCaptação estresse\tCaptação repouso"]
    for l in tabela_segmentos(r, valores):
        t = l["textos"]
        linhas.append(f"{l['segmento']}. {l['nome']}\t{l['territorio']}\t{t['estresse']}\t{t['repouso']}\t{t['diferenca']}\t{t['captacao_estresse']}\t{t['captacao_repouso']}")
    return "\n".join(linhas) + "\n"


def _linhas_exportacao(r: Escores, valores: dict) -> list[list]:
    linhas: list[list] = [["Escore", "Valor", "% do VE", "Faixa"]]
    for l in resumo_escores(r):
        linhas.append([l["titulo"], l["valor"] if l["valor"] is not None else "—", round(100.0 * l["valor"] / ESCORE_MAXIMO, 1) if l["valor"] is not None else "—", l["faixa"]])
    linhas += [[], ["Território", "Segmentos", "Soma estresse", "Soma repouso", "Diferença"]]
    for t, d in r.territorios.items():
        linhas.append([f"{NOME_TERRITORIO[t]} ({t})", ", ".join(str(s) for s in TERRITORIOS[t]), _num(d["estresse"]), _num(d["repouso"]), _num(d["diferenca"])])
    linhas += [[], ["Segmento", "Nome", "Território", "Escore estresse", "Escore repouso", "Diferença", "Captação estresse (%)", "Captação repouso (%)"]]
    for l in tabela_segmentos(r, valores):
        linhas.append([l["segmento"], l["nome"], l["territorio"], _num(l["estresse"]), _num(l["repouso"]), _num(l["diferenca"]),
                       _num(l["captacao_estresse"]), _num(l["captacao_repouso"])])
    return linhas


def _num(v):
    return "—" if v is None else v


def csv_resultados(r: Escores, valores: dict) -> bytes:
    linhas = _linhas_exportacao(r, valores)
    return gerar_csv(linhas[0], linhas[1:])


def xlsx_resultados(r: Escores, valores: dict, filtro: Filtro, versao: str) -> bytes:
    corpo = [
        ["Cintilografia de perfusão miocárdica (SPECT)"],
        [f"Reconstrução: {descrever_filtro(filtro, None)}"],
        [f"Núcleo mnp-nucleo {versao}"],
        [],
        *_linhas_exportacao(r, valores),
        [],
        *[[n] for n in NOTAS_METODO],
        [],
        *[[f.citacao + (f" doi:{f.doi}" if f.doi else "")] for f in refs.BIBLIOGRAFIA],
        [],
        [AVISO],
    ]
    negrito = (0, 4, 4 + 4 + 1, 4 + 4 + 1 + 4 + 1)
    return gerar_xlsx(corpo, nome_planilha="Perfusao", linhas_negrito=negrito, largura_colunas=20)


def _img(png: bytes, alt: str, classe: str, largura: int | None = None) -> str:
    w = f' width="{largura}"' if largura else ""
    return f'<img class="{classe}" src="data:image/png;base64,{base64.b64encode(png).decode("ascii")}" alt="{escape(alt)}"{w}>'


NOME_CORTE = {"SA": "Eixo curto (do ápice para a base)", "VLA": "Eixo longo vertical (do septo para a lateral)", "HLA": "Eixo longo horizontal (de inferior para anterior)"}


def _figuras_html(imagens: dict | None) -> str:
    if not imagens:
        return ""
    blocos = []
    for tipo in ("SA", "VLA", "HLA"):
        linhas = imagens["cortes"].get(tipo) or []
        if not linhas:
            continue
        itens = "".join(f'<div class="laudo-faixa"><span>{escape(rot)}</span>{_img(png, f"{NOME_CORTE[tipo]}, {rot}", "laudo-cortes")}</div>' for rot, png in linhas)
        blocos.append(f'<figure class="laudo-bloco-cortes"><figcaption>{escape(NOME_CORTE[tipo])}</figcaption>{itens}</figure>')
    polares = "".join(
        f'<figure class="laudo-polar">{_img(png, f"Mapa polar, {rot}", "laudo-polar-img", 220)}<figcaption>{escape(rot)}</figcaption></figure>'
        for rot, png in imagens.get("polares", [])
    )
    if polares:
        blocos.append(f'<div class="laudo-polares">{polares}</div>'
                      '<p class="laudo-legenda">Mapas polares: ápice no centro, base na periferia; anterior em cima, septo à esquerda, '
                      "lateral à direita e inferior embaixo. Números: escore visual de cada segmento (– = não pontuado). Cores em % do "
                      "máximo do VE de cada estudo.</p>")
    return '<section class="laudo-imagens"><h3>Imagens</h3>' + "".join(blocos) + "</section>"


def _gated_html(arquivos_info: Sequence[dict]) -> str:
    itens = []
    for a in arquivos_info:
        g = a.get("gated")
        if not g:
            continue
        partes = []
        if "batimentos_aceitos" in g:
            partes.append(f"batimentos aceitos {g['batimentos_aceitos']}")
        if "batimentos_rejeitados" in g:
            partes.append(f"rejeitados {g['batimentos_rejeitados']}" + (f" ({fmt_dec(g['percentual_rejeitado'], 1)}%)" if "percentual_rejeitado" in g else ""))
        if "frequencia_cardiaca" in g:
            partes.append(f"FC {g['frequencia_cardiaca']} bpm")
        if "rr_minimo_ms" in g and "rr_maximo_ms" in g:
            partes.append(f"janela R-R {g['rr_minimo_ms']}–{g['rr_maximo_ms']} ms")
        if "observacao" in g:
            partes.append(g["observacao"])
        pct = a.get("intervalos") or []
        if pct:
            partes.append("contagens por intervalo (% da média): " + ", ".join(fmt_dec(x, 0) for x in pct))
        itens.append(f"<li>{escape(a['rotulo'])}: {escape('; '.join(partes))}.</li>")
    if not itens:
        return ""
    return ('<section><h3>Controle de qualidade do gated</h3><ul>' + "".join(itens) + "</ul>"
            '<p class="laudo-nota">Queda das contagens nos últimos intervalos sugere arritmia ou rejeição de batimentos inadequada. '
            "A janela de aceitação do intervalo R-R costuma ficar em torno de 20% (SBC 2020).</p></section>")


def laudo_html(
    r: Escores,
    valores: dict,
    filtro: Filtro,
    versoes: dict,
    arquivos_info: Sequence[dict],
    paciente: str = "",
    data_exame: str = "",
    imagens: dict | None = None,
    avisos: Sequence[str] = (),
    mapa: str = "quente",
    gerado_em: datetime | None = None,
    pixel_mm: float | None = None,
) -> str:
    """Laudo de processamento em HTML (fragmento), para exibir, imprimir e colar no Word."""
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
    arquivos = "".join(f"<li>{escape(a['rotulo'])}: {escape(a['nome'])} ({escape(a['detalhe'])})</li>" for a in arquivos_info)
    notas = "".join(f"<li>{escape(n)}</li>" for n in NOTAS_METODO)
    bib = "".join(f"<li>{escape(f.citacao)}{escape(f' doi:{f.doi}') if f.doi else ''}</li>" for f in refs.BIBLIOGRAFIA)
    pyodide = f" · Pyodide {escape(str(v['pyodide']))}" if v.get("pyodide") else ""
    escala = "; ".join(f"{k} {t}" for k, t in ESCALA.items())
    return f"""<article class="laudo">
<header class="laudo-cab">
<p class="mnp-eyebrow">Laudo de processamento</p>
<h2>Cintilografia de perfusão miocárdica (SPECT)</h2>
{ident}
<dl class="laudo-param">
<div><dt>SSS</dt><dd>{escape(_txt(r.sss))}</dd></div>
<div><dt>SRS</dt><dd>{escape(_txt(r.srs))}</dd></div>
<div><dt>SDS</dt><dd>{escape(_txt(r.sds))}</dd></div>
<div><dt>Processado em</dt><dd>{gerado_em.strftime('%d/%m/%Y %H:%M')}</dd></div>
<div><dt>Núcleo</dt><dd>mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))}</dd></div>
</dl>
</header>
{alertas}
{_figuras_html(imagens)}
<section><h3>Escores (pontuação visual)</h3>{_tabela_resumo_html(r)}{_tabela_territorios_html(r)}
<div class="laudo-tabela">{_tabela_segmentos_html(r, valores)}</div>
<p class="laudo-nota">Escala: {escape(escala)}. Os escores são os marcados pelo médico; a captação (% do máximo do VE) vem do mapa polar e não tem banco de normalidade.</p></section>
{_gated_html(arquivos_info)}
<section><h3>Método</h3>
<p><strong>Reconstrução:</strong> retroprojeção filtrada. {escape(descrever_filtro(filtro, pixel_mm))} As duas convenções do corte (fração de Nyquist e ciclos/pixel) aparecem lado a lado porque cada fabricante usa uma (Germano, 2001). O padrão inicial da ferramenta (ordem 11, corte 0,45 Nyquist) é o melhor resultado num fantoma de VE com ⁹⁹ᵐTc citado por Lyra e Ploussi (2011).</p>
<p><strong>Reorientação:</strong> eixo longo do VE traçado à mão num corte transaxial e depois no plano vertical que contém essa linha (Germano, 2001). Cortes exibidos no padrão de Cerqueira et al. (2002): eixo curto do ápice para a base, com anterior em cima e septo à esquerda; eixo longo vertical com o ápice à direita; eixo longo horizontal com o ápice em cima.</p>
<p><strong>Mapa polar e segmentos:</strong> 17 segmentos e territórios coronarianos de Cerqueira et al. (2002), como na ASNC (2017) e na SBC (2020). <strong>Desvio declarado:</strong> a amostragem do miocárdio desta versão é própria (perfil de contagem máxima ao longo de raios a partir do eixo, com um centro apical a 30% do comprimento do eixo, limitado entre 10 e 40 mm), e não a do QPS (Germano et al., 2000), que depende da detecção automática das bordas do VE e será implementada na fase do gated.</p>
</section>
<section><h3>Fórmulas e critérios</h3><ul>{notas}</ul></section>
<section><h3>Arquivos</h3><ul class="laudo-arquivos">{arquivos}</ul></section>
<section class="laudo-refs"><h3>Referências</h3><ol>{bib}</ol></section>
<footer class="laudo-rodape">
<p class="laudo-versoes">mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))} · pydicom {escape(str(v.get('pydicom', '?')))} · NumPy {escape(str(v.get('numpy', '?')))} · Python {escape(str(v.get('python', '?')))}{pyodide}</p>
<p class="laudo-aviso">{escape(AVISO)}</p>
</footer>
</article>"""
