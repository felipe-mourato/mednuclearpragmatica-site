"""Exportação de tabelas (CSV e XLSX) e formatação de números em pt-BR.

O XLSX é escrito com a biblioteca padrão (zipfile + XML), sem dependências,
para funcionar igual no navegador e no computador.
"""

from __future__ import annotations

import io
import math
import zipfile
from typing import Sequence
from xml.sax.saxutils import escape

__all__ = ["fmt_int", "fmt_dec", "gerar_csv", "gerar_xlsx"]

Celula = str | int | float | None


def fmt_int(v: float) -> str:
    """Inteiro arredondado com separador de milhar pt-BR: 12345,6 → "12.346"."""
    if v is None or not math.isfinite(v):
        return "—"
    return f"{round(v):,}".replace(",", ".")


def fmt_dec(v: float, casas: int = 1) -> str:
    """Decimal com vírgula e milhar com ponto: 1234,56 → "1.234,6"."""
    if v is None or not math.isfinite(v):
        return "—"
    texto = f"{v:,.{casas}f}"
    return texto.replace(",", "§").replace(".", ",").replace("§", ".")


def _csv_celula(v: Celula) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sim" if v else "não"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v).replace(".", ",") if math.isfinite(v) else ""
    texto = str(v)
    if any(c in texto for c in ';"\n\r'):
        texto = '"' + texto.replace('"', '""') + '"'
    return texto


def gerar_csv(cabecalho: Sequence[str], linhas: Sequence[Sequence[Celula]]) -> bytes:
    """CSV para Excel em português: separador ";", decimal ",", UTF-8 com BOM."""
    saida = [";".join(_csv_celula(c) for c in cabecalho)]
    saida += [";".join(_csv_celula(c) for c in linha) for linha in linhas]
    return ("﻿" + "\r\n".join(saida) + "\r\n").encode("utf-8")


def _coluna(n: int) -> str:
    letras = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        letras = chr(65 + r) + letras
    return letras


def _xlsx_celula(ref: str, v: Celula, negrito: bool) -> str:
    estilo = ' s="1"' if negrito else ""
    if v is None or v == "":
        return ""
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return f'<c r="{ref}"{estilo}><v>{v!r}</v></c>'
    return f'<c r="{ref}" t="inlineStr"{estilo}><is><t xml:space="preserve">{escape(str(v))}</t></is></c>'


def gerar_xlsx(
    linhas: Sequence[Sequence[Celula]],
    nome_planilha: str = "Planilha1",
    linhas_negrito: Sequence[int] = (),
    largura_colunas: float = 18,
) -> bytes:
    """Arquivo .xlsx de uma planilha com os valores dados (linha a linha).

    Números são gravados como números (o Excel formata conforme o idioma do
    usuário); textos como texto. ``linhas_negrito``: índices (0-based) das
    linhas em negrito, como títulos e cabeçalhos.
    """
    negrito = set(linhas_negrito)
    n_colunas = max((len(l) for l in linhas), default=1)
    xml_linhas = []
    for i, linha in enumerate(linhas):
        celulas = "".join(
            _xlsx_celula(f"{_coluna(j)}{i + 1}", v, i in negrito) for j, v in enumerate(linha)
        )
        xml_linhas.append(f'<row r="{i + 1}">{celulas}</row>')
    cols = f'<cols><col min="1" max="{n_colunas}" width="{largura_colunas}" customWidth="1"/></cols>'
    planilha = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f'{cols}<sheetData>{"".join(xml_linhas)}</sheetData></worksheet>'
    )
    nome = escape(nome_planilha[:31])
    arquivos = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            "</Types>"
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            "</Relationships>"
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            f'<sheets><sheet name="{nome}" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            "</Relationships>"
        ),
        "xl/styles.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
            '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
            '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
            '<borders count="1"><border/></borders>'
            '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            '<cellXfs count="2"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
            '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
            '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>'
            "</styleSheet>"
        ),
        "xl/worksheets/sheet1.xml": planilha,
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as z:
        for caminho, conteudo in arquivos.items():
            info = zipfile.ZipInfo(caminho, date_time=(2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, conteudo)
    return buffer.getvalue()
