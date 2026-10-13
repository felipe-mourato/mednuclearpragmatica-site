# Histórico de versões do mnp-nucleo

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem [versionamento semântico](https://semver.org/lang/pt-BR/). Toda entrada diz se algum número calculado muda em relação à versão anterior.

## [0.3.0] - 2026-10-13

Nenhum número da ferramenta de esvaziamento gástrico muda: o subpacote `gastrico` não foi alterado e os testes dele passam como antes.

### Incluído

- **Cintilografia renal com ⁹⁹ᵐTc-DMSA** (`mnp_nucleo.dmsa`, ferramenta em `/ferramentas/dmsa/`).
  - Incidências POSTERIOR (obrigatória), ANTERIOR e oblíquas (OPD, OPE, OAD, OAE; só exibição), sugeridas pela descrição da série (siglas em português e em inglês) e corrigíveis. Arquivo multiframe vira um item por quadro, com quadro 1 posterior e quadro 2 anterior como sugestão; quadros seguintes ficam de fora até o usuário escolher.
  - ROIs dos dois rins desenhadas à mão na posterior; na anterior, espelhadas (x' = largura − x, a mesma convenção do gástrico) e deslocáveis à parte. Com dimensões diferentes entre posterior e anterior, o espelhamento é feito em escala, com aviso.
  - Fundo: anel perirrenal circunferencial de 4 pixels em volta de cada rim inteiro, sem invadir a ROI do outro rim, calculado automaticamente. A forma segue Civan et al. (Phys Med 2022;95:83-8, doi:10.1016/j.ejmp.2022.01.010), em que só o fundo em volta do rim inteiro não diferiu do SPECT; a largura de 4 pixels é escolha da ferramenta (a fonte consultada não informa a largura) e está declarada na tela e no laudo. Correção à mão por rim e por vista, com volta ao anel. Opção "sem correção" para comparação.
  - Função relativa pela posterior e pela média geométrica, área relativa e função corrigida pelo tamanho (contagem por pixel, Estorch et al., Nucl Med Commun 2004;25:167-70, doi:10.1097/00006231-200402000-00013), todas somando 100%. Comparação dentro ou fora de 45–55% só para a função relativa (Vali et al., Clin Transl Imaging 2022;10:173-84, doi:10.1007/s40336-022-00484-x; diretriz pediátrica, aplicada a qualquer idade com nota no laudo).
  - Saídas: tabelas, CSV, Excel, figuras PNG com as ROIs e o fundo (cinza normal ou invertida), laudo HTML com imagens para imprimir ou colar no Word, protocolo de reprodução (com cada região de fundo gravada como máscara) e lote no computador (`mnp-dmsa` ou `python -m mnp_nucleo.dmsa`).
  - O laudo não lê dados do paciente no DICOM: nome e data do exame são digitados pelo usuário.
  - Fantoma `fantoma_dmsa()` com resposta exata (rins de 44% e 56% da área com a mesma captação por pixel: função relativa 44,0%, corrigida pelo tamanho 50,0%).
- `comum.morfologia` (dilatação por disco, contorno, máscara em trechos) e `comum.png` (codificador PNG com a biblioteca padrão).

### Desvios declarados em relação às fontes

- A largura do anel de fundo (4 pixels) não vem de artigo.
- A correção pelo tamanho usa a área da ROI na imagem planar, não o volume renal; o laudo explica que a área cresce menos que o volume. O método exato de medida de tamanho de Estorch et al. não foi conferido no texto completo.

## [0.2.0] - 2026-10-09

Muda números em relação à 0.1.0: proximal, distal e as retenções regionais. A retenção total não muda.

### Alterado

- **Divisão proximal/distal pelo eixo longitudinal** (Silver et al., Neurogastroenterol Motil 2022, que segue Orthey et al., J Nucl Med 2018). O comprimento do eixo é dividido ao meio e o corte perpendicular nesse ponto separa as metades. Cada pixel da ROI vai para a metade do ponto do eixo mais próximo dele (no artigo, a ROI proximal é desenhada à mão a partir do corte). Substitui a divisão por componentes principais em metades de mesma área da 0.1.0.
- **Eixo longitudinal automático** (no artigo, é traçado à mão): linha média geodésica da ROI. As extremidades são os dois pixels da ROI mais distantes entre si por dentro dela (topo do fundo e extremidade distal); o caminho entre elas tem custo por passo proporcional a 1/d², em que d é a distância à borda da ROI, e por isso segue o meio do estômago; as pontas que desviam para os cantos são aparadas e prolongadas em linha reta até a borda. Depende só do contorno da ROI, sem limiar de contagem. O usuário pode corrigir o eixo à mão em qualquer tempo e voltar ao automático.
- **Contagem distal = total − proximal**, em média geométrica, como no artigo. Proximal + distal = total em todas as linhas.
- O eixo é espelhado na posterior, como a ROI, e acompanha a ROI quando ela é arrastada. Redesenhar a ROI de um tempo descarta a correção manual do eixo daquele tempo.
- Protocolo de reprodução no formato 2, com o eixo usado em cada tempo e a origem (automático ou manual); o lote usa exatamente esse eixo, mesmo que o algoritmo automático mude em versões futuras. Protocolos da 0.1.0 são recusados com mensagem clara.

### Incluído

- Razão proximal/distal (PDCR), marcada como não avaliável com retenção abaixo de 5% (Silver 2022), e medianas do artigo no laudo, para contexto.
- Faixa etária nos resultados: adulto (Tougas 2000, percentil 95) ou pediátrico (MacLean e El-Chammas, J Nucl Med Technol 2024, Tabela 2, com refeição de clara de ovo/Ensure Plus ou aveia). Coluna de referência na tabela, no CSV, no Excel e no laudo; a comparação usa o tempo de referência mais próximo, até 15 min.
- Comprimento do eixo em cm quando o DICOM traz PixelSpacing (0028,0030).

## [0.1.0] - 2026-10-09

Primeira versão. Porta para Python a lógica do app de referência "Esvaziamento Gástrico — Cintilografia" (React/TypeScript).

### Incluído

- Leitura de DICOM não comprimido com pydicom: 8, 16 e 32 bits, com e sem sinal, rescale (inclinação e intercepto), multiframe, horário com alternativas (AcquisitionTime, ContentTime, SeriesTime, StudyTime) combinado com a data. Mensagens claras para arquivo comprimido, colorido, sem pixels ou não DICOM.
- Geometria de ROI: máscara por ponto no polígono, espelhamento para a posterior, translação limitada à imagem, simplificação do traço.
- Esvaziamento gástrico: média geométrica, correção de decaimento, retenção, esvaziamento, divisão proximal/distal por componentes principais, distribuição proximal e retenções regionais.
- Sessão por comandos JSON (usada pela ferramenta web), protocolo de reprodução e processamento em lote (`mnp-gastrico`).
- Exportação CSV e XLSX, curva em SVG e laudo HTML com as versões do software.
- Fantomas sintéticos com contagens conhecidas.

### Diferenças em relação ao app de referência

- **Espelhamento da ROI posterior:** passa a ser x' = largura − x (antes, largura − 1 − x). Com coordenadas contínuas e pixel testado pelo centro, a fórmula antiga deslocava a ROI posterior 1 pixel para a esquerda. Muda levemente as contagens posteriores.
- Pixels em precisão dupla (float64); o app de referência usava float32.
- Sobreposição proximal/distal misturada ao cinza (antes, a cor substituía o pixel na tela). Só exibição.
