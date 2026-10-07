#!/usr/bin/env bash
# =====================================================================
# Build do site MedNuclear Pragmática para o Cloudflare Pages.
#
# No Cloudflare Pages:
#   Comando de build:      bash build.sh
#   Diretório de saída:    _site
#
# O script baixa uma versão fixa do Quarto para Linux, confere a
# assinatura (SHA-256) do arquivo, renderiza o site e deixa tudo em _site.
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

# Conferências mínimas antes de publicar
for f in _site/index.html _site/sitemap.xml _site/404.html _site/robots.txt; do
  if [ ! -s "$f" ]; then
    echo "ERRO: ${f} não foi gerado." >&2
    exit 1
  fi
done

echo ">> Pronto: site gerado em _site/"
