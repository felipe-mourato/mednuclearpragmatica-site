# Histórico de versões do mnp-nucleo

O formato segue [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem [versionamento semântico](https://semver.org/lang/pt-BR/). Toda entrada diz se algum número calculado muda em relação à versão anterior.

## [0.2.0] - 2026-10-09

Muda números em relação à 0.1.0: proximal, distal e as retenções regionais. A retenção total não muda.

### Alterado

- **Divisão proximal/distal pelo eixo longitudinal** (Silver et al., Neurogastroenterol Motil 2022, que segue Orthey et al., J Nucl Med 2018). O usuário traça o eixo pela linha média do estômago, do topo do fundo até o estômago distal; o comprimento é dividido ao meio e o corte perpendicular nesse ponto separa as metades. Cada pixel da ROI vai para a metade do ponto do eixo mais próximo dele (no artigo, a ROI proximal é desenhada à mão a partir do corte). Substitui a divisão por componentes principais em metades de mesma área da 0.1.0.
- **Contagem distal = total − proximal**, em média geométrica, como no artigo. Proximal + distal = total em todas as linhas.
- O eixo é espelhado na posterior, como a ROI, e acompanha a ROI quando ela é arrastada. O primeiro eixo traçado vale para todos os tempos.
- Protocolo de reprodução no formato 2 (com o eixo). Protocolos da 0.1.0 são recusados com mensagem clara.

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
