# MS Studio — regras de trabalho

## AS SETE REGRAS SUPREMAS

Ditadas pelo Léo, dono do negócio, em 09/09/2026. Elas vêm antes de tudo o que
está escrito abaixo e antes de qualquer instrução de tarefa. Cada uma nasceu de
um prejuízo real — o que está entre parênteses aconteceu.

**0. O sinal `!` é ordem de resumo.**
Mensagem com `!` significa: resuma a resposta anterior. Sem explicação nova,
sem justificativa, sem repetir o que já foi dito — só o essencial do que eu
acabei de escrever, em poucas linhas.

**0-bis. O sinal `@` sozinho é ordem de conferência.**
Mensagem com `@` e mais nada significa: aplique o PROTOCOLO DE CONFERÊNCIA
inteiro, sem pedir para repetir o que ele é. Ele está escrito em "O RETRABALHO
QUE EU GERO", mais abaixo, e são sete passos:

1. Rodar os **sete verificadores**, e colar a saída — não "devem passar".
2. Rodar o auto-teste de **todo arquivo tocado**, e os 60+ do repositório.
3. Responder *"qual verificador leu a linha que eu mudei?"* para cada nome
   novo ou alterado. Nome sem guarda: escrever a guarda, ou dizer em voz alta
   que aquela linha sobe sem rede.
4. **Mutação** em toda guarda nova: reintroduzir o defeito e ver a guarda
   falhar. Guarda que nunca viu o defeito nunca foi testada.
5. Mapear o risco do diff: import circular, chave de widget repetida, chamada
   de rede dentro de laço de render, e quem mais lê o que mudou.
6. **De onde veio o dado do teste?** Valor escrito à mão no teste mede o meu
   entendimento do sistema, e é o meu entendimento que costuma estar errado.
   Abrir a linha que PRODUZ aquele valor e conferir o tipo — e fazer ao menos
   uma asserção partir da cadeia real, não do meio dela. *(O botão dos oito
   prompts quebrou com a guarda verde: eu passei `direcao_arte` como texto, e
   no sistema ela é dicionário.)*
7. **Conflito de merge:** a lista vem de `git diff --name-only
   --diff-filter=U`, nunca do que coube na tela — e depois de resolver, varrer
   o repositório inteiro atrás de marcador, inclusive fora do código.
8. **Custo por passada:** linha nova que grava, lê ou chama rede dentro do
   desenho da tela roda A CADA TECLA digitada. Perguntar quantas vezes ela
   roda, e quanto custa cada uma. *(A primeira versão da gravação das fotos
   escrevia 30 MB no disco por tecla.)*

`@` sozinho pede o protocolo. `@arquivo.py` continua sendo referência a
arquivo, e não tem nada a ver com isto.

**1. Resumir. Ser preciso e didático.**
Respostas de 3 a 6 linhas. Tabela em vez de parágrafo. "Sim ou não" recebe "sim"
ou "não". *("Se eu tiver que ler todos os textos que me manda meu cérebro irá
ficar exausto antes do fim do dia.")*

**2. NUNCA fazer nada de cabeça.**
Abrir o código, ler a linha, citar `arquivo:linha`. O que depende de algo fora do
repositório — a planilha, o Trello, a RHiD, a plataforma — se verifica ou se
declara como dúvida. Palpite que acerta não economiza nada; palpite que erra
custa um deploy. *("Já falei 1 milhão de vezes para olhar a porra dos arquivos
ao invés de ficar chutando.")*

**3. Mapear o estrago antes de sugerir ou aplicar.**
Toda mudança passa pela pergunta: que bug, que erro, que lentidão isto pode
causar? Antes de propor, não depois de quebrar. *(A produção caiu duas vezes por
UnboundLocalError, e uma tela passou a levar 15 segundos para abrir porque o
cache foi dado como pago sem conferência.)*

**4. O tempo dele é o recurso mais caro do projeto.**
Nada é entregue "quase funcionando". Entre duas soluções, vence a que exige menos
dele — menos clique, menos conferência, menos ida e volta.

**5. Diante de um erro, achar a raiz — não otimizar em volta dela.**
Quando algo não funciona, a primeira pergunta é *"o que falta neste sistema para
resolver isto de vez?"*, e a resposta se diz em voz alta, mesmo quando ela é
"falta uma capacidade que ele não tem". *(Foram perdidos DIAS ajustando o texto
do pedido de correção de imagem enquanto o problema real era que o sistema não
enxergava a imagem. Isso precisava ter sido dito no primeiro dia.)*

**6. Resolver o problema — não necessariamente atender o pedido.**
Entre a solução que muda o sistema e a que muda o processo, vence a que resolve
de verdade pelo caminho mais barato. Se aceitar um formato novo deixaria o Studio
mais lento ou mais frágil, a resposta certa pode ser orientar quem envia a
converter o arquivo — e não engordar o sistema para ele aceitar tudo.

O critério é sempre o mesmo: **o problema deixou de existir?** Um sistema que
aceita tudo e ficou lento não resolveu nada: trocou um incômodo por outro, maior
e permanente. Quando a saída estiver fora do código, diga isso com todas as
letras, em vez de construir o que ninguém precisava.

**7. A causa pode estar na operação, não no sistema.**
Antes de mexer no código, perguntar se o número errado não vem do jeito como se
trabalha. Analisar o processo é parte do diagnóstico, não desvio dele — e apontar
isso não é empurrar a culpa para a equipe: é achar onde a correção cabe.

Nesta base já aconteceu três vezes. A ociosidade subia porque alguém esquecia a
etiqueta FILMAGEM. O custo do produto vinha errado porque o SKU é digitado à mão,
e o mesmo código servia a dois produtos diferentes. O cartão de análise punia
quem entrava depois porque ninguém lembrava de marcar a pessoa no começo.

Nenhum desses era bug. Todos apareciam como bug.

---


## Detalhamento da Regra 2 — conferir no arquivo antes de afirmar

**Nunca responder de memória sobre o comportamento do sistema.** Abrir o
arquivo, ler a linha, e só então afirmar. Quando a resposta depende de algo
fora do repositório (a planilha, o Trello, a RHiD), dizer que depende — e dizer
exatamente de quê — em vez de completar com o palpite mais provável.

Isto não é zelo: é produtividade. Toda vez que esta regra foi quebrada nesta
base, o custo foi retrabalho imediato:

- "os cartões INTERROMPIDO já pausavam o tempo" — não pausavam.
- "o cache já foi pago por outra leitura" — não tinha sido; a tela passou a
  levar 15 segundos para abrir.
- "Nicollas e Luiz entram com meta 0" — eles tinham meta configurada; o zero
  era um padrão que eu mesmo tinha acabado de introduzir.

O palpite que acerta não economiza nada — a conferência levaria trinta
segundos. O palpite que erra custa um deploy, um relatório errado, ou uma
decisão tomada em cima de número inventado.

**Corolário:** afirmação sobre número, regra ou comportamento vem com o
`arquivo:linha` que a sustenta, ou vem com a dúvida declarada.

## Como o trabalho chega em produção

Desenvolver em `homologacao`. O merge para `main` é feito pelo GitHub MCP
(`create_pull_request` + `merge_pull_request`) — comandos `git checkout main` /
`git merge` via Bash são bloqueados neste ambiente.

**A análise de risco não se pede: ela é obrigatória em todo merge.**

O dono escreveu a condição dele dezenas de vezes — *"se for corrigir e não for
travar ou gerar nada errado, pode subir"* — e em 25/09 perguntou o óbvio: *"se
eu não mandar todas as vezes, você não analisa?"*. Analisar era para ser o
padrão, e não um favor que se pede a cada mensagem.

Então nenhum merge para `main` acontece sem que estas três respostas existam,
escritas antes do merge e não depois:

1. **Os sete verificadores passaram?** Não "devem passar": rodaram, e a saída
   está no commit.
2. **O que este commit muda que alguém mais lê?** `checar_impacto` responde
   metade; a outra metade é abrir o arquivo de quem lê.
3. **A guarda nova reprova o defeito?** Reintroduzir o defeito e ver a guarda
   falhar. Guarda que nunca viu o defeito é guarda que nunca foi testada —
   três desta base nasceram erradas assim.

Verde nos cinco não é licença para subir com produção em uso: com gente
trabalhando no Studio, quem decide a hora é o dono.

## O RETRABALHO QUE EU GERO — a varredura de 28/09 e o que ela mudou

O dono: *"só de retrabalho gerado por erros seus é infinitamente superior a
qualquer outra coisa"*. Varri a conversa inteira. O retrabalho não é variado:
são **cinco formas**, e cada uma se repetiu.

### Forma 1 — corrigir onde o sintoma apareceu, não onde a regra alcança

| O que aconteceu | O custo |
|---|---|
| `additionalProperties` escrito em `imagem.py`, faltando em `ambientacao_ref.py` | erro 400 na tela, com a linha certa já no repositório |
| paleta azul fixa | voltou **três** vezes |
| "ZERO TEXTO" removido em um lugar | sobreviveu num preset |
| regra de ocupar 65-80% | pegou a ambientação e o produto saiu do tamanho do ambiente |
| cartão de texto | quatro vozes: a regra e três presets |
| campo de imagem aceita todo formato | **um** campo (o chat) recusava, e o `video.py` mandava o frame cru |

**Guarda:** `checar_alcance.py`, o sexto verificador. Ele não julga qualidade —
pergunta se a mesma capacidade existe nos irmãos dela.

### Forma 2 — a guarda escrita DEPOIS trava a redação, não o comportamento

Os dois auto-testes sobre a variação de ângulo exigiam a frase
`"frontal, três-quartos, lateral, traseiro"` — ou seja, exigiam **a ordem que
quebrou**. Passaram verdes enquanto a produção entregava caneca torta, alça a
mais e um modelo que não existe.

Três guardas desta base já nasceram assim, e uma quarta nasceu se encontrando
a si mesma (reprovava qualquer menção a `pergunta_info`, inclusive a que o
proíbe).

**Regra:** a guarda se escreve ANTES, e se confere por **mutação** —
reintroduzir o defeito e ver a guarda falhar. Guarda que nunca viu o defeito
nunca foi testada. E ela procura no **bloco** (`inspect.getsource`), nunca no
arquivo: guarda que varre o arquivo se encontra a si mesma.

### Forma 3 — dizer "verde" sobre um texto que o verificador não lia

Em 28/09 relatei "cinco verificadores verdes" depois de editar o **prompt do
plano**. Os cinco não liam esse texto: `checar_prompts.py` monta o prompt da
IMAGEM. Sessenta regras verdes mediam outro arquivo, e o defeito estava ao lado.

**Regra:** antes de dizer verde, responder *"qual verificador leu a linha que
eu mudei?"*. Se nenhum leu, o verde não vale para ela — e ou se escreve o
verificador, ou se diz em voz alta que aquela mudança subiu sem rede.

### Forma 4 — otimizar em volta da raiz

O chat cortava em `max_tokens=2000` e parecia recusar comandos. Minha primeira
resposta foi *"divida em duas mensagens"* — processo, quando faltava
capacidade. Igual aos DIAS perdidos ajustando o texto do pedido de correção
enquanto o sistema não enxergava a imagem.

**Regra 5 já dizia isso.** O que faltava era aplicá-la à minha própria resposta.

### Forma 5 — o mesmo cálculo em dois lugares

`_processar` existe em `placar.py` e em `placar_core.py`. Já discordaram em
**330 pontos** no mesmo mês e na mesma sessão. `pergunta_info` ganhou um
segundo dono e duas peças sumiram. `LPV` e `UC` tinham duas definições cada.

**Regra:** um nome, uma resposta. Quando a mesma pergunta tem duas respostas
no código, elas passam a discordar — a questão é só quando.

### Forma 6 — descobrir uma restrição de ambiente e aplicá-la a UM leitor

Esta é a Forma 1 com um agravante: eu **já sabia** o fato, escrevi sobre ele,
e ainda assim parei no primeiro campo.

Descobri nesta base que **`st.session_state` é ilegível dentro de uma
`threading.Thread`**. Apliquei a descoberta ao número da peça — virou
`_PECA_EM_AJUSTE`, global de módulo — e escrevi até uma guarda que abre uma
Thread de verdade para provar (`imagem.py:8717`).

E deixei `produto` e `usuario` lendo do `session_state` **no mesmo
`append_row`, duas linhas ao lado** (`log_imagem.py:59-61`). A geração inteira
roda em thread (`imagem.py:7162`), então toda linha do log gravou produto
vazio; o filtro por nome nunca bateu; e o `.txt` do histórico sempre voltou
vazio, dizendo "nenhum prompt registrado" — que era a segunda mentira
empilhada na primeira.

**Três regras saem daqui:**

1. **Restrição de ambiente se varre, não se corrige.** Achou que thread não lê
   `session_state`, que o container roda em UTC, que o Python é 3.11? A
   correção não é a linha que doeu: é **listar todos os leitores daquele
   recurso** e conferir um a um. `grep` do nome do recurso, não do sintoma.

2. **A guarda exercita o CAMINHO INTEIRO no ambiente real.** A minha abria uma
   Thread e chamava `peca_em_ajuste()` sozinha — a função que eu tinha acabado
   de escrever. Se tivesse chamado `registrar()` de dentro da Thread e olhado a
   linha gravada, os três campos vazios apareciam de uma vez.

3. **Campo que pode sair vazio em silêncio precisa de guarda de CONTEÚDO.**
   `registrar` engole a própria exceção de propósito — registro não pode
   derrubar geração — e grava `""`. "Produto vazio" ficou indistinguível de
   "não digitou nome". Guarda que só confere "não explodiu" não vê isso:
   ela tem de conferir **o que foi escrito**.

**Guarda:** `checar_alcance.py` passa a procurar leitura de `st.session_state`
dentro de função alcançável por `threading.Thread`, e reprova.

### Forma 7 — a guarda alimentada com dado que eu mesmo inventei

O botão dos oito prompts quebrou em produção — `AttributeError: 'dict'
object has no attribute 'strip'` — **com a guarda dele verde**.

Por quê: a guarda chamava `txt_dos_prompts` com pares de string que eu
escrevi na hora, e com `direcao_arte="Medieval Rústico"`. Na realidade a
direção de arte é um **dicionário** (`imagem.py:6681`). O teste nunca tocou
`prompt_de_cada_peca`, que é quem monta os pares de verdade.

**Isto é diferente das Formas 2 e 6.** Ali a guarda travava a redação, ou
exercitava a função isolada. Aqui ela exercitava a função certa — só que
com uma ENTRADA que não existe no sistema. Duplo mais pobre que a realidade
"acusa o inocente"; duplo com o TIPO errado faz pior: **absolve o culpado**.

**Três regras:**

1. **A entrada do teste vem do sistema, não da minha cabeça.** Antes de
   escrever um valor no teste, abrir o lugar que o produz e conferir o
   TIPO. `cfg.get("direcao_de_arte")` devolve `{}`, não `""` — está escrito
   na linha que monta o `cfg`.

2. **Toda função nova é exercitada pela CADEIA, ao menos uma vez.** Testar
   `txt_dos_prompts` sozinha é legítimo para as bordas; mas uma das
   asserções tem de partir de `prompt_de_cada_peca` de verdade, com o `cfg`
   na forma que a tela monta. Foi isso que faltou.

3. **Valor de teste escrito à mão é suspeito por definição.** Quando a
   guarda é a única coisa que produz aquele dado, ela está medindo o meu
   entendimento do sistema — e o meu entendimento é justamente o que estava
   errado.

### Forma 8 — resolver conflito só onde o git apontou na tela

Duas vezes no mesmo dia. `CLAUDE.md` subiu **commitado com `<<<<<<< HEAD`
dentro**: resolvi os três `.py` que li na saída do merge e não olhei o
resto. Depois a guarda nova achou um segundo, `CONTEXTO_PARA_ANALISE.txt`,
commitado havia semanas. E no merge seguinte eram **seis** arquivos, não
três — o `tail -6` da saída tinha escondido metade.

**Duas regras:**

1. **A lista de conflitos vem de `git diff --name-only --diff-filter=U`**,
   que é a fonte, e nunca do que coube na tela.
2. **Depois de resolver, varrer o repositório inteiro** atrás de marcador —
   inclusive fora do código. Nenhum dos seis verificadores lia `.md` ou
   `.txt` antes disto.

**Guarda:** `checar_alcance.py` varre `.py`, `.md`, `.txt` e `.toml` e
reprova marcador de conflito commitado.

### Forma 9 — subir com gente no meio do trabalho

28/09, 17:07: fiz o merge para `main` enquanto o dono gerava imagens. 17:17:
ele me mandou o print com três fotos anexadas na tela e o Studio respondendo
"Suba pelo menos uma foto do produto".

O deploy reinicia o processo. A lista de NOMES do upload fica no NAVEGADOR; os
BYTES ficam na memória do PROCESSO. Reiniciou, os dois deixam de concordar — e
quem está olhando a tela vê as fotos lá, anexadas.

A regra já existia, escrita em "Como o trabalho chega em produção": *"verde nos
cinco não é licença para subir com produção em uso: com gente trabalhando no
Studio, quem decide a hora é o dono"*. Eu subi mesmo assim.

**Duas regras:**

1. **Antes de todo merge para `main`, perguntar se pode subir AGORA** — e a
   pergunta é uma linha, não um relatório. Quem está no Studio aparece em "NO
   STUDIO AGORA", na barra lateral.
2. **Deploy no meio de um trabalho tem de ser recuperável.** O que a pessoa
   perde num reinício é o que o sistema não guardou em disco. A galeria já era
   guardada; as fotos anexadas não eram. Toda vez que o reinício custar
   trabalho, a pergunta não é "como evitar o reinício" — é *"o que falta gravar
   para que ele não custe nada?"*.

### O que eu mapeei e o que NÃO mapeei

**Mapeado e corrigido:** os cinco defeitos acima, as peças 7 e 8, o produto
torto, o `st.rerun()` que apagava a tela, o botão de histórico no lugar errado,
o `dueComplete` invisível no mapa de pontos, o chat que recusava HEIC, o
`video.py` que mandava frame cru, os quatro rótulos que mentiam.

**NÃO mapeado — dito em voz alta em vez de escondido:**

| Aberto | Por quê |
|---|---|
| corte de texto nas peças 4 e 5 | preciso do prompt real; não sei se é o layout ou o modelo desobedecendo |
| `_processar` duplicado | unificar é mudança grande; o risco tem de ser mapeado antes |
| retrato do placar antes de 28/09 | não existe e não volta |
| prompts gerados antes do deploy do log | perdidos |
| fatura PDF | é lida e mostrada, nunca gravada — falta conferir contra uma fatura real |

---

## Antes de todo push: `python3 conferir.py`

**Um comando.** Ele roda os sete verificadores, os 66 auto-testes de módulo, a
conferência da varredura e a checagem de conflito, e dá um veredito só.

E ele **descobre** os verificadores no disco em vez de ter uma lista escrita:
verificador novo entra sozinho. Com lista, o defeito seria o de sempre —
alguém escreve o oitavo, esquece de somar, e a conferência segue dizendo
"verde" medindo sete.

Ele existe porque rodar sete comandos à mão, na ordem certa, toda vez, era a
peça mais boba e mais cara do protocolo. Esquecer um é gratuito e silencioso:
foi assim que relatei "cinco verificadores verdes" depois de editar um texto
que nenhum dos cinco lia.

**Ele cobre os passos 1, 2 e 7.** Os passos 3, 5, 6 e 8 continuam sendo
leitura — e é neles que os últimos seis defeitos apareceram.

Na primeira execução ele reprovou quatro, e um era defeito meu de horas antes:
`varredura_formas.py --autoteste` saía com código 1 **sempre**, porque uma
função devolvia contagem de falhas e a irmã devolvia booleano, e eu somei as
duas com `and`. Ninguém tinha visto porque ninguém lia o código de saída — e
pior: a 16ª entrada do `checar_mutacao.py` estava **verde por acidente**, já
que "reprova com o defeito de volta" era verdade sem medir nada. Daí o
`checar_mutacao.py` passar a conferir que o comando PASSA antes de mutar.

Os sete, se precisar rodar um de cada vez:

```
python3 -m compileall -q .      # sintaxe
python3 checar_ordem.py *.py    # nome lido antes de existir (UnboundLocalError)
python3 checar_prompts.py       # regra de imagem que ficou faltando ou sobrando
python3 checar_impacto.py       # quem mais lê o que este commit mudou
python3 checar_tela.py          # a tela monta sem quebrar?
python3 checar_alcance.py       # a correção chegou em TODOS os irmãos?
python3 checar_mutacao.py       # as guardas VEEM o defeito? reintroduz e exige vermelho
```

O sétimo nasceu de uma pergunta do dono, depois da terceira conferência
seguida: *"tem certeza? você falou isso da primeira vez, mandei revisar e
pegou novos dois erros quando tinha acabado de revisar!"*

Ele estava certo, e a medição deu razão a ele. Em três rodadas do protocolo os
seis acharam **zero** defeitos novos; o passo 5, feito à mão, achou **quatro**.
Os seis rodam igual sempre — a mutação (passo 4) e o mapa de risco (passo 5)
dependiam de eu lembrar, e à mão eu não faço igual duas vezes.

`checar_mutacao.py` tira o passo 4 da minha mão. Cada entrada é um defeito que
JÁ aconteceu aqui, com o trecho certo e o errado: ele reintroduz o defeito,
roda o verificador que deveria pegá-lo, e exige **vermelho**. Guarda que fica
verde com o defeito de volta nunca foi guarda.

Na primeira execução ele reprovou três. **Duas eram mutação minha malfeita** —
um `or` que deixava a chamada na árvore (e a guarda é por AST, então ela via,
certíssima) e um corte pela metade. Lição própria: mutação que não reintroduz
o defeito dá alarme falso, e alarme falso ensina a ignorar o verificador —
quase reescrevi duas guardas que estavam certas. **A terceira era guarda fraca
de verdade**, e do tipo que eu não acharia à mão: tirando a conferência do laço
da geração, `checar_tela` continuava verde porque a chamada do chat ainda
estava lá. Ela perguntava "existe em algum lugar" e não via a peça que deixou
de ser conferida.

O arquivo é sempre restaurado, inclusive quando o verificador estoura no meio:
verificador que deixa o repositório mutado é pior que nenhum.

O sexto existe porque a forma mais cara de retrabalho desta base é corrigir
**no lugar onde o problema apareceu** em vez de em todos onde a regra alcança.
Ele varre os campos que recebem imagem (todos têm de aceitar todo formato — o
Studio tem `normalizar_imagem`), confere se quem manda imagem a um modelo passa
pelo conversor, reprova rótulo que promete menos do que o campo aceita, e exige
que `checar_prompts.py` leia o prompt do PLANO — que era o único texto de
prompt que varredura nenhuma lia, e onde as peças 7 e 8 sumiram com os cinco
verificadores verdes.

O quinto existe porque os outros quatro **não desenham nada**, e uma tela
quebrada passou por todos eles. Em 25/09 a Home caiu em produção com
`TypeError: string indices must be integers`: `_lpv_card` devolvia o cartão já
renderizado numa lista em que todo o resto era dicionário. O auto-teste
conferia o HTML dessa função isolada — exatamente o único lugar onde o tipo
errado parecia certo.

`checar_tela.py` troca o Streamlit por um duplo, põe dado de mentira no lugar
das planilhas e manda a página se desenhar inteira, em cinco cenários: com
tudo, sem LPV, sem custo fixo, sem Bling, sem a BASE DE VENDAS. O duplo também
guarda toda chave de widget e explode na repetida — foi assim que a tela de
Extratos caiu no mesmo dia, com `StreamlitDuplicateElementKey: ext_fin_0`.

**Só o que vai à planilha ou à rede é substituído.** A primeira versão dele
trocava `linha_do_mes` por um dicionário mais pobre que a realidade e acusou o
inocente. Verificador que dá alarme falso é pior que nenhum: ensina a
ignorá-lo.

O quarto existe porque três correções seguidas precisaram de uma segunda
correção, e o padrão era sempre o mesmo: **mudei uma coisa e não listei quem
lê ela.**

`tipo_canonico` passou a devolver o rótulo oficial — e o índice do plano era
feito com o rótulo cru. A copy exata sumiu do prompt, em produção. O limite de
fotos subiu de três para seis — e ninguém perguntou o que limita além da
quantidade: seis fotos de 10MB são timeout. `BLOCOS[5]` virou 4 — e a caneca
tinha cinco cotas.

Ele não julga qualidade: só pergunta se o nome que mudou tem leitor em outro
arquivo e se existe alguma guarda citando ele. Nome mudado, com leitor fora, e
sem guarda: reprova.

**E a guarda se escreve ANTES da mudança.** Escrita depois, ela sai parecida
com o que já foi feito — foi assim que três guardas minhas nasceram erradas
nesta base: a que descartava "margens generosas" por conter "rosa", a que
acusava a própria trava de cor, e a que se encontrava a si mesma.

O terceiro existe porque eu corrigia regra de imagem NO LUGAR ONDE O PROBLEMA
APARECEU, e não em todos onde ela alcançava. A paleta azul fixa voltou três
vezes; o "ZERO TEXTO" sobreviveu num preset depois de eu o remover; a regra de
ocupar 65-80% do quadro pegou a ambientação e o produto saiu do tamanho do
ambiente. Nos três casos procurei pelo TEXTO do sintoma em vez do ALCANCE da
regra.

`checar_prompts.py` monta o prompt real dos nove tipos e confere, um a um, o
que cada um TEM de conter e o que NÃO PODE. Mexeu numa regra de imagem sem
passar por ele, ela reaparece na tela de alguém daqui a três semanas.

O segundo existe porque `UnboundLocalError` derrubou o Painel de Metas duas
vezes seguidas: sintaxe válida, nome conhecido, só explode em execução. Numa
página Streamlit de duas mil linhas, mover um bloco cruza essa fronteira sem
aviso — e `import x as y` liga nome local igual a uma atribuição.

## Fatos do ambiente que já custaram caro

- **O container do Railway roda em UTC.** `datetime.now()` devolve UTC;
  comparação com horário local exige `datetime.now(placar_core.FUSO)`.
- **Python 3.11.** f-string com aspas duplas aninhadas só vale de 3.12 em
  diante — pré-calcular numa variável.
- **O HTML do painel passa pelo markdown do Streamlit.** Linha só com espaços
  fecha o bloco HTML, e tag partida em duas linhas vira parágrafo. `<p>` dentro
  de `<svg>` faz o navegador fechar o svg ali. A TV escapa disso porque monta a
  página inteira sem markdown.
- **Nunca commitar valor de secret.** `.streamlit/secrets.toml` está no
  `.gitignore` — um commit dele já derrubou o Fim de Expediente.

## Uma regra é uma regra, e não uma cópia

Contratação é cadastro na aba `equipe` da planilha, não alteração de código.
Lista de pessoas escrita no arquivo já escondeu dois colaboradores do painel e
tirou dois outros do próprio login. Quando a mesma pergunta tem duas respostas
no código, elas passam a discordar — a questão é só quando.
