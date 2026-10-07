"""
Gera as imagens de compartilhamento (CartaoLink, 1200 x 627) do site.
Opcional: só é preciso rodar para criar um cartão novo. Requer Python com
Playwright (pip install playwright && playwright install chromium) e as
fontes da marca instaladas no computador.

Uso, a partir da pasta do projeto:
  python _estrutura/cartoes/gerar_cartoes.py

Para um cartão de post, acrescente uma linha na lista CARTOES abaixo.
"""
import pathlib
from playwright.sync_api import sync_playwright

RAIZ = pathlib.Path(__file__).resolve().parents[2]
LOGOS = RAIZ / "assets" / "logos"

# (arquivo de saída, versão escura?, sobretítulo, título)
CARTOES = [
    ("assets/og/cartao-padrao.png", True, "Educação em medicina nuclear",
     "Para quem pede o exame e para quem faz o laudo"),
    ("assets/og/cartao-papers.png", True, "Paper comentado",
     "Leitura crítica de estudos, com o que muda na prática"),
    ("assets/og/cartao-guias.png", False, "Guia do solicitante",
     "Quando pedir, qual traçador e como ler o laudo"),
    ("assets/og/cartao-casos.png", True, "Caso clínico",
     "Imagens de medicina nuclear, uma pergunta e a conclusão"),
    ("assets/og/cartao-fundamentos.png", False, "Fundamentos",
     "Física, radiofarmácia, radioproteção e quantificação"),
]

CSS = (pathlib.Path(__file__).parent / "cartao.css").read_text(encoding="utf-8")


def html(escuro, serie, titulo):
    simbolo = (LOGOS / ("mnp-simbolo-negativo.svg" if escuro else "mnp-simbolo.svg")).as_uri()
    logo = (LOGOS / ("mnp-horizontal-negativo.svg" if escuro else "mnp-horizontal.svg")).as_uri()
    classe = "mnp-card" if escuro else "mnp-card mnp-card--claro"
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8"><style>{CSS}</style></head>
<body><div class="{classe}">
<div class="mnp-card__texto"><span class="mnp-card__serie">{serie}</span>
<h2 class="mnp-card__titulo">{titulo}</h2><span class="mnp-card__autor">por Felipe Mourato</span></div>
<img class="mnp-card__simbolo" src="{simbolo}" alt="">
<div class="mnp-card__base"><img src="{logo}" alt="MedNuclear Pragmática"><span>mednuclearpragmatica.com.br</span></div>
<div class="mnp-termica"><i></i><i></i><i></i><i></i><i></i></div>
</div></body></html>"""


def main():
    with sync_playwright() as p:
        nav = p.chromium.launch()
        pag = nav.new_page(viewport={"width": 1200, "height": 627}, device_scale_factor=1)
        for saida, escuro, serie, titulo in CARTOES:
            arq = RAIZ / "_estrutura" / "cartoes" / "_temp.html"
            arq.write_text(html(escuro, serie, titulo), encoding="utf-8")
            pag.goto(arq.as_uri(), wait_until="networkidle")
            pag.evaluate("document.fonts.ready")
            destino = RAIZ / saida
            destino.parent.mkdir(parents=True, exist_ok=True)
            pag.screenshot(path=str(destino), clip={"x": 0, "y": 0, "width": 1200, "height": 627})
            arq.unlink()
            print("ok", saida)
        nav.close()


if __name__ == "__main__":
    main()
