# CSP — atribuição de encomendas a veículos

Esta pasta contém a implementação independente da parte CSP do trabalho. O
módulo atribui encomendas completas a veículos, constrói os domínios a partir
das restrições disponíveis e disponibiliza `python-constraint` e um
backtracking próprio com e sem MRV.

## Cobertura dos objetivos

| Objetivo | Estado | Como está tratado |
|---|---|---|
| Variáveis e domínios | Coberto | Uma variável por encomenda completa; o domínio contém os veículos elegíveis. |
| Capacidade | Coberto com dois modos | `single_load` limita o peso total atribuído; `multi_trip` verifica se cada encomenda cabe numa viagem. |
| Janelas temporais | Parcial | Cada encomenda é verificada isoladamente. Ainda não se verificam conflitos de horário entre encomendas atribuídas ao mesmo veículo. |
| Compatibilidade veículo/produto | Parcial | Há suporte para `requires_refrigeration`, mas os CSV atuais não declaram esse requisito por produto. |
| Resolução com `python-constraint` | Coberto | Enumera atribuições e seleciona a mais equilibrada entre as soluções consideradas. |
| Restrição suave / heurística | Coberto | O balanceamento da carga ordena as escolhas; não invalida uma solução válida por estar desequilibrada. |
| Backtracking com e sem MRV | Coberto | Os dois métodos devolvem nós e backtracks. Nos dados atuais, ambos chegam à primeira solução sem backtracks. |
| Atribuição viável | Coberto ao nível da atribuição | A solução respeita o modo de capacidade escolhido e os filtros individuais; ainda deve passar pelo planeador e verificador de rotas. |

O detalhe da formulação, das funções, da interpretação dos resultados e dos
limites está em [documentacao.md](documentacao.md). O notebook
[`01_csp.ipynb`](01_csp.ipynb) acompanha a apresentação e comparação dos
métodos.

## Executar

Na raiz do repositório:

```bash
pip install -r requirements.txt
jupyter notebook csp/01_csp.ipynb
```

## API rápida

```python
from model import Problem
from csp.csp import FleetCSP, compare_backtracking

problem = Problem("docs/data_tiny")
csp = FleetCSP(problem)

resultado = csp.solve_python_constraint(capacity_mode="single_load")
comparacao = compare_backtracking(csp, capacity_mode="single_load")
```

Use `capacity_mode="multi_trip"` para permitir que um veículo receba mais
peso no total do que a sua capacidade, desde que cada encomenda caiba numa
viagem, como no modelo de rotas atual.
