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

## Estrutura

```
├── 01_eda_tiny.ipynb               # Introdução e análise exploratória dos dados
├── requirements.txt                # Dependências (versões fixas)
├── readme.txt                      # Link do repositório (exigido na entrega)
└── docs/
    ├── IA91_Project01_Guide.pdf    # Enunciado
    ├── data_tiny/                  # Conjunto de dados pequeno
    └── data_small_30_31oct2026/    # Conjunto de dados maior (+ rules.csv)
```

## Dependências

Todas as dependências estão em `requirements.txt`, com versões fixas para que o notebook corra igual em qualquer computador.

| Pacote | Para que serve no projeto |
|---|---|
| **pandas** | Ler os CSVs e trabalhar com eles como tabelas: juntar encomendas, itens e produtos, converter datas, contagens e somas. Base da EDA. |
| **numpy** | Cálculo numérico com vetores e matrizes (matriz de distâncias, contas nas heurísticas). Dependência do pandas. |
| **matplotlib** | Gráficos: pesos por dia, Gantt das janelas temporais, curvas de custo por iteração. |
| **seaborn** | Gráficos estatísticos sobre o matplotlib, como o heatmap das distâncias e as distribuições. |
| **folium** | Mapas interativos com produtores, centro de recolha e locais de entrega; mais tarde, as rotas. |
| **python-constraint** | Biblioteca do CSP (`from constraint import Problem`): variáveis, domínios e restrições. |
| **jupyter** | Ambiente para abrir e correr os notebooks `.ipynb`. |
| **ipykernel** | Kernel Python que executa as células do notebook (também usado pelo VS Code). |

## Como executar

```bash
pip install -r requirements.txt
jupyter notebook
```

Abrir `01_eda_tiny.ipynb` e executar todas as células.
