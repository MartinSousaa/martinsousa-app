# ACHADOS ABERTOS — o que foi mapeado e ainda NÃO foi corrigido

Este arquivo é lido por `checar_alcance.py`, e **reprova a conferência**
enquanto houver item aberto sem motivo escrito.

## POR QUE ELE EXISTE

30/09. Varri a cadeia Studio → Gemini, achei treze defeitos, escrevi todos
numa lista minha, corrigi onze e **deixei dois**. Um deles — `_tem_fotos`
decidindo o texto do prompt pela chave da OpenAI — é uma das causas de
"produto nada a ver com o original", e ficou aberto por horas enquanto eu
relatava "APROVADO".

O dono perguntou: *"como me garante que não há outros erros que mapeou e não
tratou?"*. A resposta honesta é que eu não garanto por promessa. Os oito
verificadores guardam o CÓDIGO; nada guardava a minha LISTA. Achado anotado
num bilhete depende de eu lembrar — e à mão eu não faço igual duas vezes.

Então a lista deixa de ser bilhete e passa a ser trava, igual ao que esta
base já faz com as isenções (`MUDAS_POR_ESCOLHA`, `THREADS_SEM_TELA`): ou o
item é corrigido e sai daqui, ou fica com MOTIVO escrito de por que não foi.

## COMO USAR

Item aberto tem três linhas obrigatórias:

    ### <título curto>
    ONDE: arquivo:linha
    POR QUE AINDA NÃO: <motivo, com todas as letras>

Sem a linha `POR QUE AINDA NÃO`, a conferência reprova. "Esqueci" não é
motivo — mas é uma resposta honesta, e escrita ela para de ser esquecimento.

## ABERTOS

### Por que as oito peças do «Compasso Cortador Colorido» saíram erradas
ONDE: toda a cadeia · evidência em `log_imagem.py` (contexto do log)
POR QUE AINDA NÃO: a análise do dia 30/09 foi feita em cima do `.txt` do
histórico que o dono baixou, e aquele arquivo **misturava as rodadas de duas
pessoas** — o contexto do log era um global de processo, então o histórico de
um produto veio com peças de outro dentro, carimbadas com o nome de quem não
as gerou. O global foi corrigido (contexto por thread, com herança na criação
da thread), mas o log ANTIGO não se conserta: as linhas já gravadas continuam
com produto e usuário errados. A pergunta original — por que as peças dele
saíram com moldura, texto cortado e produto fora de escala — precisa ser
refeita com um histórico novo, gerado depois desta correção. Dito em voz alta
em vez de escondido: **eu afirmei que o plano estava misturado entre dois
produtos, e essa afirmação não se sustenta.** Ela saiu do log corrompido.

### A trava do plano misturado ficou pronta e foi retirada
ONDE: imagem.py:576 (`plano_misturado`) e o painel de confirmação
POR QUE AINDA NÃO: a função fica, e o aviso também — com um plano coerente ela
devolve `""` e não custa nada. O que saiu foi a TRAVA do botão Confirmar:
trancar a geração com base num defeito que eu não consigo mais provar é alarme
falso, e alarme falso ensina a desviar do alarme verdadeiro junto. A trava
volta no dia em que um plano real vier misturado.


### Com FOTOS, uma conta sem `gpt-image-*` continua caindo no reserva
ONDE: imagem.py:_chamar_openai_geracao
POR QUE AINDA NÃO: o caminho SEM fotos passou a funcionar com `dall-e-3` em
01/10 — a chamada agora lê na resposta de erro qual parâmetro o modelo recusou
e repete sem ele, em vez de mandar o que só a família `gpt-image-*` aceita.
O que continua aberto é o caso COM fotos: as três tentativas da OpenAI usam a
Responses API com `tools=[image_generation]` e `images.edit`, e o `dall-e-3`
não atende por ali nem aceita foto de referência. Com fotos ele falharia nas
três e cairia no Gemini do mesmo jeito — e o Gemini não aceita
`input_fidelity=high`, que é o que preserva o produto.

Isto NÃO tem conserto por código: nenhuma chamada faz um modelo aceitar foto
de referência que ele não aceita. A saída é a conta ter um `gpt-image-*`.
Enquanto não tiver, a régua de parecença (`medir_imagem.produto_diferente`)
reprova a peça repintada e manda refazer — é compensação, não conserto.

### A régua GEOMÉTRICA não vê a forma — mas a conferência de visão vê
ONDE: medir_imagem.py:produto_diferente e imagem.py:conferir_peca
POR QUE AINDA NÃO: corrijo aqui uma afirmação minha que estava incompleta e
assustava mais do que devia. A régua geométrica compara COR, e de fato não vê
forma. Mas ela não é a única conferência: `conferir_peca` olha a peça com
visão, lado a lado com as fotos do produto, e já pergunta pelo número de
alças, formato, acabamento, componentes e cor — e ela JÁ RODA em toda peça de
toda geração, pela porta única `revisar_tudo`.

O que falta de verdade é mais estreito: a conferência de visão depende da
ANTHROPIC_API_KEY e das fotos; sem uma das duas ela não roda e diz isso, e aí
só a régua de cor sobra. Nesse caso, produto da cor certa e formato errado
passa. Medir forma geometricamente não serve: testei preenchimento da caixa e
proporção, e a variação entre ângulos do MESMO produto (26 a 53 pontos) é
maior que a variação entre produtos DIFERENTES (5 pontos no pior caso).
Qualquer limite ou deixa passar a troca ou acusa o inocente.

### `_processar` duplicado: travado, ainda não unificado
ONDE: placar.py:_processar e placar_core.py:_processar
POR QUE AINDA NÃO: as duas estão VIVAS, em telas diferentes — o Painel de
Metas chama a do core, o Placar e mais quatro telas chamam a do placar. Elas já
discordaram em 330 pontos. Medido em 01/10: hoje concordam nas 25 chaves em
comum, em 18 cenários (450 comparações), e há guarda que reprova se voltarem a
discordar — então o estrago silencioso acabou.

A unificação de verdade não foi feita, e o motivo é medido: a do core é
superconjunto da do placar menos três chaves (`cards_pts`, `pausados_lista`,
`sem_membro_lista`), mas ela faz consultas EXTRAS ao Trello (ações do board,
movimentação, criadores de cartão) que o Placar hoje não paga. Fazer o placar
delegar deixaria a tela mais lenta — que é exatamente como uma tela desta base
já levou 15 segundos para abrir. O caminho certo é extrair o LAÇO COMUM para
uma função que as duas chamem, sem arrastar os extras junto; é mudança grande
na tela que decide bônus, e ela merece ser feita com o dono sabendo.

