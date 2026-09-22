# Os cards da imagem viram camada de texto  ·  proposta, 22/09/2026

> **Nada disto foi aplicado.** Está escrito antes de mexer, como o dono pediu:
> *"tome cuidado para não prejudicar outra coisa, o objetivo aqui é a qualidade
> do serviço."*

---

## 1. O que aconteceu, medido

Um produto — meia "Pé de Galinha", 8 imagens — consumiu **cerca de 41 disparos
de geração**, contados na conversa entre a colaboradora e o Assistente. Como
cada disparo pode repetir (aparece "na 2ª tentativa" várias vezes) e cada
imagem gerada ainda passa pela conferência no Opus 5 (`imagem.py:2685`), o
número real de chamadas pagas é maior que 41.

Isso é o custo. Mas o custo é sintoma: o que essas 41 rodadas significam é que
a colaboradora passou uma tarde pedindo a mesma coisa várias vezes.

### As quatro causas, e quanto cada uma custou

| # | Causa | Rodadas |
|---|-------|---------|
| 1 | A cor do produto estava errada (amarelo, e é laranja) | ~18 |
| 2 | Todo ajuste re-renderiza a imagem inteira e quebra o enquadramento | quase todas |
| 3 | Ela não consegue subir foto de referência pelo chat | ~6 |
| 4 | O gerador escreve texto errado e não conserta | desiste em 2 |

### Causa 1 — um campo errado, dezoito gerações

A conversa vira quando ela escreve *"chat as meias não sao amarela e sim
laranja"*. Dali em diante são dezoito disparos só para trocar uma cor em oito
imagens, e ainda assim três falharam e viraram "refazer do zero".

A cor não foi descoberta pela IA: ela estava errada na origem, e só apareceu
quando as oito imagens já existiam.

### Causa 2 — a correção quebra o que estava certo

Esta é a que fabrica as outras. **Todo** resultado bem-sucedido do log traz a
mesma observação:

> ⚠️ Mudou também, sem ter sido pedido: o enquadramento ficou levemente
> ampliado/deslocado…

Trocar o texto de um card move a meia. Tirar uma rodela de laranja recompõe a
cena inteira e faz o texto perder a linha de posicionamento. A pessoa então
pede para consertar o que a correção quebrou — e esse pedido quebra outra
coisa. O laço se alimenta sozinho.

O diagnóstico do Studio já enxergava isso: a conferência foi construída
justamente para responder *"mudou mais do que eu pedi?"* (`imagem.py:2680`).
Ela detecta o problema toda vez. Detectar não resolve.

### Causa 3 — falta uma capacidade, e isso precisa ser dito

Quatro vezes ela escreve alguma variação de *"vou te mandar uma foto
referencia pq voce nao deixa eu enviar"*. Numa delas o Assistente respondeu
**descrevendo um layout que nunca viu**, refez a imagem 6 em cima dele, e
depois admitiu: *"Erro meu — eu não consigo ver imagem enviada aqui no chat."*

Uma geração inteira jogada fora, mais as seguintes para desfazer.

### Causa 4 — o gerador não sabe escrever

Na imagem 7 o resultado saiu com *"Cerne o presento"*, *"compunorso supposto"*
e *"meta de galinha"*. O Studio tentou corrigir duas vezes e parou, marcando
"não publique assim" — que é o comportamento certo, e ainda assim é uma imagem
perdida depois de três gerações.

---

## 2. A proposta

### O que muda

Os cards de informação — **ALTURA: 40 cm**, **CORES: Branco, Laranja, Preto**,
**Tamanho: do 38 ao 43** — deixam de ser desenhados pelo modelo de imagem e
passam a ser **compostos pelo Studio por cima da foto gerada**, como camada de
texto.

A IA continua fazendo o que faz bem: a foto do produto e a ambientação.

### Por que isso resolve três das quatro causas

| Causa | Depois |
|-------|--------|
| 1 — cor errada | Card lê o cadastro. Corrigir o campo corrige as 8 imagens, sem gerar nenhuma |
| 2 — reenquadramento | Trocar texto de card não chama o gerador. **Zero** gerações, e a foto não é tocada |
| 4 — erro de português | Texto desenhado por fonte não erra. Nunca |

A causa 3 (referência no chat) é independente e mais barata: é deixar a aba de
upload disponível de dentro do chat.

### O que NÃO muda, e é o ponto de atenção do dono

- O visual precisa ficar **igual ou melhor**. Card desenhado por código tende a
  ficar mais limpo que card desenhado por IA — tipografia consistente, alinhamento
  exato, sem letra torta —, mas isso tem que ser **visto** antes de valer.
- A ambientação, a luz e o enquadramento continuam sendo da IA. Nada do que foi
  feito na direção de arte (PR #149) é desfeito.
- As 8 imagens atuais de cada produto continuam existindo do mesmo jeito.

---

## 3. Riscos, mapeados antes e não depois

| Risco | Como fica coberto |
|-------|-------------------|
| O card tapar o produto | A posição sai do diagnóstico de enquadramento que já existe (`diagnostico["enquadramento"]`). Card vai para a área vazia, não sobre a peça |
| Ficar com cara de adesivo colado | O card herda a paleta detectada da própria foto, não uma cor fixa — a mesma decisão que tirou o azul obrigatório do padrão visual |
| Imagem que não tem card nenhum | Nada muda: sem dado de card, a foto sai como sai hoje |
| Voltar atrás | A composição é uma etapa a mais no fim do fluxo. Desligá-la devolve o comportamento atual sem tocar em nada do que existe |
| Quebrar a geração atual | A camada roda DEPOIS da imagem pronta. Se ela falhar, a foto continua válida — falha de card nunca pode derrubar a geração |

---

## 4. Ordem sugerida

1. **Corrigir a cor no cadastro antes de gerar** — barato, e teria evitado 18
   das 41 rodadas deste produto sozinho.
2. **Referência no chat** — tira o caso em que o Assistente descreve o que não
   viu.
3. **Cards como camada** — o trabalho maior, e o que fecha o laço.

Os três são independentes. Nenhum precisa do outro para valer.

---

## 5. O que ainda não sei

- **Quanto custa hoje uma foto.** O `log_imagem.py` guarda o que foi pedido,
  não os tokens. A resposta da API traz `usage.input_tokens`; gravá-lo no log
  transforma "está caro" em número. Uma semana de uso basta.
- **Se a colaboradora prefere o card composto.** Isso se decide olhando, não
  argumentando. Dá para gerar as duas versões do mesmo produto e comparar antes
  de trocar qualquer coisa.
