# Pesquisa local — Hill-Climbing (Alexandre Silva)

Parte do Alexandre, numa pasta à parte, para juntar no fim ao trabalho do grupo. **Não altera nenhum ficheiro dos colegas.**

| Ficheiro | Conteúdo |
|---|---|
| `local.py` | Representação por visitas, vizinhos (trocar / mover / inverter, mais o extra *mover bloco*), avaliação pelo `verificar_viabilidade`, Hill-Climbing (melhor vizinho e primeira melhoria), Simulated Annealing (extra) e plano com os dias 30 e 31 encadeados |
| `03_pesquisa_local.ipynb` | Notebook com as experiências e as **curvas de custo × iteração** (tiny e small) |
| `DOCUMENTACAO.md` | Explicação completa, exemplo passo a passo, resultados e perguntas da defesa |

**Para correr:** abrir `03_pesquisa_local.ipynb` dentro desta pasta e executar tudo (cerca de 2 minutos).

O notebook precisa de duas coisas fora desta pasta:
- o `model.py` da raiz do repositório;
- a pasta `../pesquisa_informada/`, que fornece a solução inicial do Greedy. Quando o `pesquisa.py` do Fábio estiver pronto, basta mudar a função `solucao_greedy()`.

**Resultados:**
- **Tiny:** chega ao ótimo do A* (601,97 km).
- **Small:** chega ao ótimo do A* (879,45 km) em 10 de 10 tentativas com *mover bloco*, contra 1 de 10 só com os três movimentos base.
