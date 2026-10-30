# IA26_P01_G02

Repositório do 1º Trabalho Prático de **Inteligência Artificial** (2026/27) — Licenciatura em Engenharia de Sistemas Informáticos, IPCA.

**Tema:** Local food — agente de routing de recolha e entrega para uma plataforma que liga pequenos produtores locais, clientes e centros de recolha no distrito de Braga.

## Grupo 02

| Nome | Nº de aluno |
|---|---|
| André Rodrigues | 26900 |
| Tiago Gonçalves | 29389 |
| Fábio Ferreira | 29365 |
| Alexandre Silva | 29382 |

## Objetivo

Desenvolver um agente inteligente que encontre rotas de recolha (produtores) e entrega (locais escolhidos pelos clientes) eficientes e viáveis, respeitando janelas temporais e a capacidade dos veículos. Técnicas aplicadas:

- **Pesquisa informada** — Greedy Best-First e A\* com duas heurísticas; UCS para validar a solução ótima;
- **CSP** — janelas temporais e capacidade como restrições (`python-constraint`);
- **Pesquisa local** (extra) — Hill-Climbing sobre a solução Greedy.

## Estado do projeto

| Fase | Estado |
|---|---|
| 1. Introdução e EDA (load e *parsing* do dataset em memória) | ✅ Concluída — `01_eda_tiny.ipynb` e `01_eda_small.ipynb` |
| 2. Modelação (`model.py`) | ⏳ Por fazer |
| 3. Pesquisa informada (Greedy, A\*, UCS) | ⏳ Por fazer |
| 4. CSP (`python-constraint`) | ⏳ Por fazer |
| 5. Pesquisa local (extra) | ⏳ Por fazer |
| 6. Análise de resultados e conclusão | ⏳ Por fazer |

## Estrutura

```
├── 01_eda_tiny.ipynb               # Introdução e análise exploratória (EDA) do conjunto tiny
├── 01_eda_small.ipynb              # A mesma análise para o conjunto small (só muda a pasta dos dados)
├── requirements.txt                # Dependências (versões fixas)
├── README.md                       # Este ficheiro
├── Auxiliares_dev_EDA/             # Material de apoio do desenvolvimento (versões anteriores e ideias)
└── docs/
    ├── IA91_Project01_Guide.pdf    # Enunciado
    ├── data_tiny/                  # Conjunto de dados pequeno
    └── data_small_30_31oct2026/    # Conjunto de dados maior
```

## Dependências

Todas as dependências estão em `requirements.txt`, com versões fixas para que o notebook corra igual em qualquer computador.

| Pacote | Para que serve no projeto |
|---|---|
| **pandas** | Ler os CSVs e trabalhar com eles como tabelas: juntar encomendas, itens e produtos, converter datas, contagens e somas. Base da EDA. |
| **numpy** | Cálculo numérico com vetores e matrizes. Dependência do pandas; útil nas heurísticas. |
| **matplotlib** | Gráficos: Gantt das janelas temporais e carga vs. capacidade; mais tarde, curvas de custo por iteração. |
| **seaborn** | Gráficos estatísticos sobre o matplotlib. Não é usado na EDA; previsto para a análise de resultados. |
| **folium** | Mapas interativos. Não é usado na EDA; previsto para desenhar as rotas encontradas. |
| **python-constraint2** | Biblioteca do CSP ([github.com/python-constraint/python-constraint](https://github.com/python-constraint/python-constraint)). Importa-se com `from constraint import Problem`: variáveis, domínios, restrições e solvers (backtracking, min-conflicts). Substitui o antigo `python-constraint`, que já não é atualizado. |
| **jupyter** | Ambiente para abrir e correr os notebooks `.ipynb`. |
| **ipykernel** | Kernel Python que executa as células do notebook (também usado pelo VS Code). |

## Como executar

```bash
pip install -r requirements.txt
jupyter notebook
```

No Windows, se o comando `jupyter` não for reconhecido ou o Python errado for usado, usar o lançador `py`:

```bash
py -m pip install -r requirements.txt
py -m notebook
```

Abrir `01_eda_tiny.ipynb` ou `01_eda_small.ipynb` e executar todas as células. Todo o código está em cada notebook.
