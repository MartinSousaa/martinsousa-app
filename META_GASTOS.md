# Meta de gastos — as regras, decididas pelo dono

Fechado em 17/09/2026, na conversa. Escrito aqui porque regra combinada em
chat morre com o chat — e esta decide número que vai para a tela.

## A régua é o CAIXA

O cartão é olhado como **gasto consolidado**, não compra a compra. Ele tem
finalidades, mas não deixa de ser dinheiro saindo, e é isso que consome a meta.

Por isso a meta de gastos mede o que sai do banco no mês — não o que a compra
custou no papel.

## Estorno abate no mês em que cai, integral

Plataforma reembolsa o valor cheio do produto de uma vez, e as parcelas
continuam sendo cobradas nos meses seguintes. Exemplo do dono:

> Dois produtos de R$ 500 em 10×. Aparece como 10 parcelas de R$ 100.
> Devolvo um: caem R$ 500 de uma vez, e as 10 parcelas de R$ 100 continuam.

O estorno entra **inteiro** no mês em que caiu, na **finalidade da compra
original**. As parcelas seguem consumindo a cota dos meses seguintes.

Se em setembro a finalidade "Outros" tem R$ 2.500 e cai um estorno de R$ 500
de uma compra "Outros", setembro fecha em R$ 2.000.

## Indicador pode ficar negativo, e fica

Quando o estorno é maior que o gasto daquela finalidade no mês, o indicador
mostra **negativo**. Decisão do dono, com o motivo dele: entende-se que houve
valores daquela modalidade acima da fatia de consumo do mês.

Travar em zero esconderia dinheiro que voltou — e número que esconde é pior
que número feio.

## O que isto NÃO é

Não é o custo do item. O produto devolvido custou zero, e isso continua
verdade — mas essa conta não é a da meta de gastos, e as duas não devem ser
somadas na mesma tela.

## O que ainda depende de decisão

O custo fixo é digitado no Studio e o mesmo gasto aparece no extrato. Enquanto
não se escolher qual das duas fontes manda (ver `FLUXO.md`), a meta de gastos
corre risco de contar o mesmo dinheiro duas vezes.

---

## A meta acompanha o faturamento — só pela mercadoria

Decidido em 17/09/2026.

A meta de gastos é feita para o faturamento do **ponto de equilíbrio**. Vendendo
acima dele, é preciso comprar mais mercadoria para sustentar a venda, e cobrar a
mesma meta puniria justamente o mês bom.

    faturamento excedente = faturamento − ponto de equilíbrio
    folga                 = excedente × CMV
    meta do mês           = meta base + folga

Exemplo do dono: meta 150k, equilíbrio 240k, faturou 300k. Com CMV de 35%, os
60k a mais liberam 21k de mercadoria, e a meta do mês vira 171k.

### A folga é só de mercadoria

> "O que não pode é aumentar o faturamento e nos gastos aumentar o 'outros'."

Por isso existem dois tetos, e não um:

| Teto | Vale para | Cresce com o faturamento? |
|---|---|---|
| Flexível | Mercadoria | **Sim** |
| Rígido | Todo o resto | **Não** — é a meta base menos a mercadoria que ela já previa |

O teto do rígido é **fixo**, e de propósito. Se ele fosse "o que sobrou da
mercadoria", comprar menos para vender passaria a liberar gasto em "outros" —
o contrário do que a meta existe para fazer.

### O que ainda falta

O **CMV** — quanto de cada real vendido vira mercadoria. Ou o gestor digita, ou
sai da razão medida entre mercadoria e faturamento do mês. Enquanto não houver
um, a meta não cresce: liberar gasto por um número que ninguém configurou é o
tipo de erro que só aparece no fim do mês.
