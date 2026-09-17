# O que o Studio chama de ociosidade

Mapeamento feito em 17/09/2026, a pedido do dono, depois de uma colaboradora
relatar que estava com demanda EM ANDAMENTO e viu a ociosidade dela subir.

Cada afirmação aqui tem o `arquivo:linha` que a sustenta. Nada foi escrito de
memória.

---

## A conta, em uma linha

> **Ociosidade = tempo dentro do expediente batido no relógio em que NENHUM
> cartão seu estava rodando** — menos as folgas, menos a hora pessoal, menos o
> que foi abonado.

Ela nunca sai do nada: precisa de duas listas — a do relógio de ponto e a do
Trello — e o que sobra entre uma e outra é o ocioso.
`placar_core.ociosidade_do_dia` (`placar_core.py:1880`).

---

## 1. O denominador: de onde saem as horas

| O que entra | Onde |
|---|---|
| As janelas do dia vêm do **relógio de ponto**, não do contrato: entrada → saída para o almoço, volta → saída | `batidas.janelas_do_dia` |
| Quem **não bate ponto** cai no horário contratual | `batidas.py`, decisão 1 |
| Quem entrou e **ainda não saiu** conta até agora | `batidas.py`, decisão 2 |
| O almoço real **não existe** para a conta — nem como trabalho, nem como ociosidade | `batidas.py:105` |
| Acima de **7 horas por dia**, nada conta: nem trabalho nem ociosidade | `placar_core.TETO_DIA_MIN` (`placar_core.py:471`) |
| Dia sem expediente (feriado, fim de semana) não tem janela | `placar_core.eh_dia_util` |

## 2. O numerador: o que conta como "você estava trabalhando"

Um cartão está rodando quando tem **etiqueta de trabalho E nenhuma etiqueta de
interrupção** — `placar_core.py:1276`.

| Etiqueta | Conta como trabalho? |
|---|---|
| EM ANDAMENTO | ✅ sim |
| FILMAGEM | ✅ sim |
| INTERROMPIDO | ❌ para o relógio |
| INTERROMPIDO MS | ❌ para o relógio |
| FIM DE EXPEDIENTE | ❌ para o relógio |
| PENDENTE | ⚠️ **conta como trabalho** — ver a divergência no fim |

E **conta para quem está no cartão**: o trecho vai para os membros anexados
naquele trecho, não para quem entrou depois (`placar_core.py:1637`).
Exceção única: na coluna **Análise de Demandas**, todo mundo que está no
cartão agora recebe o trecho inteiro (`placar_core.py:1633`).

## 3. As tolerâncias — o que o sistema perdoa

| Folga | Quanto | Onde |
|---|---|---|
| Do bater o ponto até abrir o primeiro cartão | **10 min** | `GRACA_INICIO_MIN` (`placar_core.py:1579`) |
| Entre um cartão e o seguinte | **5 min**, em cada troca | `GRACA_ENTRE_MIN` (`placar_core.py:1580`) |
| Pausa pessoal | **60 min por dia**, tirados dos dois lados da conta | `PAUSA_PESSOAL_MIN` (`placar_core.py:1584`) |
| Parada da equipe (queda de internet, reunião) | o que for lançado | Ponto › Abonos |
| Abatimento aprovado para a pessoa | o que for aprovado | Ponto › Abonos |
| Hora abonada na RHiD | sai do ocioso **e** do total | `relogio_ponto.py:1103` |

A pausa e o abono saem **dos dois lados** de propósito: tirar só do ocioso
faria o percentual cair duas vezes pela mesma hora.

## 4. A meta

10% no normal, 5% na MAXX — `explicacao_metas.py:49`.
10% de 154h (22 dias de 7h) são 15h24 no mês.

---

## O caso relatado: cartão EM ANDAMENTO e ociosidade subindo

As causas possíveis, em ordem do que acontece mais:

1. **Ela não estava anexada ao cartão** naquele trecho. O cartão roda, o tempo
   é medido — e vai para quem está nele. Quem foi marcado depois não recebe o
   que passou antes (`placar_core.py:1637`).
2. **O cartão tinha também uma etiqueta de interrupção.** EM ANDAMENTO +
   INTERROMPIDO, ou + FIM DE EXPEDIENTE, é relógio parado (`placar_core.py:1276`).
   O FIM DE EXPEDIENTE entra sozinho depois das 19h e fica lá até alguém tirar.
3. **O painel estava atrasado.** As ações do Trello ficam em cache por 5
   minutos (`_CACHE_VALIDADE_S`, `placar_core.py:520`) e o board por 30
   segundos. Ociosidade "ao vivo" pode estar até 5 minutos atrás do Trello.
4. **Ela trabalhou de verdade sem cartão aberto** — e aí o número está certo,
   e o problema é de processo, não de sistema.

**Como saber qual foi**, sem adivinhar: abrir o cartão no Trello e olhar o
histórico — quando a etiqueta entrou, quando ela foi marcada como membro, e se
alguma etiqueta de interrupção esteve lá no meio.

---

## Uma divergência encontrada durante o mapeamento

O texto que a equipe lê diz:

> "Cartão **INTERROMPIDO** ou **PENDENTE** não conta como atividade."
> — `explicacao_metas.py:228`

Mas `PENDENTE` **não está** em `LABELS_INTERRUPCAO` (`placar_core.py:432`).
Na prática, cartão com EM ANDAMENTO + PENDENTE continua contando como
trabalho.

A divergência é **a favor da equipe** (conta tempo que o texto diz que não
contaria), então não explica o caso relatado. Mas são duas respostas para a
mesma pergunta, e elas vão discordar de novo — a questão é só quando. Precisa
de uma decisão: ou PENDENTE entra na lista de interrupção, ou o texto muda.
