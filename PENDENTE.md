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

```
ID do arquivo: 1d82vJONqMXkcPPYQqLwXk1C7KJuUh-st
```

Abas que existem: SAIDAS PIX-BOLETO 2026 · CARTÕES · ADS E CROSS ·
SIMPLES - FLEX · CHEQUES · DEVOLUÇÕES 2026 · DIN FINANÇAS · DINAMICA ·
DASH 2026 · AJUSTE DE PLANILHA · PREÇO DE CUSTO. · BASE DE VENDAS (e mais,
cortadas na tela).

**O que falta dele:** dizer quais abas o Studio deve ler.

**O que falta de mim:** leitor de `.xlsx` no Studio — download via Drive API
(`gdrive.py` ainda não tem função de download) e leitura com pandas, que exige
`openpyxl` no requirements. Cache por TTL: o arquivo inteiro desce a cada
leitura fria.

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
