# mnp-nucleo

Núcleo de processamento das ferramentas de medicina nuclear da [MedNuclear Pragmática](https://mednuclearpragmatica.com.br/ferramentas/). É um pacote Python (pydicom + NumPy) sem nenhuma dependência da interface: o mesmo código roda no navegador, dentro da ferramenta web (via Pyodide), e no computador, em lote, para estudos de validação.

> Ferramenta de pesquisa e ensino, ainda não validada para uso clínico. Auxílio ao cálculo; a interpretação é de responsabilidade do médico nuclear.

## O que tem aqui

| Módulo | Conteúdo |
| --- | --- |
| `mnp_nucleo.comum.dicom` | Leitura de DICOM não comprimido, rescale, multiframe, horário com alternativas |
| `mnp_nucleo.comum.roi` | Polígonos: máscara, espelhamento, translação, área |
| `mnp_nucleo.comum.contagens` | Soma em ROI, média geométrica, correção de decaimento |
| `mnp_nucleo.comum.exibicao` | Janela e inversão de cinza (só exibição) |
| `mnp_nucleo.comum.tabela` | CSV e XLSX sem dependências |
| `mnp_nucleo.gastrico` | Esvaziamento gástrico: segmentação proximal/distal, cálculos, sessão, laudo, lote |
| `mnp_nucleo.fantomas` | DICOMs sintéticos com contagens conhecidas |

Cada função de cálculo traz na docstring a fórmula e a referência.

## Instalar e testar (no computador)

Com Python 3.10 ou mais novo, dentro da pasta `nucleo/`:

```
python3 -m pip install -e ".[teste]"
python3 -m pytest
```

## Processar em lote

Na ferramenta web, depois de desenhar as ROIs, baixe o **protocolo** (arquivo `.json`): ele guarda os nomes e o SHA-256 dos DICOMs, os quadros, os minutos e as ROIs, sem pixels. No computador:

```
mnp-gastrico protocolo.json --pasta pasta-dos-dicoms/ --csv resultado.csv --laudo laudo.html
mnp-gastrico protocolos/*.json --pasta pasta-dos-dicoms/ --csv todos.csv
```

O resultado é o mesmo do navegador, porque o código é o mesmo. Os nomes de arquivo podem conter dados do paciente: renomeie antes de compartilhar um protocolo.

## Fantoma de conferência

```python
from mnp_nucleo.fantomas import fantoma_esvaziamento
f = fantoma_esvaziamento()
for nome, dados in f.arquivos.items():
    open(nome, "wb").write(dados)
print(f.retencao, f.distribuicao)  # valores que a ferramenta deve devolver
```

## Lançar uma versão

1. Mude `__version__` em `src/mnp_nucleo/__init__.py`. Correção que não muda nenhum número: 0.1.1. Novidade ou qualquer mudança que altere números já calculados: 0.2.0. Depois do artigo de validação, a versão validada vira 1.0.0.
2. Registre a mudança em `CHANGELOG.md`, dizendo se algum número calculado muda.
3. Atualize `version` e `date-released` em `CITATION.cff` (na raiz do repositório) e o campo `versao` do cartão em `ferramentas/ferramentas.yml`.
4. Rode os testes (`python3 -m pytest`).
5. Envie para o GitHub e crie uma *release* com a etiqueta `nucleo-v0.1.0` (o número novo). Com a integração GitHub–Zenodo ativada, cada *release* recebe um DOI próprio. O passo a passo da integração está no README da raiz, seção 12.

A versão do núcleo aparece nos resultados e no laudo de cada exame processado, e o build do site publica a wheel com o número no nome.
