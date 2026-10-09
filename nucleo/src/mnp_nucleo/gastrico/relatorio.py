"""Saídas do esvaziamento gástrico: tabela, curva (SVG), CSV, XLSX e laudo HTML.

Nada aqui depende do navegador: o mesmo laudo pode ser gerado em lote no
computador (ver :mod:`mnp_nucleo.gastrico.lote`).
"""

from __future__ import annotations

import math
from datetime import datetime
from html import escape
from typing import Sequence

from ..comum.tabela import fmt_dec, fmt_int, gerar_csv, gerar_xlsx
from .calculo import REFERENCIA_TOUGAS_2000, LinhaResultado

__all__ = [
    "COLUNAS",
    "linhas_formatadas",
    "curva_svg",
    "csv_resultados",
    "xlsx_resultados",
    "laudo_html",
    "NOTAS_FORMULAS",
    "AVISO",
]

AVISO = (
    "Ferramenta de pesquisa e ensino, ainda não validada para uso clínico. Auxílio ao cálculo; "
    "a interpretação é de responsabilidade do médico nuclear. Processamento 100% local: nenhum "
    "dado sai do seu computador."
)

# (chave, título, explicação) — a ordem é a da tabela e das exportações.
COLUNAS = (
    ("rotulo", "Tempo", "Tempo de aquisição; T0 é a primeira imagem."),
    ("minutos", "Tempo decorrido (min)", "Minutos desde o T0, lidos do DICOM ou editados."),
    ("mg_total", "Contagem total (MG)", "Média geométrica √(ANT × PÓS) das contagens da ROI inteira."),
    ("mg_proximal", "Contagem proximal (MG)", "Média geométrica da metade proximal (superior)."),
    ("mg_distal", "Contagem distal (MG)", "Média geométrica da metade distal (inferior)."),
    ("distribuicao_proximal", "Distribuição proximal (%)", "MG proximal ÷ MG total × 100, no próprio tempo."),
    ("esvaziamento", "Esvaziamento (%)", "100 − retenção."),
    ("retencao", "Retenção (%)", "MG(t) ÷ MG(T0) × 100, com correção de decaimento quando ativa."),
    ("retencao_proximal", "Retenção proximal (%)", "Retenção × distribuição proximal ÷ 100."),
    ("retencao_distal", "Retenção distal (%)", "Retenção − retenção proximal."),
)
_INTEIRAS = {"mg_total", "mg_proximal", "mg_distal"}

NOTAS_FORMULAS = (
    "MG = √(contagens ANT × contagens PÓS), por região (Abell 2008).",
    "Retenção(t) = MG(t) ÷ MG(T0) × 100 × 2^(t ÷ (T½ × 60)), t em minutos e T½ em horas (Donohoe 2009).",
    "Retenção proximal + retenção distal = retenção total, em todas as linhas.",
    "Na projeção posterior a ROI é espelhada (esquerda e direita trocam; superior e inferior se mantêm).",
    "Proximal e distal: metades com o mesmo número de pixels ao longo do eixo principal da ROI.",
)


def _fmt(chave: str, valor) -> str:
    if chave == "rotulo":
        return str(valor)
    if chave in _INTEIRAS:
        return fmt_int(valor)
    return fmt_dec(valor, 1)


def linhas_formatadas(linhas: Sequence[LinhaResultado]) -> list[dict]:
    """Linhas da tabela com números brutos e textos já formatados em pt-BR."""
    saida = []
    for l in linhas:
        d = l.como_dict()
        saida.append({"valores": d, "textos": {k: _fmt(k, d[k]) for k, _, _ in COLUNAS}})
    return saida


def _passo_bonito(amplitude: float, alvo: int = 6) -> float:
    if amplitude <= 0:
        return 1.0
    bruto = amplitude / alvo
    base = 10 ** math.floor(math.log10(bruto))
    for m in (1, 2, 2.5, 5, 10):
        if m * base >= bruto:
            return m * base
    return 10 * base


SERIES = (
    ("retencao", "Total", "serie-1", "circulo"),
    ("retencao_proximal", "Proximal", "serie-2", "quadrado"),
    ("retencao_distal", "Distal", "serie-3", "triangulo"),
)


def _marcador(forma: str, x: float, y: float, classe: str, titulo: str) -> str:
    r = 4.5
    t = f"<title>{escape(titulo)}</title>"
    if forma == "circulo":
        return f'<circle class="{classe} marca" cx="{x:.1f}" cy="{y:.1f}" r="{r}">{t}</circle>'
    if forma == "quadrado":
        return (
            f'<rect class="{classe} marca" x="{x - r:.1f}" y="{y - r:.1f}" '
            f'width="{2 * r}" height="{2 * r}" rx="1">{t}</rect>'
        )
    pts = f"{x:.1f},{y - r - 1:.1f} {x + r + 0.5:.1f},{y + r - 0.5:.1f} {x - r - 0.5:.1f},{y + r - 0.5:.1f}"
    return f'<polygon class="{classe} marca" points="{pts}">{t}</polygon>'


def curva_svg(linhas: Sequence[LinhaResultado], largura: int = 640, altura: int = 300) -> str:
    """Curva de retenção (total, proximal e distal) em SVG.

    As cores vêm de classes CSS (serie-1, serie-2, serie-3) definidas pela
    página; cada série tem também marcador próprio e rótulo direto, para não
    depender só da cor.
    """
    if not linhas:
        return ""
    m_esq, m_dir, m_sup, m_inf = 48, 92, 16, 40
    w, h = largura - m_esq - m_dir, altura - m_sup - m_inf
    xmax = max(l.minutos for l in linhas)
    passo_x = _passo_bonito(xmax if xmax > 0 else 60)
    xmax_eixo = max(passo_x, math.ceil(xmax / passo_x) * passo_x)
    ymax_dados = max(max(l.retencao, l.retencao_proximal, l.retencao_distal) for l in linhas)
    ymax = max(100.0, math.ceil(ymax_dados / 10.0) * 10.0)
    ymin_dados = min(min(l.retencao_proximal, l.retencao_distal, l.retencao) for l in linhas)
    ymin = min(0.0, math.floor(ymin_dados / 10.0) * 10.0)

    def px(v):
        return m_esq + (v / xmax_eixo) * w

    def py(v):
        return m_sup + (1 - (v - ymin) / (ymax - ymin)) * h

    partes = [
        f'<svg class="mnp-curva" viewBox="0 0 {largura} {altura}" role="img" '
        'aria-label="Curva de retenção gástrica total, proximal e distal ao longo do tempo" '
        'xmlns="http://www.w3.org/2000/svg">'
    ]
    passo_y = 20 if ymax - ymin <= 120 else _passo_bonito(ymax - ymin)
    v = ymin
    while v <= ymax + 1e-9:
        y = py(v)
        partes.append(f'<line class="grade" x1="{m_esq}" x2="{m_esq + w}" y1="{y:.1f}" y2="{y:.1f}"/>')
        partes.append(f'<text class="eixo" x="{m_esq - 8}" y="{y + 4:.1f}" text-anchor="end">{fmt_int(v)}</text>')
        v += passo_y
    v = 0.0
    while v <= xmax_eixo + 1e-9:
        x = px(v)
        partes.append(f'<text class="eixo" x="{x:.1f}" y="{m_sup + h + 18}" text-anchor="middle">{fmt_int(v)}</text>')
        v += passo_x
    partes.append(f'<line class="base" x1="{m_esq}" x2="{m_esq + w}" y1="{py(0):.1f}" y2="{py(0):.1f}"/>')
    partes.append(
        f'<text class="eixo-titulo" x="{m_esq + w / 2:.1f}" y="{altura - 4}" text-anchor="middle">'
        "Tempo decorrido (min)</text>"
    )
    partes.append(
        f'<text class="eixo-titulo" transform="translate(12 {m_sup + h / 2:.1f}) rotate(-90)" '
        'text-anchor="middle">Retenção (%)</text>'
    )

    rotulos = []
    for chave, nome, classe, forma in SERIES:
        pontos = [(px(l.minutos), py(getattr(l, chave))) for l in linhas]
        caminho = " ".join(f"{x:.1f},{y:.1f}" for x, y in pontos)
        partes.append(f'<polyline class="{classe} linha" points="{caminho}"/>')
        for l, (x, y) in zip(linhas, pontos):
            titulo = f"{l.rotulo} · {fmt_dec(l.minutos, 0)} min · {nome}: {fmt_dec(getattr(l, chave), 1)}%"
            partes.append(_marcador(forma, x, y, classe, titulo))
        rotulos.append([pontos[-1][1], nome, classe, pontos[-1][0]])

    # Rótulos diretos à direita do último ponto, afastados para não colidir.
    # De baixo para cima: nenhum rótulo abaixo da base do gráfico e 14 px entre eles.
    rotulos.sort(reverse=True)
    limite = m_sup + h - 4
    for r in rotulos:
        r[0] = min(r[0], limite)
        limite = r[0] - 14
    for y, nome, classe, x in rotulos:
        partes.append(f'<text class="rotulo-serie" x="{x + 10:.1f}" y="{y + 4:.1f}">{escape(nome)}</text>')
    partes.append("</svg>")
    return "".join(partes)


def _linhas_exportacao(linhas: Sequence[LinhaResultado]) -> list[list]:
    saida = []
    for l in linhas:
        d = l.como_dict()
        linha = []
        for chave, _, _ in COLUNAS:
            v = d[chave]
            if chave == "rotulo":
                linha.append(v)
            elif chave in _INTEIRAS:
                linha.append(int(round(v)))
            else:
                linha.append(round(float(v), 1))
        saida.append(linha)
    return saida


def _descricao_decaimento(meia_vida_h: float | None) -> str:
    if meia_vida_h is None:
        return "não"
    return f"sim (T½ = {fmt_dec(meia_vida_h, 4)} h)"


def csv_resultados(linhas: Sequence[LinhaResultado]) -> bytes:
    """Tabela de resultados em CSV (separador ";" e vírgula decimal)."""
    return gerar_csv([t for _, t, _ in COLUNAS], _linhas_exportacao(linhas))


def xlsx_resultados(linhas: Sequence[LinhaResultado], meia_vida_h: float | None, versao: str) -> bytes:
    """Tabela de resultados em Excel, com cabeçalho de parâmetros e versão do núcleo."""
    corpo = [
        ["Esvaziamento gástrico — cintilografia"],
        [f"Correção de decaimento: {_descricao_decaimento(meia_vida_h)}"],
        [f"Núcleo mnp-nucleo {versao}"],
        [],
        [t for _, t, _ in COLUNAS],
        *_linhas_exportacao(linhas),
        [],
        *[[n] for n in NOTAS_FORMULAS],
        [],
        [AVISO],
    ]
    return gerar_xlsx(corpo, nome_planilha="Esvaziamento gástrico", linhas_negrito=(0, 4))


def laudo_html(
    linhas: Sequence[LinhaResultado],
    meia_vida_h: float | None,
    versoes: dict,
    tempos_info: Sequence[dict],
    identificacao: str = "",
    gerado_em: datetime | None = None,
) -> str:
    """Laudo de processamento em HTML (fragmento), pronto para exibir e imprimir.

    Traz parâmetros, tabela, curva, valores de referência do protocolo
    padronizado, fórmulas, versões do software e o aviso de uso.
    Não contém dados do cabeçalho DICOM que identifiquem o paciente; a
    identificação, se houver, é a digitada pelo usuário.
    """
    gerado_em = gerado_em or datetime.now()
    v = versoes
    linhas_tab = linhas_formatadas(linhas)
    cab = "".join(f'<th scope="col">{escape(t)}</th>' for _, t, _ in COLUNAS)
    corpo = "".join(
        "<tr>" + "".join(
            (f'<th scope="row">{escape(l["textos"][k])}</th>' if k == "rotulo" else f"<td>{escape(l['textos'][k])}</td>")
            for k, _, _ in COLUNAS
        ) + "</tr>"
        for l in linhas_tab
    )
    arquivos = "".join(
        f"<li>{escape(t['rotulo'])}: {escape(t['ant'])} (ANT) e {escape(t['post'])} (PÓS)</li>" for t in tempos_info
    )
    refs = "".join(
        f"<tr><td>{r['minutos']}</td><td>{fmt_dec(r['mediana'], 1)}</td><td>{fmt_dec(r['p95'], 0)}</td></tr>"
        for r in REFERENCIA_TOUGAS_2000
    )
    notas = "".join(f"<li>{escape(n)}</li>" for n in NOTAS_FORMULAS)
    ident = (
        f'<p class="laudo-ident"><span class="mnp-eyebrow">Identificação</span> {escape(identificacao)}</p>'
        if identificacao.strip()
        else ""
    )
    pyodide = f" · Pyodide {escape(str(v['pyodide']))}" if v.get("pyodide") else ""
    return f"""<article class="laudo">
<header class="laudo-cab">
<p class="mnp-eyebrow">Laudo de processamento</p>
<h2>Cintilografia de esvaziamento gástrico</h2>
{ident}
<dl class="laudo-param">
<div><dt>Correção de decaimento</dt><dd>{escape(_descricao_decaimento(meia_vida_h))}</dd></div>
<div><dt>Tempos</dt><dd>{len(linhas)}</dd></div>
<div><dt>Processado em</dt><dd>{gerado_em.strftime('%d/%m/%Y %H:%M')}</dd></div>
<div><dt>Núcleo</dt><dd>mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))}</dd></div>
</dl>
</header>
<div class="laudo-tabela"><table><thead><tr>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>
<figure class="laudo-curva">{curva_svg(linhas)}
<figcaption>Retenção total, proximal e distal (% da atividade do T0).</figcaption></figure>
<section><h3>Valores de referência do protocolo padronizado</h3>
<p>Retenção gástrica em 123 voluntários saudáveis, refeição de baixo teor de gordura (substituto de ovo) marcada com ⁹⁹ᵐTc (Tougas 2000). Só se aplicam a esse protocolo; acima do percentil 95 sugere esvaziamento lento.</p>
<table class="laudo-ref"><thead><tr><th scope="col">Tempo (min)</th><th scope="col">Mediana (%)</th><th scope="col">Percentil 95 (%)</th></tr></thead><tbody>{refs}</tbody></table>
</section>
<section><h3>Fórmulas</h3><ul>{notas}</ul></section>
<section><h3>Arquivos</h3><ul class="laudo-arquivos">{arquivos}</ul></section>
<section class="laudo-refs"><h3>Referências</h3><ol>
<li>Abell TL, Camilleri M, Donohoe K, et al. Consensus recommendations for gastric emptying scintigraphy: a joint report of the American Neurogastroenterology and Motility Society and the Society of Nuclear Medicine. Am J Gastroenterol. 2008;103(3):753-63. doi:10.1111/j.1572-0241.2007.01636.x</li>
<li>Donohoe KJ, Maurer AH, Ziessman HA, et al. Procedure guideline for adult solid-meal gastric-emptying study 3.0. J Nucl Med Technol. 2009;37(3):196-200. doi:10.2967/jnmt.109.067843</li>
<li>Tougas G, Eaker EY, Abell TL, et al. Assessment of gastric emptying using a low fat meal: establishment of international control values. Am J Gastroenterol. 2000;95(6):1456-62. doi:10.1111/j.1572-0241.2000.02076.x</li>
<li>Orthey P, Yu D, Van Natta ML, et al. Intragastric meal distribution during gastric emptying scintigraphy for assessment of fundic accommodation: correlation with symptoms of gastroparesis. J Nucl Med. 2018;59(4):691-7. doi:10.2967/jnumed.117.197053</li>
</ol></section>
<footer class="laudo-rodape">
<p class="laudo-versoes">mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))} · pydicom {escape(str(v.get('pydicom', '?')))} · NumPy {escape(str(v.get('numpy', '?')))} · Python {escape(str(v.get('python', '?')))}{pyodide}</p>
<p class="laudo-aviso">{escape(AVISO)}</p>
</footer>
</article>"""
