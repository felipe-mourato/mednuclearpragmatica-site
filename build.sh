#!/usr/bin/env bash
# =====================================================================
# Build do site MedNuclear Pragmática para o Cloudflare Pages.
#
# No Cloudflare Pages:
#   Comando de build:      bash build.sh
#   Diretório de saída:    _site
#
# O script baixa uma versão fixa do Quarto para Linux, confere a
# assinatura (SHA-256) do arquivo, renderiza o site, testa e empacota o
# núcleo Python das ferramentas e deixa tudo em _site.
# Não usa GitHub Actions nem chaves secretas.
#
# Para atualizar o Quarto: troque QUARTO_VERSION por outra versão estável
# (veja https://quarto.org/docs/download/) e teste com `bash build.sh`.
# =====================================================================
set -euo pipefail

QUARTO_VERSION="1.10.18"

cd "$(dirname "$0")"

ARQUIVO="quarto-${QUARTO_VERSION}-linux-amd64.tar.gz"
BASE_URL="https://github.com/quarto-dev/quarto-cli/releases/download/v${QUARTO_VERSION}"
PASTA=".quarto-bin/quarto-${QUARTO_VERSION}"
QUARTO="${PASTA}/bin/quarto"

if [ ! -x "${QUARTO}" ]; then
  echo ">> Baixando Quarto ${QUARTO_VERSION}"
  mkdir -p .quarto-bin
  curl -fsSL --retry 3 -o ".quarto-bin/${ARQUIVO}" "${BASE_URL}/${ARQUIVO}"
  curl -fsSL --retry 3 -o ".quarto-bin/checksums.txt" "${BASE_URL}/quarto-${QUARTO_VERSION}-checksums.txt"

  echo ">> Conferindo SHA-256"
  ESPERADO="$(grep " ${ARQUIVO}\$" .quarto-bin/checksums.txt | awk '{print $1}')"
  if [ -z "${ESPERADO}" ]; then
    echo "ERRO: checksum de ${ARQUIVO} não encontrado." >&2
    exit 1
  fi
  OBTIDO="$(sha256sum ".quarto-bin/${ARQUIVO}" | awk '{print $1}')"
  if [ "${ESPERADO}" != "${OBTIDO}" ]; then
    echo "ERRO: checksum não confere (esperado ${ESPERADO}, obtido ${OBTIDO})." >&2
    exit 1
  fi

  mkdir -p "${PASTA}"
  tar -xzf ".quarto-bin/${ARQUIVO}" -C "${PASTA}" --strip-components=1
  rm -f ".quarto-bin/${ARQUIVO}"
fi

"${QUARTO}" --version

echo ">> Renderizando o site"
rm -rf _site
"${QUARTO}" render

# Rascunhos (draft: true) viram arquivos HTML vazios. Apagamos a página e,
# quando ela é o index.html de uma pasta de post, a pasta inteira (imagens,
# cartão de compartilhamento), para nada de um rascunho ir para o ar.
find _site -name '*.html' -size -200c | while read -r f; do
  echo ">> rascunho omitido: ${f#_site/}"
  pasta="$(dirname "$f")"
  if [ "$(basename "$f")" = "index.html" ] && [ "$pasta" != "_site" ] \
     && [ -z "$(find "$pasta" -name '*.html' ! -path "$f" -print -quit)" ]; then
    rm -rf "$pasta"
  else
    rm -f "$f"
  fi
done

# ---------------------------------------------------------------------
# Ferramentas (ferramentas/<exame>/) e o núcleo Python (nucleo/)
#
# 1. Testa o núcleo (pytest). Se algum teste falhar, o site NÃO é
#    publicado. Para pular numa emergência: variável de ambiente
#    PULAR_TESTES_NUCLEO=1 no Cloudflare (não recomendado).
# 2. Gera a wheel do núcleo e baixa o pydicom com hash conferido, em
#    _site/ferramentas/_pacotes/ (mesma origem das ferramentas).
# 3. Copia cada pasta ferramentas/<exame>/ que tenha index.html.
# Exige python3 (já vem na imagem de build do Cloudflare Pages).
# ---------------------------------------------------------------------
if ! command -v python3 >/dev/null 2>&1; then
  echo "ERRO: python3 não encontrado; é necessário para o núcleo das ferramentas." >&2
  exit 1
fi
VENV=".nucleo-venv"
echo ">> Preparando Python para o núcleo ($(python3 --version))"
rm -rf "${VENV}"
python3 -m venv "${VENV}"
PY="${VENV}/bin/python"
"${PY}" -m pip install --quiet --disable-pip-version-check --upgrade pip

if [ "${PULAR_TESTES_NUCLEO:-0}" = "1" ]; then
  echo ">> ATENÇÃO: testes do núcleo pulados (PULAR_TESTES_NUCLEO=1)"
else
  echo ">> Testando o núcleo"
  # NumPy da mesma série do Pyodide quando possível; senão, o mais recente.
  "${PY}" -m pip install --quiet --disable-pip-version-check "numpy==2.2.5" \
    || "${PY}" -m pip install --quiet --disable-pip-version-check "numpy>=1.26"
  "${PY}" -m pip install --quiet --disable-pip-version-check -r nucleo/requisitos-teste.txt
  "${PY}" -m pip install --quiet --disable-pip-version-check --no-deps ./nucleo
  (cd nucleo && "../${PY}" -m pytest -q -p no:cacheprovider)
fi

echo ">> Empacotando o núcleo para as ferramentas"
"${PY}" _estrutura/empacotar_nucleo.py --python "${PY}" --saida _site/ferramentas/_pacotes

for pasta in ferramentas/*/; do
  nome="$(basename "${pasta}")"
  if [ -f "${pasta}index.html" ]; then
    echo ">> Ferramenta: ${nome}"
    rm -rf "_site/ferramentas/${nome}"
    cp -R "${pasta}" "_site/ferramentas/${nome}"
  fi
done
rm -rf "${VENV}"

# Conferências mínimas antes de publicar
for f in _site/index.html _site/sitemap.xml _site/404.html _site/robots.txt \
         _site/ferramentas/_pacotes/pacotes.json _site/ferramentas/esvaziamento-gastrico/index.html; do
  if [ ! -s "$f" ]; then
    echo "ERRO: ${f} não foi gerado." >&2
    exit 1
  fi
done

echo ">> Pronto: site gerado em _site/"
