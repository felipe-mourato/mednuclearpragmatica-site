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
    "funcao_tabelas_html",
    "funcao_texto",
    "linhas_funcao",
    "NOTAS_FUNCAO",
    "automatico_html",
    "linhas_automatico",
]

AVISO = (
    "Ferramenta de pesquisa e ensino, ainda não validada para uso clínico. Auxílio ao cálculo; "
    "a interpretação é de responsabilidade do médico nuclear. Processamento 100% local: nenhum "
    "dado sai do seu computador."
)

#: Escala do mapa das diferenças (repouso − estresse), em pontos percentuais (só exibição).
TETO_DIFERENCA = 30.0

NOTAS_METODO = (
    "Escala por segmento: 0 normal; 1 hipocaptação discreta; 2 moderada; 3 acentuada; 4 ausência de captação (SBC 2020; ASNC 2017).",
    "SSS = soma dos 17 escores do estresse; SRS = soma do repouso; SDS = SSS − SRS (ASNC 2017, Tabela 12).",
    "Percentual do VE = escore somado ÷ 68 × 100, porque 68 = 4 × 17 é o máximo (ASNC 2017).",
    "Faixas do SSS: < 4 normal; 4 a 8 discretamente anormal; 9 a 13 moderadamente anormal; > 13 francamente anormal (SBC 2020, citando Hachamovitch).",
    "Captação no mapa polar: perfil de contagem máxima ao longo de raios a partir do eixo, em % do máximo do VE; o valor do segmento é a média das amostras dele. Sem banco de normalidade: os valores apoiam a pontuação visual, não classificam.",
    "Diferença de captação: repouso menos estresse, amostra a amostra, em pontos percentuais (cada estudo normalizado ao máximo do próprio VE). Positiva = captação maior no repouso, como na reversibilidade. Como cada estudo é normalizado ao próprio máximo, um defeito extenso no estresse muda a referência; é apoio à pontuação, não critério.",
)


NOTAS_FUNCAO = (
    "FE = (VDF − VSF) ÷ VDF × 100; VDF e VSF = maior e menor volume da curva de volume do gated (diástole e sístole finais).",
    "Bordas do VE pelo método do QGS (Germano et al., J Nucl Med 1995;36:2138-47): segmentação por limiar de 50% e clusters; "
    "superfície de contagem máxima a partir do centro de massa e elipsoide iterado; perfis normais ao elipsoide com o detector "
    "de segunda derivada da gaussiana (σ = 10 mm); plano valvar com limiar de 25% na diástole; gaussiana assimétrica em perfis "
    "de ±20 mm, com endocárdio e epicárdio a 65% do desvio-padrão; volume miocárdico constante nos outros intervalos. "
    "Implementação própria a partir do artigo, com as escolhas declaradas no código; não é o programa comercial.",
    "Motilidade: deslocamento do endocárdio da diástole para a sístole final (mm; mapa de 0 a 10 mm). Espessamento: aumento "
    "relativo da espessura geométrica da diástole para a sístole final (%; mapa de 0 a 100%). Sem banco de normalidade: o septo "
    "costuma mover menos que a parede lateral e o ápice espessa mais que a base, mesmo em pessoas normais (manual do QGS).",
    "Escores visuais: motilidade 0 normal, 1 hipocinesia discreta, 2 moderada, 3 acentuada, 4 acinesia, 5 discinesia; "
    "espessamento 0 normal, 1 redução discreta, 2 redução moderada ou acentuada, 3 ausência de espessamento (SBC 2020, Tabela 19). "
    "SMS e STS = somas dos 17 segmentos; % = soma ÷ 85 (motilidade) ou ÷ 51 (espessamento).",
    "TID = volume endocárdico no estresse ÷ no repouso, nas imagens não sincronizadas, pelo mesmo método de bordas (Abidov 2004). "
    "Mostrada sem ponto de corte: o limiar depende do protocolo, do radiofármaco e do programa.",
    "Volumes indexados pela superfície corporal de Mosteller (√(altura × peso ÷ 3600)), com peso e altura digitados.",
)


def _sinal(v: float) -> str:
    """Diferença em pontos percentuais com sinal: +10, −3, 0."""
    r = round(v)
    return ("+" if r > 0 else "−" if r < 0 else "") + fmt_dec(abs(r), 0)


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
                "captacao_diferenca": None if ve is None or vr is None else round(vr - ve, 1),
                "textos": {
                    "estresse": _txt(e),
                    "repouso": _txt(p),
                    "diferenca": _txt(None if e is None or p is None else e - p),
                    "captacao_estresse": "—" if ve is None else fmt_dec(ve, 0) + "%",
                    "captacao_repouso": "—" if vr is None else fmt_dec(vr, 0) + "%",
                    "captacao_diferenca": "—" if ve is None or vr is None else _sinal(vr - ve),
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
        f'<td>{escape(l["textos"]["captacao_estresse"])}</td><td>{escape(l["textos"]["captacao_repouso"])}</td>'
        f'<td>{escape(l["textos"]["captacao_diferenca"])}</td></tr>'
        for l in tabela_segmentos(r, valores)
    )
    return ('<table class="laudo-segmentos"><thead><tr><th scope="col">Segmento</th><th scope="col">Território</th>'
            '<th scope="col">Escore estresse</th><th scope="col">Escore repouso</th><th scope="col">Diferença</th>'
            '<th scope="col">Captação estresse</th><th scope="col">Captação repouso</th>'
            '<th scope="col">Captação repouso − estresse (pontos)</th></tr></thead>'
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
    linhas += ["", "Segmento\tTerritório\tEscore estresse\tEscore repouso\tDiferença\tCaptação estresse\tCaptação repouso\tCaptação repouso − estresse"]
    for l in tabela_segmentos(r, valores):
        t = l["textos"]
        linhas.append(f"{l['segmento']}. {l['nome']}\t{l['territorio']}\t{t['estresse']}\t{t['repouso']}\t{t['diferenca']}\t{t['captacao_estresse']}\t{t['captacao_repouso']}\t{t['captacao_diferenca']}")
    return "\n".join(linhas) + "\n"


def _linhas_exportacao(r: Escores, valores: dict) -> list[list]:
    linhas: list[list] = [["Escore", "Valor", "% do VE", "Faixa"]]
    for l in resumo_escores(r):
        linhas.append([l["titulo"], l["valor"] if l["valor"] is not None else "—", round(100.0 * l["valor"] / ESCORE_MAXIMO, 1) if l["valor"] is not None else "—", l["faixa"]])
    linhas += [[], ["Território", "Segmentos", "Soma estresse", "Soma repouso", "Diferença"]]
    for t, d in r.territorios.items():
        linhas.append([f"{NOME_TERRITORIO[t]} ({t})", ", ".join(str(s) for s in TERRITORIOS[t]), _num(d["estresse"]), _num(d["repouso"]), _num(d["diferenca"])])
    linhas += [[], ["Segmento", "Nome", "Território", "Escore estresse", "Escore repouso", "Diferença", "Captação estresse (%)", "Captação repouso (%)", "Captação repouso − estresse (pontos)"]]
    for l in tabela_segmentos(r, valores):
        linhas.append([l["segmento"], l["nome"], l["territorio"], _num(l["estresse"]), _num(l["repouso"]), _num(l["diferenca"]),
                       _num(l["captacao_estresse"]), _num(l["captacao_repouso"]), _num(l["captacao_diferenca"])])
    return linhas


def _num(v):
    return "—" if v is None else v


def _f(v, casas=1):
    return "—" if v is None else round(float(v), casas)


def linhas_funcao(fun: dict | None) -> list[list]:
    """Linhas do gated para CSV e planilha: resumo por estudo, TID e valores e escores por segmento."""
    if not fun:
        return []
    est = fun.get("estudos") or {}
    linhas: list[list] = []
    if est:
        linhas += [["Função (gated)", "FE (%)", "VDF (mL)", "VSF (mL)", "VS (mL)", "VDF/SC (mL/m²)", "VSF/SC (mL/m²)",
                    "Diástole final (intervalo)", "Sístole final (intervalo)", "SMS", "SM%", "STS", "ST%", "Volumes por intervalo (mL)"]]
        for d in est.values():
            ind = d.get("indices") or {}
            sms, sts = (d.get("somas") or {}).get("sms"), (d.get("somas") or {}).get("sts")
            linhas.append([d["rotulo"], d["fe"], d["vdf_ml"], d["vsf_ml"], d["vs_ml"], _f(ind.get("vdf_ml_m2")), _f(ind.get("vsf_ml_m2")),
                           d["ed"], d["es"], sms["soma"] if sms else "—", sms["percentual"] if sms else "—",
                           sts["soma"] if sts else "—", sts["percentual"] if sts else "—",
                           "; ".join(fmt_dec(v, 1) for v in d["volumes_ml"])])
    tid = fun.get("tid")
    if tid:
        linhas += [[], ["TID (não sincronizadas)", "Volume estresse (mL)", "Volume repouso (mL)", "TID"],
                   ["Estresse ÷ repouso", tid["estresse_ml"], tid["repouso_ml"], tid["tid"]]]
    if fun.get("superficie_corporal"):
        linhas += [["Superfície corporal (m², Mosteller)", fun["superficie_corporal"]]]
    if est:
        cab = ["Segmento", "Nome"]
        for d in est.values():
            cab += [f"Motilidade {d['rotulo'].lower()} (mm)", f"Espessamento {d['rotulo'].lower()} (%)",
                    f"Escore motilidade {d['rotulo'].lower()}", f"Escore espessamento {d['rotulo'].lower()}"]
        linhas += [[], cab]
        for s in SEGMENTOS:
            ln = [s, NOMES[s]]
            for d in est.values():
                seg = d["segmentos"][str(s)]
                em = d["mapas"]["motilidade"]["escores"].get(str(s))
                ee = d["mapas"]["espessamento"]["escores"].get(str(s))
                ln += [seg["motilidade_mm"], seg["espessamento"], _num(em), _num(ee)]
            linhas.append(ln)
    return linhas


def csv_resultados(r: Escores, valores: dict, fun: dict | None = None, auto: dict | None = None) -> bytes:
    linhas = _linhas_exportacao(r, valores)
    la = linhas_automatico(auto)
    linhas = linhas + ([[]] + la if la else [])
    extra = linhas_funcao(fun)
    return gerar_csv(linhas[0], linhas[1:] + ([[]] + extra if extra else []))


def xlsx_resultados(r: Escores, valores: dict, filtro: Filtro, versao: str, fun: dict | None = None, auto: dict | None = None) -> bytes:
    extra = linhas_funcao(fun)
    la = linhas_automatico(auto)
    corpo = [
        ["Cintilografia de perfusão miocárdica (SPECT)"],
        [f"Reconstrução: {descrever_filtro(filtro, None)}"],
        [f"Núcleo mnp-nucleo {versao}"],
        [],
        *_linhas_exportacao(r, valores),
        *([[]] + la if la else []),
        *([[]] + extra if extra else []),
        [],
        *[[n] for n in NOTAS_METODO],
        *([[n] for n in NOTAS_FUNCAO] if extra else []),
        [],
        *[[f.citacao + (f" doi:{f.doi}" if f.doi else "")] for f in refs.BIBLIOGRAFIA + (refs.BIBLIOGRAFIA_GATED if extra else ())],
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
                      "máximo do VE de cada estudo. Mapa das diferenças: captação do repouso menos a do estresse, em pontos percentuais, "
                      f"de 0 a {TETO_DIFERENCA:.0f} (diferença negativa aparece como 0); valores por segmento na tabela.</p>")
    return '<section class="laudo-imagens"><h3>Imagens</h3>' + "".join(blocos) + "</section>"


def linhas_automatico(auto: dict | None) -> list[list]:
    """Linhas do escore automático (guia) para CSV e planilha."""
    if not auto:
        return []
    est = auto["estudos"]
    sexo = {"F": "feminino", "M": "masculino"}[auto["sexo"]]
    so = auto["somas"]
    linhas: list[list] = [[f"Escore automático (guia; banco espanhol, sexo {sexo})", "SSS", "SRS", "SDS"],
                          ["Somas automáticas", _num(so["sss"]), _num(so["srs"]), _num(so["sds"])], []]
    cab = ["Segmento", "Nome"]
    for e in ("estresse", "repouso"):
        if e in est:
            cab += [f"Captação {e} (%)", f"Banco {e}: média", f"Banco {e}: DP", f"z {e}", f"Escore automático {e}"]
    linhas.append(cab)
    for s in SEGMENTOS:
        ln = [s, NOMES[s]]
        for e in ("estresse", "repouso"):
            if e in est:
                d = est[e][s]
                ln += [round(d["captacao"], 1), d["media"], d["dp"], round(d["z"], 2), d["escore"]]
        linhas.append(ln)
    linhas += [[auto["descricao"]]]
    return linhas


def automatico_html(auto: dict | None, imagens: list | None = None) -> str:
    """Seção do escore automático (guia), com o alerta do banco de normalidade."""
    if not auto:
        return ""
    est = auto["estudos"]
    sexo = {"F": "feminino", "M": "masculino"}[auto["sexo"]]
    so = auto["somas"]
    cab = "".join(f'<th scope="col">{escape(e.capitalize())}: captação · z · escore</th>' for e in ("estresse", "repouso") if e in est)
    corpo = ""
    for s in SEGMENTOS:
        cel = "".join(
            f'<td>{fmt_dec(est[e][s]["captacao"], 0)}% · {fmt_dec(est[e][s]["z"], 1)} · {est[e][s]["escore"]}</td>'
            for e in ("estresse", "repouso") if e in est)
        corpo += f'<tr><th scope="row">{s}. {escape(NOMES[s])}</th>{cel}</tr>'
    figs = "".join(f'<figure class="laudo-polar">{_img(png, f"Escore automático, {rot}", "laudo-polar-img", 200)}<figcaption>{escape(rot)}</figcaption></figure>'
                   for rot, png in (imagens or []))
    return (f'<section class="laudo-automatico"><h3>Escore automático (guia)</h3>'
            f'<p class="laudo-alerta-banco"><strong>Atenção:</strong> {escape(auto["descricao"])}</p>'
            f'<p>Sexo escolhido: {sexo}. SSS automático {escape(_txt(so["sss"]))}; SRS automático {escape(_txt(so["srs"]))}; '
            f'SDS automático {escape(_txt(so["sds"]))}.</p>'
            + (f'<div class="laudo-polares">{figs}</div>' if figs else "")
            + f'<div class="laudo-tabela"><table class="laudo-auto"><thead><tr><th scope="col">Segmento</th>{cab}</tr></thead><tbody>{corpo}</tbody></table></div></section>')


def _curva_svg(volumes: Sequence[float], ed: int, es: int) -> str:
    """Curva de volume (mL por intervalo) em SVG simples, com o primeiro intervalo repetido no fim (como no QGS)."""
    v = list(volumes) + [volumes[0]]
    n = len(v)
    L, A, m = 260, 120, 28
    vmax = max(v) * 1.1 or 1.0
    x = lambda i: m + i * (L - m - 8) / max(n - 1, 1)  # noqa: E731
    y = lambda val: A - 18 - val / vmax * (A - 30)  # noqa: E731
    pts = " ".join(f"{x(i):.1f},{y(val):.1f}" for i, val in enumerate(v))
    marcas = "".join(
        f'<circle cx="{x(i):.1f}" cy="{y(v[i]):.1f}" r="3.5" fill="{cor}"/><text x="{x(i):.1f}" y="{y(v[i]) - 7:.1f}" font-size="9" text-anchor="middle">{rot}</text>'
        for i, cor, rot in ((ed, "#b33a1f", "VDF"), (es, "#1f4f8f", "VSF"))
    )
    eixo_x = "".join(f'<text x="{x(i):.1f}" y="{A - 4}" font-size="8" text-anchor="middle">{(i % (n - 1)) + 1}</text>' for i in range(n))
    return (f'<svg class="laudo-curva" viewBox="0 0 {L} {A}" width="{L}" height="{A}" role="img" aria-label="Curva de volume do VE">'
            f'<line x1="{m}" y1="{A - 18}" x2="{L - 8}" y2="{A - 18}" stroke="#999" stroke-width="0.6"/>'
            f'<text x="4" y="12" font-size="8">mL</text><text x="4" y="{y(vmax / 1.1):.1f}" font-size="8">{fmt_dec(vmax / 1.1, 0)}</text>'
            f'<polyline points="{pts}" fill="none" stroke="#333" stroke-width="1.4"/>{marcas}{eixo_x}</svg>')


def funcao_tabelas_html(fun: dict | None) -> str:
    if not fun:
        return ""
    est = fun.get("estudos") or {}
    partes = []
    if est:
        linhas = ""
        for d in est.values():
            ind = d.get("indices") or {}
            sms, sts = d["somas"]["sms"], d["somas"]["sts"]
            linhas += (f'<tr><th scope="row">{escape(d["rotulo"])}</th><td>{fmt_dec(d["fe"], 0)}%</td><td>{fmt_dec(d["vdf_ml"], 0)} mL'
                       + (f' ({fmt_dec(ind["vdf_ml_m2"], 0)} mL/m²)' if ind else "") + f'</td><td>{fmt_dec(d["vsf_ml"], 0)} mL'
                       + (f' ({fmt_dec(ind["vsf_ml_m2"], 0)} mL/m²)' if ind else "") + f'</td><td>{fmt_dec(d["vs_ml"], 0)} mL</td>'
                       f'<td>{d["ed"]} / {d["es"]} de {d["n_intervalos"]}</td>'
                       f'<td>{escape(_txt(sms and sms["soma"]))}</td><td>{escape(_txt(sts and sts["soma"]))}</td></tr>')
        partes.append('<table class="laudo-funcao"><thead><tr><th scope="col">Gated</th><th scope="col">FE</th><th scope="col">VDF</th>'
                      '<th scope="col">VSF</th><th scope="col">Volume sistólico</th><th scope="col">Diástole / sístole final (intervalo)</th>'
                      f'<th scope="col">SMS</th><th scope="col">STS</th></tr></thead><tbody>{linhas}</tbody></table>')
    tid = fun.get("tid")
    if tid:
        partes.append(f'<p class="laudo-tid"><strong>TID:</strong> {fmt_dec(tid["tid"], 2)} (cavidade de {fmt_dec(tid["estresse_ml"], 0)} mL no estresse '
                      f'e {fmt_dec(tid["repouso_ml"], 0)} mL no repouso, imagens não sincronizadas).</p>')
    if est:
        cab = "".join(f'<th scope="col">Motilidade {escape(d["rotulo"].lower())}</th><th scope="col">Espessamento {escape(d["rotulo"].lower())}</th>' for d in est.values())
        corpo = ""
        for s in SEGMENTOS:
            cel = ""
            for d in est.values():
                seg = d["segmentos"][str(s)]
                em = d["mapas"]["motilidade"]["escores"].get(str(s))
                ee = d["mapas"]["espessamento"]["escores"].get(str(s))
                cel += (f'<td>{fmt_dec(seg["motilidade_mm"], 1)} mm · escore {escape(_txt(em))}</td>'
                        f'<td>{fmt_dec(seg["espessamento"], 0)}% · escore {escape(_txt(ee))}</td>')
            corpo += f'<tr><th scope="row">{s}. {escape(NOMES[s])}</th>{cel}</tr>'
        partes.append(f'<div class="laudo-tabela"><table class="laudo-funcao-seg"><thead><tr><th scope="col">Segmento</th>{cab}</tr></thead><tbody>{corpo}</tbody></table></div>')
    return "".join(partes)


def funcao_texto(fun: dict | None) -> str:
    linhas = linhas_funcao(fun)
    if not linhas:
        return ""
    return "\n" + "\n".join("\t".join(str(c) for c in ln) for ln in linhas) + "\n"


def _funcao_html(fun: dict | None, imagens: dict | None) -> str:
    if not fun:
        return ""
    est = fun.get("estudos") or {}
    curvas = "".join(f'<figure class="laudo-curva-fig">{_curva_svg([v for v in d["volumes_ml"]], d["ed"] - 1, d["es"] - 1)}'
                     f'<figcaption>Curva de volume, {escape(d["rotulo"].lower())}</figcaption></figure>' for d in est.values())
    figs = ""
    if imagens:
        malhas = "".join(f'<figure class="laudo-malha">{_img(png, f"Malha do VE, {rot}", "laudo-malha-img", 220)}<figcaption>{escape(rot)}</figcaption></figure>'
                         for rot, png in imagens.get("malhas", []))
        pol = "".join(f'<figure class="laudo-polar">{_img(png, f"Mapa polar de {rot}", "laudo-polar-img", 200)}<figcaption>{escape(rot)}</figcaption></figure>'
                      for rot, png in imagens.get("polares", []))
        cont = "".join(f'<figure class="laudo-contorno">{_img(png, f"Contornos, {rot}", "laudo-contorno-img")}<figcaption>{escape(rot)}</figcaption></figure>'
                       for rot, png in imagens.get("contornos", []))
        figs = ((f'<div class="laudo-contornos">{cont}<p class="laudo-legenda">Eixo curto apical, médio e basal, eixo longo vertical e '
                 "horizontal; endocárdio em azul e epicárdio em verde.</p></div>") if cont else "") \
            + (f'<div class="laudo-polares">{malhas}</div>' if malhas else "") + (f'<div class="laudo-polares">{pol}</div>' if pol else "")
    sc = f'<p class="laudo-nota">Superfície corporal: {fmt_dec(fun["superficie_corporal"], 2)} m² (Mosteller), com peso e altura digitados.</p>' if fun.get("superficie_corporal") else ""
    return (f'<section><h3>Função ventricular (gated)</h3>{funcao_tabelas_html(fun)}{sc}'
            f'<div class="laudo-polares">{curvas}</div>{figs}'
            '<p class="laudo-nota">Mapas de função: motilidade de 0 a 10 mm e espessamento de 0 a 100% (valores fora da escala aparecem '
            "no limite); números = escores visuais (– = não pontuado). Sem banco de normalidade.</p></section>")


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
    funcao: dict | None = None,
    imagens_funcao: dict | None = None,
    automatico: dict | None = None,
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
    notas = "".join(f"<li>{escape(n)}</li>" for n in NOTAS_METODO + (NOTAS_FUNCAO if funcao else ()))
    fontes = refs.BIBLIOGRAFIA + (refs.BIBLIOGRAFIA_GATED if funcao else ()) + ((refs.CUBERAS_2010,) if automatico else ())
    bib = "".join(f"<li>{escape(f.citacao)}{escape(f' doi:{f.doi}') if f.doi else ''}</li>" for f in fontes)
    fe = ""
    for d in ((funcao or {}).get("estudos") or {}).values():
        fe += f"<div><dt>FE {escape(d['rotulo'].lower())}</dt><dd>{fmt_dec(d['fe'], 0)}%</dd></div>"
    if (funcao or {}).get("tid"):
        fe += f"<div><dt>TID</dt><dd>{fmt_dec(funcao['tid']['tid'], 2)}</dd></div>"
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
{fe}
<div><dt>Processado em</dt><dd>{gerado_em.strftime('%d/%m/%Y %H:%M')}</dd></div>
<div><dt>Núcleo</dt><dd>mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))}</dd></div>
</dl>
</header>
{alertas}
{_figuras_html(imagens)}
<section><h3>Escores (pontuação visual)</h3>{_tabela_resumo_html(r)}{_tabela_territorios_html(r)}
<div class="laudo-tabela">{_tabela_segmentos_html(r, valores)}</div>
<p class="laudo-nota">Escala: {escape(escala)}. Os escores são os marcados pelo médico; a captação (% do máximo do VE) vem do mapa polar e não tem banco de normalidade.</p></section>
{automatico_html(automatico, (imagens or {}).get("automatico"))}
{_funcao_html(funcao, imagens_funcao)}
{_gated_html(arquivos_info)}
<section><h3>Método</h3>
<p><strong>Reconstrução:</strong> retroprojeção filtrada. {escape(descrever_filtro(filtro, pixel_mm))} As duas convenções do corte (fração de Nyquist e ciclos/pixel) aparecem lado a lado porque cada fabricante usa uma (Germano, 2001). O padrão inicial da ferramenta (ordem 11, corte 0,45 Nyquist) é o melhor resultado num fantoma de VE com ⁹⁹ᵐTc citado por Lyra e Ploussi (2011).</p>
<p><strong>Reorientação:</strong> eixo longo do VE traçado à mão num corte transaxial e depois no plano vertical que contém essa linha (Germano, 2001). Cortes exibidos no padrão de Cerqueira et al. (2002): eixo curto do ápice para a base, com anterior em cima e septo à esquerda; eixo longo vertical com o ápice à direita; eixo longo horizontal com o ápice em cima.</p>
<p><strong>Mapa polar e segmentos:</strong> 17 segmentos e territórios coronarianos de Cerqueira et al. (2002), como na ASNC (2017) e na SBC (2020). <strong>Desvio declarado:</strong> a amostragem do miocárdio desta versão é própria (perfil de contagem máxima ao longo de raios a partir do eixo, com um centro apical a 30% do comprimento do eixo, limitado entre 10 e 40 mm), e não a do QPS (Germano et al., 2000), que depende da detecção automática das bordas do VE.</p>
{'<p><strong>Gated:</strong> cada intervalo reconstruído com o mesmo filtro. Bordas, volumes, motilidade e espessamento pelo método publicado do QGS (Germano et al., 1995; motilidade e espessamento como em Germano et al., 1997), implementado a partir do artigo (ver as fórmulas abaixo). Não é o programa comercial: a reconstrução, o filtro e os detalhes não publicados mudam os números, que não são intercambiáveis com os do QGS.</p>' if funcao else ''}
</section>
<section><h3>Fórmulas e critérios</h3><ul>{notas}</ul></section>
<section><h3>Arquivos</h3><ul class="laudo-arquivos">{arquivos}</ul></section>
<section class="laudo-refs"><h3>Referências</h3><ol>{bib}</ol></section>
<footer class="laudo-rodape">
<p class="laudo-versoes">mnp-nucleo {escape(str(v.get('mnp_nucleo', '?')))} · pydicom {escape(str(v.get('pydicom', '?')))} · NumPy {escape(str(v.get('numpy', '?')))} · Python {escape(str(v.get('python', '?')))}{pyodide}</p>
<p class="laudo-aviso">{escape(AVISO)}</p>
</footer>
</article>"""
