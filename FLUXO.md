# Quem é dono de cada dado — Studio ou Excel

Definido pelo dono em 17/09/2026. Uma aba tem UM dono: o lugar onde o dado é
digitado. O outro lado, quando existe, é consulta.

## Passa para o Studio

| O quê | Situação |
|---|---|
| Custo fixo | Digitado no Studio. O Excel vira consulta |
| Salários / folha | Digitado no Studio |
| Não operacionais | Digitado no Studio |
| Cheques | Preenchimento e baixa passam para o Studio |
| Devoluções | Passa para o Studio |

## Continua no Excel

| Aba | Por quê |
|---|---|
| SAIDAS PIX-BOLETO 2026 | O extrato traz gastos que já entram como custo fixo; jogar direto contabilizaria duas vezes |
| CARTÕES | O que é debitado ali precisa ser analisado e realocado — mercadoria, ADS, custo fixo (Hostgator) |
| ADS E CROSS | Nem tudo ali é ADS: tem transporte até o Full, taxa de página ativa, selo de loja oficial (R$ 99) |
| SIMPLES - FLEX | Simples cai no extrato; Flex é pago por DDA |
| AJUSTE DE PLANILHA | É o preparo da base antes de virar BASE DE VENDAS |
| PREÇO DE CUSTO | Renan consolida SKU ali. **Não deve ser considerado pelo Studio** |
| BASE DE VENDAS 2026 | A base fica no Excel; o Studio lê para os indicadores |
| MINHAS DINÂMICAS / DINÂMICA | Ficam no Excel; o Studio mostra algumas |

## Depende de coisa que ainda não existe

| O quê | O que falta |
|---|---|
| A RECEBER | Integração com as plataformas. Dinheiro libera e provisiona a cada venda — sem integração, nenhum número fica atualizado |
| DASH | O Studio mostra, quando o resto estiver rodando |
| FATURAMENTO CONSOLIDADO | Indicadores mais para frente |

---

## Custo fixo: provisionado no Studio, conferido pelo extrato

**Decidido pelo dono em 17/09.** Nem A nem B — as duas fontes existem, com
papéis diferentes:

| Fonte | Papel |
|---|---|
| Studio | **Provisiona.** O custo fixo do mês existe no dia 1º, antes de ser pago |
| Extrato / fatura | **Confere.** Quando o débito aparece, o Studio o liga ao item provisionado |

Quando o valor pago diverge do provisionado, ajusta-se o valor **daquele mês**
— e o provisionado dos meses seguintes continua como está, até alguém mudá-lo.

O que isto resolve: o custo fixo continua previsto (dá para planejar o mês) e
para de ser chute (o que foi pago manda no que ficou registrado). E o extrato
deixa de ser uma segunda fonte de gasto — ele confere, não soma.

**A regra que impede a conta dobrada:** linha de extrato ligada a um item de
custo fixo NÃO entra de novo como gasto. Ela atualiza o item.
