# Dossiê do prompt de imagem — o que tem de estar, e por quê

Este documento existe para que o Claude consiga **julgar** um prompt do MS
Studio, e não apenas descrevê-lo. Julgar exige saber o que cada pedaço deveria
conter, de onde ele vem, e qual prejuízo nasceu quando ele faltou.

---

## LEIA ISTO PRIMEIRO — o que você pode afirmar

Este dossiê é lido em dois lugares muito diferentes. **Descubra em qual você
está antes de continuar.**

### Se você está numa CONVERSA, e este documento foi anexado

Você **não** tem o código. Você tem: este dossiê e os prompts que o dono
colar ou anexar. Então:

**O que você PODE afirmar, lendo só o prompt:**

- que dois números se contradizem — duas faixas de ocupação, dois tetos de
  blocos, duas contagens de texto;
- que uma ordem e a contraordem estão na mesma mensagem — "escolha a paleta"
  ao lado de uma paleta já decidida; "nenhum texto" ao lado de "escreva X";
  "NEVER add people" numa peça que pede duas pessoas;
- que um bloco obrigatório da seção 2 deste dossiê **não está** no prompt;
- que um trecho proibido **está** — cor de marca fixa, lista pronta de
  cômodos, `{faixa}` e outros buracos de molde vazados;
- que o `IMAGE TYPE:` não bate com o conteúdo da peça;
- que as oito peças do mesmo produto repetem cenário, props ou ângulo.

Tudo isso se vê **no texto do prompt**, e é a maior parte dos defeitos.

**O que você NÃO pode afirmar, e não deve fingir:**

- que rodou qualquer comando. Você não rodou. Os comandos citados aqui são
  para quem tem o repositório;
- que conferiu um `arquivo:linha`. As referências existem para o dono saber
  onde mandar corrigir — você não as leu;
- que a imagem vai sair certa. O prompt certo não garante a imagem certa;
- que uma paleta é "boa" para o produto sem ver a foto dele. Se a foto não
  foi anexada, diga que depende dela.

**Quando faltar informação, declare a dúvida.** Palpite que acerta não
economiza nada; palpite que erra custa um deploy.

**Como entregar o achado.** Um por linha, nesta forma — é o que permite
corrigir sem ida e volta:

```
SEÇÃO / peça   →   o que está escrito   →   por que é defeito   →   o que deveria estar
```

### Se você está numa sessão com o REPOSITÓRIO

Vale tudo o que está acima, mais os comandos das seções 6.1 e 6.5, e mais uma
regra: **nada neste arquivo substitui o código.** Toda afirmação traz o
`arquivo:linha` que a sustenta. Se o código e este documento discordarem, **o
código está certo e este documento está velho** — corrija o documento, e
acrescente a regra em `checar_prompts.py` para que a discordância nunca mais
passe calada.

---

## 1. Como ler um prompt sem se enganar

Existem **dois** textos, e confundi-los custou semanas nesta base.

| | O que é | Onde nasce |
|---|---|---|
| **Brief em português** | O texto que o Studio monta a partir do tipo, do plano e dos dados | `imagem.py:3232` `montar_prompt_imagem()` |
| **Prompt enviado** | O texto em inglês que o motor de imagem realmente recebe | `imagem.py:2104` `gerar_imagem_ia()`, montado perto do fim |

**O que importa é o segundo.** Durante semanas a varredura conferia o primeiro
e dava "ok" em regras que o motor nunca recebeu — porque um recorte por regex
descartava dois terços do brief em silêncio. Se você for conferir alguma coisa,
confira o **ENVIADO**.

Para obtê-lo sem gerar imagem:

```python
import imagem
pt = imagem.montar_prompt_imagem(tipo, instrucoes, dados, nome, ...)
en = imagem.prompt_que_sera_enviado(pt, fotos_bytes, tipo=tipo)   # imagem.py:3547
```

`prompt_que_sera_enviado` chama `gerar_imagem_ia(..., so_montar=True)`, que
para **antes** de chamar qualquer motor. Não há segunda montagem, de propósito:
montar o mesmo prompt em dois lugares garante que um dia os dois discordem.

Na tela, o mesmo texto aparece no **Plano de criação** → botão
*"Ver o prompt que será enviado em cada peça"*.

---

## 2. A anatomia do prompt enviado

Na ordem em que o motor lê:

```
Create a professional e-commerce marketing image.
IMAGE TYPE: <tipo oficial>

━━━ SECTION 1: THE COMPLETE BRIEF FOR THIS PIECE (Brazilian Portuguese) ━━━
━━━ SECTION 2: PRODUCT REFERENCE ━━━
━━━ SECTION 3: USER / COLLABORATOR BRIEF ━━━
━━━ VISUAL STYLE ━━━
TEXT RULE:
COMPOSITION:
━━━ PRODUCT INTEGRITY RULES ━━━
ADDITIONAL RULES:
━━━ THE TIE-BREAKER ━━━
IMAGENS ENVIADAS — o que é cada uma:   (só quando há referência de layout)
```

### SECTION 1 — o brief inteiro, em português

É o brief inteiro, sem corte, menos as linhas de controle `MS_`.

**TEM de conter**, em qualquer tipo:

| Bloco | Origem | Por que existe |
|---|---|---|
| `PRODUTO:` com o nome comercial | `montar_prompt_imagem` | Sem ele o modelo nomeia o objeto sozinho — foi assim que uma caneca virou "aquecedor vermelho" |
| `COR REAL DO PRODUTO:` + `TRAVA DE COR` | `_trava_cor_produto` | Um álbum preto saiu azul-marinho |
| `Medidas EXATAS` e `Peso EXATO`, quando informados | `montar_prompt_imagem` | O tipo 5 pede "use APENAS os valores informados" — sem os valores na mensagem, ele inventa |
| `TIPO DE IMAGEM:` + o preset do tipo | `PRESETS` `imagem.py:525` | Sem o preset a peça sai com as regras genéricas |
| `REGRA DE FIDELIDADE` | `imagem.py:360` | "A mais importante de todas" |
| Bloco de protagonismo com a ocupação | `imagem.py:287/346/315` | "o maior possível" é opinião; ocupação medida é instrução |
| `MS_FUNDO:` — **NÃO**, esta linha é removida | `gerar_imagem_ia` | É marcador interno, não instrução |

**Condicional:**

| Bloco | Quando aparece |
|---|---|
| `DIREÇÃO DE ARTE DESTE PRODUTO — JÁ DECIDIDA` + `PALETA-MÃE` | Quando o plano traz `direcao_de_arte` |
| `━━━ TEXTO EXATO A ESCREVER` | Quando o plano traz `textos` |
| `Cena desta peça:` | Quando o plano traz `cena` |
| `AMBIENTAÇÃO PEDIDA POR QUEM VENDE` | Quando o colaborador escreveu tema |
| `CONTEXTO INTERNO DO PRODUTO` | Tipos 1–8, quando há instruções extras |
| `INSTRUÇÕES VISUAIS DO COLABORADOR` | Só no Personalizado |
| `REGRA DE LAYOUT PARA IMAGENS DE MARKETING` | Tipos 2–7 |

**NÃO PODE conter, em tipo nenhum:**

- `#1A3A6B`, `#E8EEF5`, "azul marinho", "borda fina azul", "paleta azul da
  empresa", "cores da marca presentes" — a paleta azul fixa já voltou **cinco**
  vezes, em lugares diferentes
- "escritório, quarto, sala de estudo" — lista pronta de cômodos; um marcador
  de taça não pertence a nenhum deles
- `{faixa}`, `{blocos}`, `{direcao}` — são buracos de molde. Se aparecerem
  literalmente, alguém usou a constante direto em vez do helper
- Com direção herdada: a frase "escolha a paleta". Ter a ordem de deduzir ao
  lado da direção pronta é o defeito que a direção de arte existe para fechar

### SECTION 2 — a referência do produto

Duas formas, e a diferença importa:

- **Com fotos e com chave da OpenAI:** `PRODUCT REFERENCE: Use the product
  photos provided as the exact visual reference.` O modelo **vê** as fotos.
- **Sem uma das duas:** `PRODUCT DESCRIPTION (recreate this product
  exactly...)` seguido de uma descrição escrita pelo Claude Vision.

O segundo caminho é onde nasce o produto errado: a descrição é texto, e texto
sobre foto perde detalhe. Ao auditar, verifique se a descrição nomeia o objeto
de forma compatível com `PRODUTO:` da SECTION 1. Divergência ali é defeito.

### SECTION 3 — o brief do colaborador

- Tipos 2–7 com marketing: os textos dele são para **renderizar na imagem**
- Demais: `PRODUCT CONTEXT (reference only — do NOT render as text)`
- Sem instrução: `(none — follow type instructions only)`

### VISUAL STYLE

`BACKGROUND:` muda por tipo (ver a tabela da seção 3 deste dossiê).

**NÃO PODE:** cor de marca fixa em lugar nenhum. Em foto limpa (tipos 1 e 8) a
linha correta é `NO brand color anywhere`; nos demais, `Graphic accents: derive
text and graphic element colours from the art direction chosen for THIS
product ... There is no fixed brand colour.`

`Typography: Clean geometric sans-serif (Montserrat or Poppins style)` é a
única coisa fixa, e é o que faz as peças parecerem da mesma loja.

### TEXT RULE

Três formas, e exatamente uma por peça:

| Tipo | Regra |
|---|---|
| 1 — Capa | `ZERO TEXT RULE` — nenhuma palavra |
| 8 — Ambientação | `ZERO TEXT RULE, ONE EXPLICIT EXCEPTION` — só "Imagem meramente ilustrativa" |
| 2–7, Personalizado | `TEXT ZONES RULE` — texto só em painel, nunca sobre o produto |

**Defeito clássico:** a ambientação receber a regra de zero texto absoluto
enquanto o brief em português manda escrever "Imagem meramente ilustrativa".
Duas ordens opostas na mesma mensagem, e o modelo resolve escrevendo mais.

### COMPOSITION

Quatro linhas, e **uma só** medida de ocupação:

```
- COMPOSITION: Product occupancy <faixa>. <complemento do tipo>
- Maintain product exact proportions — NEVER stretch, compress, or distort
- Maximum N information elements ...   (ou a linha de "sem texto")
- Professional studio quality — high-end e-commerce agency standard
```

**Duas faixas de ocupação diferentes no mesmo prompt é sempre defeito.** Já
houve três ao mesmo tempo: 85‑92 no inglês, 90‑95 no preset e 80‑92 no bloco de
protagonismo, todas na mesma mensagem, com a seção em português rotulada como
"override any conflicting rule below". O gerador escolhia — e escolhia pequeno.

O mesmo vale para o teto de blocos: `Maximum N`, "exatamente N bloco" e "use de
X a Y blocos" não podem discordar.

### PRODUCT INTEGRITY RULES e ADDITIONAL RULES

Fixas em todos os tipos, com **uma** variação: a linha de pessoas.

- Tipo 7: `PEOPLE ARE REQUIRED in this image type` — a peça é a entrega do
  presente, com duas pessoas
- Todos os outros: `NEVER add people or human figures unless...`

As duas juntas no mesmo prompt é defeito.

### THE TIE-BREAKER

Fecha todo prompt, sem exceção:

```
The environment adapts to the product. The product NEVER adapts to the
environment.
The real product photographs have higher priority than the palette, the art
direction, the lighting, the styling and the scene.
If any instruction in this message conflicts with the real product reference,
IGNORE that instruction and preserve the product exactly as photographed.
```

Ela existe porque o próprio código já sabia que **gerador de imagem ignora
instrução negativa** (`conferir_ajuste`, `imagem.py`): a trava de cor era só
proibição, e faltava a ordem positiva de desempate.

---

## 3. O contrato por tipo

Tudo isto sai de **uma** fonte cada, e é por isso que não pode ser copiado para
outro lugar: `OCUPACAO` (`imagem.py:168`), `BLOCOS` (`imagem.py:211`),
`modo_fundo_do_tipo`, `pode_ter_texto`.

| # | Tipo | Ocupação | Blocos | Fundo | Texto | Pessoas |
|---|---|---|---|---|---|---|
| 1 | Capa do anúncio (fundo branco) | 85–92% | 0 | branco puro | zero | não |
| 2 | Benefícios do produto | 60–75% | 3–5 | deduzido | painel | não |
| 3 | Benefícios no cenário de uso | ≥45% | 2–3 | deduzido | painel | não |
| 4 | Close nos detalhes | 80–92% (do detalhe) | 1–2 | deduzido | painel | não |
| 5 | Características técnicas | 50–65% | 1–6 | deduzido | painel | não |
| 6 | Quebra de objeção | 50–65% | 3–4 | deduzido | painel | não |
| 7 | Presenteie | 30–45% | 1 | deduzido | painel | **sim, duas** |
| 8 | Ambientação realista | **escala real**, sem porcentagem | 0 | o próprio ambiente | só "Imagem meramente ilustrativa" | não |
| — | Personalizado | ≥70% | 3–5 | o colaborador manda | painel | não |

**Por que a 8 não tem porcentagem:** ela já teve, e o dono relatou o resultado
— *"criando ambientação com o produto desproporcional ao que ele é no ambiente,
parece que ele é GIGANTE"*. Numa foto ambientada o produto domina por **foco**,
não por tamanho. Pôr um número ali traz o problema de volta.

**Por que a 7 caiu para 30–45%:** ela virou cena de entrega com duas pessoas.
Duas pessoas e o produto a 55–70% do quadro só fecham inflando o produto ao
tamanho de um torso — a mesma armadilha da 8.

---

## 4. A identidade do tipo — onde mais se erra

A IA que escreve o plano **renomeia e reordena** os tipos. Ela devolve
"Foto editorial — ambientação realista" no lugar de
"8 — Ambientação realista (sem texto)".

Sem número na frente:

```
preset_do_tipo   -> ""        (a peça vai sem as regras do tipo)
modo_fundo_do_tipo -> "padrao"  (a ambientação recebe fundo de marketing)
pode_ter_texto   -> True      (a foto editorial ganha título e selo)
```

Foi assim que a ambientação saiu com "ACOMPANHA 2 CANETAS DE LUXO" e um botão
"COMPRAR AGORA" desenhado dentro da imagem.

`tipo_canonico` (`imagem.py:3032`) desfaz isso pelo `numero` do plano. **Ao
auditar, confira sempre:**

1. `IMAGE TYPE:` traz o rótulo oficial, com o `N — ` na frente
2. Dois cartões do plano não caem no mesmo tipo oficial
3. Nenhum tipo pedido ficou de fora

O plano na tela avisa em vermelho quando 2 ou 3 falham.

---

## 5. Um produto ou quatro? — os dois, nesta ordem

A pergunta do dono foi exatamente esta, e ela tem resposta, não empate.

**Um produto só já acha todo defeito de MONTAGEM.** Contradição numérica,
bloco que sumiu, placeholder vazado, ordem e contraordem, tipo embaralhado —
nada disso depende do produto. Medido, comparando o mesmo tipo nos quatro
produtos do gerador:

```
album          ocup=60–75%   tie-breaker=1   paleta-mãe=1
caneca         ocup=60–75%   tie-breaker=1   paleta-mãe=1
porta_canetas  ocup=60–75%   tie-breaker=1   paleta-mãe=1
brinquedo      ocup=60–75%   tie-breaker=1   paleta-mãe=1
```

A estrutura é idêntica. Rodar os quatro nesta fase entrega **quatro cópias do
mesmo achado** — e quadruplica a leitura sem acrescentar informação.

**Quatro produtos acham o defeito de JULGAMENTO.** Este só existe quando os
produtos discordam entre si:

| Só aparece com variedade | Como se vê |
|---|---|
| A direção de arte é deduzida ou caiu num padrão? | Quatro produtos opostos têm de dar quatro paletas e quatro conjuntos de materiais diferentes |
| A instrução de reflexo dispara? | Só o porta-canetas dourado tem risco ALTO. Se a linha de reflexo não sair nele, não sai em lugar nenhum |
| O Presenteie troca o par? | O brinquedo infantil tem de pedir pai e filho; os outros três, adulto |
| O cenário é do produto ou genérico? | A caneca pede taverna, o porta-canetas pede escritório. Se os dois derem a mesma mesa, a dedução não está acontecendo |
| A trava de cor aguenta cor difícil? | "multicolorido" e "dourado escuro" são os que o gerador mais tenta "harmonizar" |

### A ordem recomendada

**Fase 1 — um produto, até zerar.** Use `album`. Rode os dez cenários, ache
todo defeito estrutural, corrija na fonte única, acrescente a regra em
`checar_prompts.py`. Só passe para a fase 2 quando a varredura estiver limpa.

**Fase 2 — os quatro, para o julgamento.** Rode `--produto todos` e compare
lado a lado. O que se procura aqui não é "o prompt está bem montado" — é "esta
direção de arte é mesmo deste produto".

Inverter a ordem custa caro: um defeito estrutural encontrado na fase 2
aparece quatro vezes, e some quatro vezes com uma correção só.

**Os quatro produtos do gerador** foram escolhidos para serem opostos nos
eixos que decidem a direção de arte — cor, material e acabamento,
posicionamento, público e ambiente:

| | Cor / material | Posicionamento | Público | Reflexo |
|---|---|---|---|---|
| `album` | preto fosco, papel | delicado, premium | adulto | baixo |
| `caneca` | cinza pedra, resina + inox | temático, artesanal | masculino | médio |
| `porta_canetas` | dourado, metálico brilhante | premium corporativo | adulto | **alto** |
| `brinquedo` | multicolorido, silicone | divertido, leve | **infantil** | médio |

Dois produtos parecidos testam uma coisa só, duas vezes. Se você trocar algum
destes quatro por um produto seu, troque mantendo o contraste: o valor está na
discordância entre eles, não na quantidade.

---

## 6. Como testar — o protocolo

### 6.1 Gerar a matriz, sem gastar

```bash
python3 gerar_prompts_teste.py                      # fase 1: album, 10 cenários
python3 gerar_prompts_teste.py --produto todos      # fase 2: os quatro
python3 gerar_prompts_teste.py --listar             # cenários e produtos
```

Leia `prompts_teste/_INDICE.md` primeiro. **O arquivo que importa é o
`_ENVIADO.txt`**; o `_pt.txt` é o brief de onde ele nasce, útil só para
descobrir *onde* um defeito entrou.

Cada cenário muda **uma** coisa em relação ao `01_completo`. Mudar duas de uma
vez faz o arquivo parar de responder à pergunta "o que esta variação causa".

### 6.2 O que procurar, nesta ordem

1. **Contradição numérica** — duas faixas de ocupação, dois tetos de blocos,
   duas contagens de texto. `grep -E "occupancy|Maximum [0-9]|exatamente [0-9]"`
2. **Ordem e contraordem** — "escolha a paleta" ao lado da direção herdada;
   "NEVER add people" no tipo 7; zero texto ao lado de "escreva X"
3. **Cor fixa** — `grep -iE "azul|#1A3A6B|#E8EEF5|navy"`
4. **Bloco que sumiu** — compare o `_pt.txt` com o `_ENVIADO.txt`: toda linha
   não vazia do primeiro tem de existir no segundo
5. **Placeholder vazado** — `grep -E "\{faixa\}|\{blocos\}|\{direcao\}"`
6. **Repetição entre peças** — as oito cenas do mesmo cenário têm de ser
   diferentes. Consistência é mesma paleta e mesmo material, não mesma mesa

### 6.3 Comparações que revelam defeito

| Compare | O que tem de acontecer |
|---|---|
| `10_rotulo_inventado_pela_ia` × `01_completo` | **Idênticos**, arquivo por arquivo |
| `02_sem_direcao_de_arte` × `01_completo` | Só o 02 tem "escolha a paleta"; só o 01 tem `PALETA-MÃE` |
| `03_sem_plano_de_triagem` | Sem `TEXTO EXATO`, sem `Cena desta peça` |
| `04_sem_dados_tecnicos`, tipo 5 | Nenhum número de medida inventado |
| `09_copy_acima_do_teto` | O teto de cada tipo bate com a tabela da seção 3 |
| O mesmo tipo entre os quatro produtos | Estrutura idêntica, direção de arte diferente. Estrutura diferente = defeito; direção igual = a dedução não está acontecendo |

### 6.4 Achou um defeito — o que fazer

Nesta ordem, e o passo 3 não é opcional:

1. **Achar a raiz, não o sintoma.** Pergunte *o que falta neste sistema para
   isto não acontecer de novo*. Corrigir o texto onde o problema apareceu, e
   não em todos os lugares onde a regra alcança, é como a paleta azul voltou
   cinco vezes.
2. **Corrigir na fonte única.** Ocupação em `OCUPACAO`, blocos em `BLOCOS`,
   direção de arte na triagem. Nunca escrevendo o número num segundo lugar.
3. **Acrescentar a regra em `checar_prompts.py`.** Ela monta o prompt
   **enviado** dos nove tipos e confere uma tabela de regras. Defeito
   corrigido sem regra nova volta — foi o que aconteceu todas as vezes.
4. **Testar a regra por mutação.** Quebre o código de propósito e confirme que
   a varredura reprova. Regra que não reprova nada não protege nada.

### 6.5 Os três verificadores, antes de qualquer push

```bash
python3 -m compileall -q .      # sintaxe
python3 checar_ordem.py *.py    # nome lido antes de existir (UnboundLocalError)
python3 checar_prompts.py       # as regras, no prompt ENVIADO
python3 imagem.py               # auto-testes do módulo
```

---

## 7. O que já quebrou — a lista que não pode ser reinventada

Cada linha é um prejuízo real. Se um prompt novo reintroduz qualquer uma delas,
é regressão, não novidade.

| O que aconteceu | Causa |
|---|---|
| Dois terços do brief nunca chegavam ao motor | Recorte por regex em `gerar_imagem_ia` |
| A varredura dava "ok" mesmo assim | Ela conferia o brief, não o enviado |
| Três faixas de ocupação na mesma mensagem | O número escrito em três lugares |
| Paleta azul fixa, cinco voltas | Corrigida onde o sintoma apareceu, não onde a regra alcança |
| Ambientação com "COMPRAR AGORA" | Rótulo sem número → tipo não reconhecido |
| Copy exata sumindo do prompt | Índice do plano por rótulo, busca por tipo canônico |
| "Portátile", "apoliando" na tela do gestor | Sem copy exata, o gerador redige sozinho |
| Produto gigante na ambientação | Porcentagem de ocupação numa peça de escala real |
| Cartões em cima do produto | Ocupação alta ao lado de "texto em zona separada" |
| Peça de medidas com painel de benefícios | Triagem embaralhou os tipos |
| Três gerações pagas por "PREMIUM" | Conferência de texto reprovando estrangeirismo |
| "1 de 8 sem motivo algum" | `st.rerun()` apagando os avisos do laço |
| Medida repetida na mesma peça | Preset não proibia o valor aparecer duas vezes |
| Textura e mancha inventadas no close | Macro sem exigir área nítida nas fotos |

---

## 8. Limites honestos deste dossiê

- **O prompt certo não garante a imagem certa.** O gerador erra por conta
  própria. Este documento cobre a montagem; a qualidade final depende também do
  motor, das fotos e do plano da triagem.
- **Uma diferença entre o preview e a geração real:** quando há referências de
  AMBIENTAÇÃO, o cenário lido delas é acrescentado na hora de gerar. A tela diz
  isso.
- **O `gerar_prompts_teste.py` troca a leitura de visão por um texto fixo.**
  Ele confere a MONTAGEM, não a descrição do produto. Defeito de descrição só
  aparece gerando com fotos reais.
- **A direção de arte dos quatro produtos do gerador é escrita à mão.** Ela
  simula o que a triagem devolveria, para testar a MONTAGEM do prompt. Se a
  triagem decide mal — paleta errada para o produto —, isso só aparece
  rodando a triagem de verdade, no Studio, com fotos reais.
- **Este arquivo envelhece.** `checar_prompts.py` não — ele roda. Quando os
  dois discordarem, o executável manda.
