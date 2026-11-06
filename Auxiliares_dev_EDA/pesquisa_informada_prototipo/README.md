# Pesquisa informada — protótipo (UCS, Greedy e A*)

> **Nota:** na divisão final do grupo, a pesquisa informada é do **Fábio**. Esta pasta é um protótipo feito pelo Alexandre. Serve para gerar a **solução inicial do Greedy** usada pela pesquisa local (`../pesquisa_local/`) e como referência para comparar resultados (o ótimo do A*). Quando o `pesquisa.py` do Fábio estiver pronto, o grupo decide se esta pasta fica como referência ou se é retirada.

**Não altera nenhum ficheiro do grupo.** Usa o `model.py` da raiz tal como está.

## Ficheiros

| Ficheiro | Conteúdo |
|---|---|
| `heuristicas.py` | **H1 — pedido mais caro** e **H2 — árvore geradora mínima (MST)**, as heurísticas oficiais. Inclui também as de referência: "mais distante" (ideia do Fábio, adaptada ao dia) e `max(H1, H2)`. |
| `pesquisa.py` | Subproblema (um veículo num dia), sucessores, objetivo, UCS / Greedy / A* com contagem de nós, validação com `verificar_viabilidade`, teste de admissibilidade, atribuição das encomendas aos veículos e plano completo. |
| `02_pesquisa_informada.ipynb` | Notebook documentado: modelação, heurísticas, testes, resultados do tiny e do small, rotas, mapas, análise crítica e conclusão. |

## Como correr

Abrir `02_pesquisa_informada.ipynb` **dentro desta pasta** e executar todas as células. Demora cerca de 2 minutos, quase tudo na atribuição do small. Os dados são lidos de `../docs/`.

## Resultados principais

| | UCS (ótimo) | A* H1 | A* H2 | Greedy H1 | Greedy H2 |
|---|---|---|---|---|---|
| **Tiny** — km | 601,97 | 601,97 | 601,97 | 609,59 | 609,59 |
| **Tiny** — nós expandidos | 610 | 429 | 536 | 311 | 179 |
| **Small** — km | 879,45 | 879,45 | 879,45 | 880,53 | 940,42 |
| **Small** — nós expandidos | 7256 | 6691 | 6918 | 2050 | 957 |

- O A* com qualquer heurística dá o mesmo que o UCS. As heurísticas nunca sobrestimaram no teste estado a estado.
- **H1 é a mais informada e a que mais poupa nós.**
- **Todas as rotas foram confirmadas pelo `verificar_viabilidade`.**
- **Small:** com a regra "cada encomenda do próprio dia é feita por um só veículo" não há solução completa. Está provado no notebook: nenhuma das 256 divisões das encomendas do dia 30 é viável. Por isso a encomenda 9 fica de fora.

## Decisões a confirmar com o grupo

1. O problema é dividido por **veículo e dia**. O que passa a noite no armazém pode ser entregue no dia seguinte pelo outro veículo.
2. As encomendas são atribuídas aos veículos **antes** da pesquisa, por inserção mais barata. Este pode ser um bom ponto de ligação com o CSP e o Hill-Climbing.
3. A `h_mais_distante` do `model.py` assume que todos os itens são entregues hoje. Aqui foi adaptada para os itens que só são entregues amanhã. Se fosse usada sem adaptação, sobrestimaria nesses casos.
