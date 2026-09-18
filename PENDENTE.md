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
