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
