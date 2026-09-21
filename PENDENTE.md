# Pendências — o que ficou combinado e ainda não foi feito

Fica no repositório, e não no chat: pendência dita numa conversa morre com a
conversa. Cada item diz o que é, por que existe e onde mexe. Concluído sai
daqui no mesmo commit que o resolve.

---

## 1. Reorganizar onde mora cada ajuste  ·  pedido em 17/09/2026

**O que é.** As telas de configuração estão espalhadas por critério nenhum. A
configuração das COLUNAS DO TRELLO — prioridade, tempo estimado e espera de
cada coluna — mora em **Análise de Metas › Configuração**
(`analise_metas.py:7124`), e não tem nada a ver com análise de metas. O dono
procurou no Administrativo, que é onde ela deveria estar.

**Por que importa.** Ajuste que ninguém acha é ajuste que ninguém faz. Já
aconteceu com o cadastro da equipe: ele vivia em Análise de Metas, uma
colaboradora nova ficou com login funcionando e fora das metas, e ninguém
tinha errado nada — faltava saber que a segunda tela existia. Isso foi
consertado movendo a tela para o Administrativo; as colunas do Trello são o
mesmo caso, ainda aberto.

**Onde está hoje:**

| Ajuste | Tela atual | Arquivo |
|---|---|---|
| Colunas do Trello (prioridade, tempo, espera) | Análise de Metas › Configuração | `analise_metas.py:6072` `_secao_colunas` |
| Metas e período | Análise de Metas › Configuração | `analise_metas.py` `_secao_configuracao` |
| Equipe medida | Administrativo | `admin.py` `_secao_equipe` |
| Usuários e senhas | Administrativo | `admin.py` `pagina_admin` |
| Pausas do time | Ponto | — |

**O que falta decidir.** O critério. Uma proposta a levar ao dono: tudo que é
CADASTRO (quem, quanto, quais colunas, quanto vale cada uma) vai para o
Administrativo; Análise de Metas fica só com leitura e gráfico. Nada foi
movido ainda — mover tela sem o critério acordado é trocar um lugar errado
por outro.

---

## 2. Seletor de pasta do Drive ao salvar imagem  ·  pedido em 17/09/2026

**O que é.** Hoje não existe "salvar NESTA pasta". O Studio procura a pasta
pelo nome do produto + código (`imagem.py:2646`), e quem gerou sem código
precisa acertar o nome exato da pasta de cabeça para cair nela de novo.

**O buraco medido.** O botão "☁️ Salvar esta no Drive" pega a primeira pasta
que a busca devolver, sem mostrar qual e sem deixar escolher
(`imagem.py:3964`). Com duas pastas começando pela mesma palavra, a imagem vai
para a errada em silêncio. O botão "APROVAR E SALVAR todas" não tem esse
problema: mostra o nome e oferece um seletor quando há mais de uma.

**O conserto combinado.** Um seletor listando as pastas do Drive, valendo para
os dois botões de salvar. Aguardando o "faça".

---

## 3. Ligar a leitura do Controle_MS  ·  17/09/2026

**Onde parou.** O arquivo é `.xlsx` de ~12 MB, com tabela dinâmica, e o dono
NÃO vai convertê-lo para Planilhas Google — ele continua alimentando pelo
Excel. Decidido: o Studio baixa o `.xlsx` do Drive e lê, só leitura.

**O que ele faz:** põe o arquivo na conta PESSOAL do Google Drive dele (a
conta da empresa tem login único, compartilhado com o time inteiro por causa
das imagens — permissão não esconde nada de quem entra com o mesmo login) e
compartilha com o robô como Leitor.

**FEITO em 17/09:** compartilhada com o robô como Editor, acesso Restrito.
Continua sendo `Controle MS.xlsx` — arquivo do Excel aberto no modo Office do
Sheets, e NÃO uma planilha Google. Por isso `gspread` não a abre: a leitura
tem que ser download pelo Drive + pandas.

O arquivo mudou de casa em 17/09: o dono criou um Drive novo, da empresa, e
subiu a planilha lá. É este o que vale:

```
ID do arquivo: 1TX3kgzb815EekA3v5mg-9MRvSc-5Ggc3
```

(O primeiro, na conta pessoal, era `1d82vJONqMXkcPPYQqLwXk1C7KJuUh-st`.)

Compartilhar com o robô deu "Você excedeu sua cota de compartilhamento" na
primeira tentativa: conta Google recém-criada tem cota de ENVIO DE E-MAIL
travada, e o compartilhamento manda um e-mail. Desmarcar "Notificar pessoas"
resolveu — o robô não lê e-mail, a notificação não servia para nada.

Abas que existem: SAIDAS PIX-BOLETO 2026 · CARTÕES · ADS E CROSS ·
SIMPLES - FLEX · CHEQUES · DEVOLUÇÕES 2026 · DIN FINANÇAS · DINAMICA ·
DASH 2026 · AJUSTE DE PLANILHA · PREÇO DE CUSTO. · BASE DE VENDAS (e mais,
cortadas na tela).

**O que falta dele:** dizer quais abas o Studio deve ler.

**FEITO:** `controle_ms.py` baixa o arquivo pelo Drive e lê com openpyxl em
modo `read_only`, com cache de 10 min. A tela de conferência está no
Administrativo (📗 Controle MS), e é lá que se vê se a leitura está de pé e
quais abas existem.

**Decisão em aberto:** cheque novo é lançado ONDE? Se for na planilha e no
Studio, os dois discordam. Proposta: o Studio importa o que já existe e daí em
diante o lançamento é pelo Studio.

---

## 4. Ociosidade — qual limite  ·  17/09/2026

Pedido: "a ociosidade de quem estiver com ela estourada cai para 5%", já
alinhado com a equipe. Hoje são 10% no normal e 5% na MAXX
(`explicacao_metas.py:49`). Falta o dono dizer qual das duas leituras vale:

| A | O limite geral cai de 10% para 5%, para todos |
| B | Só quem estourou os 10% passa a ter 5% — limite que varia por pessoa, e precisa de onde ficar cadastrado |

---

## Guardados para não procurar de novo

**E-mail do robô (conta de serviço), para compartilhar planilha ou pasta do
Drive com o Studio:**

```
martinsousa-robo@martinsousa-app.iam.gserviceaccount.com
```

Não é segredo — é só o endereço de quem lê; o segredo é a chave privada, que
mora nas Secrets. O mesmo endereço aparece no Studio em Administrativo ›
🔧 Diagnóstico do Google Drive › "Testar conexão com o Drive".

Compartilhe como **Leitor** quando o Studio só precisa ler, e como **Editor**
quando ele precisa escrever (é o caso da planilha financeira principal).

---

## Segurados a pedido do dono (prontos, não sobem sem ordem)

- **Correção do texto das imagens** e da mistura de inglês com português —
  commits `e0aa459` e `ca28d60`, em `homologacao`. Não subir para `main` sem
  ele mandar.

---

## 5. Folha desde janeiro — dados que o dono passou em 17/09/2026

Ainda NÃO estão na planilha. Ficam aqui para não se perderem no chat.

| Pessoa | Admissão | Salário base |
|---|---|---|
| Myrella | desde 01/2026 | 1.800,00 |
| Monique | desde 01/2026 | 2.400,00 |
| Gabriel | 16/03/2026 | 3.000,00 |
| Beatriz | 28/04/2026 | 1.800,00 |
| Nícolas | 24/08/2026 | 2.000,00 |
| Luiz | 26/08/2026 | 2.000,00 |
| Brunielly | 14/09/2026 | 2.000,00 |

| Cargo | Quem |
|---|---|
| Auxiliar administrativo | Myrella, Beatriz, Nícolas, Luiz, Brunielly |
| Analista de Marketing | Gabriel (Biel) |
| Auxiliar de Expedição | Monique |
| Sócio Fundador | Léo e Renan |

Vale-transporte: pago no primeiro salário, proporcional aos dias do mês
anterior; cheio só quando a pessoa fecha o mês inteiro.

Vale-transporte: 233,33 por pessoa (a equipe CLT inteira).

**Renan não é CLT** — é sócio, e a folha dele já está no Studio. Os R$ 900 que
o dono chamou de vale-transporte são o **vale-combustível** do sócio, já
cadastrado (`folha_salarial.py:86`). O que falta lá é o histórico: era 700 até
junho, virou 900 a partir de 30/07/2026.

Agosto teve duas coisas fora do normal:
- Gabriel, Myrella e Beatriz: +12% sobre o salário (bateram a meta MAXX
  coletiva, não a individual).
- Nícolas e Luiz: proporcional aos dias trabalhados, e os 12% sobre esse
  proporcional.

### Os três buracos que esses dados revelaram — 1 e 2 já consertados

1. **Mês de admissão entra com salário cheio.** `valor_no_mes` zera os meses
   ANTES da admissão (`ajustes.py:106`) e cobra o mês inteiro no mês em que a
   pessoa entrou. Para quem entrou em 24 e 26 de agosto, agosto sai inflado.
   `dias_uteis` não serve para isso: ele só divide a refeição
   (`colaboradores.py:325`).
2. **Vale-transporte era constante única no código**: 233,33 igual para todos
   e sem histórico. Virou campo por pessoa com vigência. (A motivação original
   era o Renan; ele acabou sendo outro caso — sócio, vale-combustível —, mas o
   conserto continua certo: sem ele, o mês de admissão cobrava VT cheio de
   quem trabalhou seis dias.)
3. **Bônus de um mês só não tem lugar.** Um ajuste vale "deste mês em diante".
   Os 12% de agosto cabem no modelo atual com DOIS ajustes (agosto com o valor
   maior, setembro de volta ao normal) — funciona hoje, sem código, e deixa o
   que aconteceu visível na tela.

---

## 6. O que já está pronto em `homologacao`, esperando ordem para subir

| Commit | O que é |
|---|---|
| `e0aa459` `ca28d60` | Texto das imagens: copy escrita antes de gerar, refação relida, aviso automático quando a revisão não roda, inglês fora dos prompts |
| (este) | Proporcional do mês de admissão e vale-transporte por pessoa |

Nada sobe para `main` sem o dono mandar.

---

## 7. PENDENTE conta como trabalho, e o texto diz que não  ·  17/09/2026

Achado durante o mapeamento da ociosidade (ver `OCIOSIDADE.md`).
`explicacao_metas.py:228` diz à equipe que cartão PENDENTE não conta como
atividade; `LABELS_INTERRUPCAO` (`placar_core.py:432`) não tem PENDENTE, então
ele conta.

A divergência é a favor da equipe, então não é urgente. Mas são duas respostas
para a mesma pergunta. Decisão do dono: PENDENTE entra na lista de
interrupção, ou o texto muda?

---

## 8. ~~Custo fixo: duas fontes para o mesmo número~~ — RESOLVIDO em 17/09

O dono decidiu: o Studio **provisiona** e o extrato **confere**. Linha de
extrato ligada a um item de custo fixo atualiza o item em vez de entrar como
gasto novo; divergência ajusta o valor daquele mês. Ver `FLUXO.md`.

---

## Importação dos cheques, conferida na tela  ·  17/09/2026, à noite

**Onde parou.** `cheques.py` e `cheques_tela.py` estão em produção, com os três
defeitos da primeira importação corrigidos (NaT derrubando a tela, `nan`
colapsando 69 cheques em um, folha `159.0`). Conferido contra o `Controle_MS`
de verdade: 604 linhas, 604 ids, em aberto R$ 88.675,44, pendente R$ 33.093,82,
vence em 09/26 R$ 51.117,23.

**O que falta.** O dono clicar em **Financeiro › 🧾 Cheques › Importar do
Controle MS** e conferir os três números na tela contra a planilha dele. Nada
foi gravado na aba `cheques` ainda — o número acima saiu de uma simulação
local, não de uma importação de verdade.

**Por que está aqui.** Ele interrompeu no meio para tratar uma urgência e
pediu, com estas palavras, para não deixar esquecer.

---

## Cheque pelo WhatsApp, do jeito que o Renan manda  ·  18/09/2026

**O que ele manda.** Uma foto dos canhotos (folha, data, valor, "Pago a
LEXTACK"), e duas linhas soltas: `1.400 envio` e `Pix / 30 / 45 dias`.

**O que falta construir.** A leitura dessa mensagem — foto + texto — virando o
lote de cheques. As peças que já existem: `cheques.lote()` monta os N cheques a
partir de folha, vencimento, valor total e frete; a mesma IA que lê o texto das
imagens sabe ler um canhoto. O que não existe é o pedaço que interpreta
`Pix / 30 / 45 dias` como "uma entrada no Pix e vencimentos em 30 e 45 dias" e
casa isso com as folhas da foto.

**O que bloqueia.** A entrada por WhatsApp depende de número WhatsApp Business
API, que o dono ainda não tem — todas as linhas dele já usam WhatsApp comum.

**Enquanto isso.** O cadastro em lote na tela já resolve o trabalho repetido, e
a leitura do canhoto pode entrar primeiro por upload, sem depender da Meta.

---

## ~~Triagem: editar, apagar e barrar o nome repetido~~ — FEITO em 21/09

Pedido do dono, em stand-by: **sobe junto com a próxima autorização.**

### O que ele pediu

1. Editar uma triagem já salva — hoje corrigir um erro cria uma triagem nova.
2. Selecionar uma triagem e apagá-la.
3. Barrar o cadastro quando já existe triagem com aquele nome, e avisar.

### O que o código faz hoje

| Onde | O que está lá |
|---|---|
| `triagem.py:118` `salvar_triagem` | Só `append_row` (linha 135). **Não existe nenhum caminho de UPDATE no módulo.** |
| `triagem.py:358` `_limpar_form_triagem` | Roda depois de salvar; o formulário sempre nasce vazio. Editar hoje = redigitar tudo e gerar linha nova. |
| `triagem.py` inteiro | Nenhum `delete_rows`. **Apagar não existe.** (`cheques.py` e `meta_gastos.py` já têm o padrão pronto.) |
| `triagem.py:13` `COLUNAS` | 14 colunas, **nenhuma é identificador**. Nada identifica uma linha. |

### O item 3 tem um problema, e ele precisa decidir

**Nome repetido é recurso, não defeito.** `_chave_variante` (`triagem.py:165`)
identifica a variante por **nome + medidas + peso + cores**, e
`buscar_triagens_por_trecho` (`triagem.py:176`) devolve uma entrada por
variante — é o que faz `widget_seletor_produto` mostrar as opções ao
colaborador. O exemplo está escrito no próprio código (`triagem.py:182`):
*"Caixa de relógio 5 posições" vs "10 posições"*.

Barrar por nome **acaba com isso**: as duas caixas deixam de poder existir.

### DECIDIDO pelo dono em 21/09: opção B — barra por NOME

Ele escolheu B sabendo o que ela custa (a alternativa A foi posta ao lado e
recusada). **Barra por `nome_comercial`, ponto.** Salvar com um nome que já
existe é recusado, com o aviso de que já há triagem com aquele nome e o botão
de editar a existente.

Consequência aceita: **não nascem mais variantes novas.** As que já estão na
aba `triagens` continuam lá e `widget_seletor_produto` segue mostrando elas —
o bloqueio vale para cadastro novo, não apaga o que existe. Quem precisar de
duas caixas de relógio passa a diferenciar no próprio nome
("Caixa de relógio 5 posições" / "Caixa de relógio 10 posições").

A regra abaixo fica registrada porque foi a alternativa avaliada — NÃO é a que
se implementa:

~~**A regra que resolve o problema dele sem quebrar a variante:**~~

- Repetiu a **chave inteira** (nome + medidas + peso + cores) → barra. É
  duplicata de verdade.
- Repetiu **só o nome**, com specs diferentes → não barra; mostra as que já
  existem e pergunta: *"é outra variante ou você quer editar aquela?"* — com o
  botão de editar ao lado.

### O que falta existir antes: um identificador

Para editar ou apagar é preciso saber **qual linha**. Duas saídas:

- **(a) Coluna `id` nova (uuid).** É o padrão que `cheques.py` já usa (a FOLHA é
  a identidade). Estável mesmo se alguém mexer na planilha à mão.
- **(b) Número da linha na planilha.** **Frágil** — `carregar_triagens` é
  `@st.cache_data(ttl=600)` e `get_all_records` não devolve o número da linha;
  se alguém apagar uma linha direto na planilha, o índice cacheado passa a
  apontar para outra. É a mesma classe de defeito de "escolher o item pelo
  texto da tela", que já custou caro nesta base.

**Recomendação: (a).**

### O estrago a mapear antes de aplicar (Regra 3)

- **Quem consome a triagem:** `imagem.py:3621`, `descricao.py:451`,
  `tit_ml.py:116`, `palavras_chave.py:133`, `video.py:222`,
  `ferramentas_chat.py:186`. Apagar uma triagem tira a fonte de dados desses
  seis — aceitável se for duplicata, não se for a boa.
- **O cache.** Editar e apagar têm que chamar `carregar_triagens.clear()`,
  como `salvar_triagem` já faz (`triagem.py:136`). Sem isso a tela mostra o
  antigo por 10 minutos e o colaborador edita de novo.
- **`data_hora` decide quem é "a mais recente":** `buscar_triagem_por_nome`
  pega `.iloc[-1]` (`triagem.py:221`) e `buscar_triagens_por_trecho` faz
  `keep="last"` (`triagem.py:197`). **Editar NÃO pode atualizar `data_hora`** —
  senão corrigir uma variante velha faz ela pular na frente da nova.

### Um defeito achado no caminho, que não é do pedido

`triagem.py:193` — `filtradas.sort_values("data_hora")` ordena **texto**, não
data: `data_hora` é gravada como `"%d/%m/%Y %H:%M"` (`triagem.py:128`). Em
string, `"31/12/2025"` vem depois de `"01/01/2026"`, porque compara o dia
primeiro. Ou seja: **a "mais recente" de cada variante pode ser a mais antiga**,
e vira mês. Conserto: converter para data antes de ordenar
(`pd.to_datetime(..., format="%d/%m/%Y %H:%M", errors="coerce")`).

Vale corrigir junto — é a mesma função que a edição vai mexer.

---

## ~~A TV e o Studio no mesmo container~~ — RESOLVIDO em 21/09 (serviço próprio)

**O que resolve de vez, e custa dinheiro.** O `tv_worker.py` roda o Painel de
Metas inteiro dentro do MESMO container do Studio (`Procfile`). Enquanto for
assim, a volta da TV vai cair em cima de alguém de vez em quando — `nice 19`
reparte CPU, mas não reparte memória, e é a memória que reinicia o container
(e reiniciar é o que apaga o histórico do chat).

**A saída:** o worker vira serviço próprio no Railway, ~US$ 5/mês. Aí não há
o que repartir.

**O que foi feito em 21/09, que é estrago reduzido e não solução:**
`_TV_TETO_ESPERA_SEG` de 90s para 900s (`placar.py`), valor escolhido pelo
dono. Com teto de 90s, quem ficava no Ajuste Fino levava o Painel de Metas por
cima a cada minuto e meio — ~40 vezes por hora. Agora são ~4.

**O que medir antes de gastar os US$ 5.** Os quatro campos de custo passaram a
viajar no `tv-status.json` e aparecem no rodapé do Painel de Metas: duração da
volta, pior duração, memória do worker, voltas adiadas. Se a volta levar
décimos de segundo, a TV não é a causa e o serviço separado não resolve nada —
é memória do próprio Streamlit, e a conta é outra.

---

## ~~A TV como serviço próprio no Railway~~ — NO AR em 21/09/2026

O dono autorizou ("serviço do Railway imediatamente") e logo em seguida pediu
para segurar: havia gente usando o Studio e o deploy derruba a sessão.
**Está pronto em `homologacao`, esperando ordem.**

### Por que repartir o container não resolveu

| Tentativa | Por que falhou |
|---|---|
| `nice 19` | Reparte CPU, não reparte o resto |
| Esperar por presença | Só adia; alguém sempre está dentro |
| Teto de espera (90s → 900s) | **É o próprio teto que cai em cima da pessoa.** Quem entra a 100s do fim leva a volta na cara — foi o dono quem apontou |

E o trabalho que derruba a sessão de quem produz **não serve a ninguém que
produz**: nenhuma tela do Studio lê o `static/tv.html`. Quem lê é o navegador da
TV, e só ele.

### O que já está escrito

`tv_servico.py` — sobe num container próprio e faz duas coisas: serve o
diretório `static/` por HTTP na porta que o Railway der, e roda o laço de
regeneração. Ele abre a porta ANTES de importar `placar` (o import leva
segundos, e o Railway derruba serviço que demora a atender), e repete o passo
do Procfile que monta o `.streamlit/secrets.toml` a partir de
`STREAMLIT_SECRETS` — sem isso o Trello sobe sem credencial e toda volta
termina em "credenciais do Trello não configuradas".

No container próprio o `_TV_TETO_ESPERA_SEG` vai a 0: a espera existia para não
atrapalhar o Studio, que não mora mais ao lado.

### Os passos no Railway, que são dele

1. No mesmo projeto, **New → GitHub Repo** → o mesmo repositório.
2. Nesse serviço novo, **Settings → Start Command**: `python tv_servico.py`
   (sem isso ele obedece ao Procfile e sobe outro Studio).
3. **Variables**: copiar `STREAMLIT_SECRETS` e `PLANILHA_ID` do serviço do
   Studio.
4. **Settings → Networking → Generate Domain**. O endereço que sair é a nova
   URL da TV.

### A CONSEQUÊNCIA QUE PRECISA SER DITA (Regra 3)

**Containers separados não dividem disco.** O `tv.html` que o serviço novo
escreve não aparece no serviço do Studio — então **a URL da TV muda**: passa a
ser o domínio do serviço novo, e não mais
`app.martinsousa.com.br/app/static/tv.html`. Alguém precisa trocar o endereço
na TV de parede uma vez.

O Studio continua escrevendo o próprio `tv.html` quando alguém abre o Painel de
Metas (`placar.py:2508`). Esse arquivo passa a não servir a ninguém — fica onde
está porque tirá-lo quebraria o modo `?tv=` de desenvolvimento.

### O que falta decidir antes de subir

O `Procfile` ainda sobe o `tv_worker.py` dentro do container do Studio. Depois
que o serviço novo estiver de pé, ele sai de lá — mas `TV_WORKER=1` tem de
CONTINUAR na variável do Studio, senão `app.py:43` volta a ligar a thread de
regeneração dentro do processo do Streamlit e o problema renasce pela terceira
porta.

Ordem certa: sobe o serviço novo → confere a TV no domínio novo → só então tira
o worker do Procfile.

---

## ~~Cheques: envio maior que a compra é normal~~ — FEITO em 21/09

Em stand-by, para subir com a próxima autorização.

### O que ele disse

Parte da compra sai no PIX ou no cartão e o resto em cheque. Pode acontecer de
o cheque cobrir só mercadoria e o ENVIO da compra inteira ser maior do que a
soma dos cheques. **Não é erro de digitação.**

### O que o código faz hoje

`cheques_tela.py:234` — `elif envio_total > valor_cada * int(n)` cai num
`st.error` e **não cadastra**. É bloqueio, não aviso: o caso real dele não
entra no Studio de jeito nenhum.

E os dados dele já provam que o caso existe: na carteira importada há cheque
com Estoque **R$ −629,91** — envio maior que o valor, gravado, vindo da
planilha dele.

### O conserto

Vira aviso, não bloqueio: o Studio diz o que notou e cadastra assim mesmo.

**Falta uma decisão dele, que não vou chutar:** quando o envio passa do valor
dos cheques, o `estoque` (= valor − envio, `cheques.py`) fica **negativo** ou
**zero**? Negativo diz "esta compra tinha mais envio do que este cheque
cobre"; zero diz "este cheque é todo envio". Os dois são defensáveis e mudam a
previsão de caixa, que é para isso que a divisão existe.

---

## ~~O `$` do real virando fórmula de LaTeX~~ — FEITO em 21/09 (`rotulos.tela`)

Na mesma tela: o aviso saiu como
`O envio (R2.300,00)émaiorqueacompra(R 1.814,20)` — sem os cifrões, tudo
grudado e em itálico. O markdown do Streamlit leu `$…$` como matemática.

**Dois `R$` no mesmo texto de tela = fórmula.** Já foi resolvido em quatro
lugares com `R\$` (`app.py:1490`, `financeiro.py:276`, `:295`, `:302`) e em
nenhum outro — a correção ficou num caminho só, de novo.

**E a varredura por AST não acha o resto.** Onde o `R$` vem de um helper
(`_brl`, `formatar_br`), o literal não está na chamada: `cheques_tela.py:234`
passou limpo pela peneira e é exatamente o caso que quebrou na tela. Escapar
call site por call site não fecha a classe — o próximo `_brl` novo reabre.

**O conserto certo é um lugar só:** um `texto_de_tela(s)` que escapa `$` antes
de entregar ao `st.*`, e as telas passam a usá-lo em vez de escapar na mão.
`_brl` continua devolvendo `R$` puro — ele também alimenta tabela e HTML, onde
a barra invertida apareceria escrita.

---

## Transferência entre contas: achar o par sozinho  ·  21/09/2026

Em stand-by — havia gente no Studio. **Sobe com a próxima autorização.**

### O que ele pediu

> "eu transfiro dinheiro entre as contas, logo, aparecerá saída de uma conta e
> entrada na outra através dos extratos… o sistema deve cruzar as informações
> do dia e hora da movimentação e saber que realoquei o valor… o valor de
> movimentação não deve entrar como custo ou gasto"

### Metade já existe

`favorecidos.NAO_CONSOME_META` (`favorecidos.py:252`) já tem
`TRANSFERENCIA ENTRE CONTAS` e `TRANSFERENCIA`, e `NAO_E_FATURAMENTO`
(`favorecidos.py:258`) também. **Uma vez classificada, a transferência já fica
de fora do gasto do mês E do faturamento.** O comentário lá diz exatamente o
motivo: *"dinheiro indo de uma conta nossa para outra não é despesa: contá-lo
dobraria o gasto do mês"*.

O que falta é o **reconhecimento automático**. Hoje alguém tem que classificar
o favorecido como TRANSFERENCIA; enquanto não classifica, a saída conta como
gasto.

### O que construir

Um casamento entre contas, na importação do extrato — mesmo lugar onde a baixa
dos cheques já entra. O par é:

| | |
|---|---|
| Sinais opostos | uma saída e uma entrada |
| **Contas diferentes** | `lancamentos.py:36` guarda `conta` em cada linha |
| Valor idêntico | ao centavo |
| Data igual, ou ±1 dia | TED enviada às 17h cai no dia seguinte |

Achado o par, as DUAS linhas recebem `finalidade = "TRANSFERENCIA ENTRE
CONTAS"`, e o resto do Studio já sabe o que fazer com isso.

### A HORA NÃO EXISTE — e ele pediu por ela

Ele disse "dia e hora". **O extrato não traz hora**: `lancamentos.COLUNAS`
(`lancamentos.py:36`) guarda `data`, e nem o leitor do Inter nem o do Itaú
extraem horário. Cruzar por hora não é possível sem mudar a fonte.

Na prática não faz falta — valor idêntico, sinais opostos e contas diferentes
no mesmo dia já é um par quase inequívoco. Mas **ele precisa saber que a regra
é essa**, e não a que pediu.

### O estrago a mapear (Regra 3)

Marcar transferência errada tira do gasto do mês um valor que FOI gasto — e o
número fica menor do que a realidade, que é o erro mais caro que existe aqui:
ninguém desconfia de um gasto menor.

O caso que gera falso par: uma venda entrando numa conta no mesmo dia e no
mesmo valor de uma despesa saindo da outra. É raro, não é impossível.

**Por isso, a mesma regra da baixa dos cheques:** par único e sem ambiguidade
entra sozinho; havendo mais de um candidato para a mesma linha, o Studio
mostra e pergunta, em vez de escolher.

### Onde entra

`extratos_tela.py`, logo depois de `_lan.gravar`, ao lado da baixa dos cheques
— o extrato acabou de chegar e é ali que ele tem o que dizer. E precisa olhar
os lançamentos JÁ GRAVADOS, não só os do arquivo: a outra perna da
transferência costuma vir no extrato da outra conta, importado em outro
momento.
