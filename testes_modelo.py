"""
testes_modelo.py — Testes do model.py com rotas escritas à mão.
Inteligência Artificial 2026/27 · Licenciatura em Engenharia de Sistemas Informáticos (UPCA)
Trabalho Prático 1 · Grupo 02 (IA26_P01_G02)

Entregável da modelação: "model.py module + tests with hand-written routes".
Cada teste escreve uma rota à mão e confirma, com assert, que o verificador aceita as
rotas válidas e rejeita cada regra violada pelo motivo certo.
Os testes das heurísticas, da pesquisa, do CSP e do Hill-Climbing estão no notebook
principal, junto ao código de cada técnica.

Executar com:   py testes_modelo.py
"""

from datetime import datetime

from model import Problem, State, verificar_solucao

TINY = Problem("docs/data_tiny/")
SMALL = Problem("docs/data_small_30_31oct2026/")
W_TINY = TINY.armazem


def itens_das_encomendas(problem, encomendas):
    return {i for i, r in problem.pedidos.items() if r.order_id in encomendas}


def primeiro_erro(resultado):
    return resultado["erros"][0] if resultado["erros"] else ""


def rota_a_mao(problem, encomenda):
    """Rota simples escrita à mão: produtores (janela que fecha primeiro) → armazém → cliente → armazém."""
    itens = sorted([r for r in problem.pedidos.values() if r.order_id == encomenda],
                   key=lambda r: r.availability_end)
    produtores = list(dict.fromkeys(r.pickup_loc for r in itens))
    W = problem.armazem
    return ([("pickup", r.item_id) for p in produtores for r in itens if r.pickup_loc == p]
            + [("warehouse", W)] + [("load", r.item_id) for r in itens]
            + [("delivery", r.item_id) for r in itens] + [("warehouse", W)])


# ---------------------------------------------------------------------
# Uma rota válida e uma rota inválida para cada regra
# ---------------------------------------------------------------------

def teste_rota_valida():
    """Encomenda 1 do small: recolher, armazém, carregar, entregar, voltar."""
    rota = [("pickup", 1), ("pickup", 2), ("warehouse", SMALL.armazem),
            ("load", 1), ("load", 2), ("delivery", 1), ("delivery", 2), ("warehouse", SMALL.armazem)]
    r = SMALL.verificar_viabilidade(1, rota, datetime(2026, 10, 30, 7, 15),
                                    itens_objetivo={1, 2}, exigir_rota_completa=True)
    assert r["viavel"] and r["completa"], r["erros"]


def teste_custo_da_rota():
    """A função de custo soma as distâncias da matriz entre paragens consecutivas."""
    paragens = [W_TINY, 1, W_TINY]
    esperado = TINY.distancia[(W_TINY, 1)] + TINY.distancia[(1, W_TINY)]
    assert abs(TINY.custo_rota(paragens)["distancia_km"] - round(esperado, 2)) < 1e-9


def teste_fluxo_sem_armazem():
    """Entregar diretamente do produtor ao cliente é proibido."""
    r = SMALL.verificar_viabilidade(1, [("pickup", 1), ("delivery", 1)], datetime(2026, 10, 30, 7, 15))
    assert not r["viavel"]
    assert "sem ter sido previamente recolhido e carregado" in primeiro_erro(r)


def teste_janela_de_recolha():
    """Partir às 15:00 chega ao produtor depois de a janela fechar."""
    rota = [("pickup", 1), ("warehouse", SMALL.armazem)]
    r = SMALL.verificar_viabilidade(1, rota, datetime(2026, 10, 30, 15, 0))
    assert not r["viavel"]
    assert "recolha não cabe na janela" in primeiro_erro(r)


def teste_capacidade():
    """Recolher tudo do dia 30 (166,9 kg) excede o veículo 1 (150 kg), mas cabe no veículo 2 (200 kg)."""
    dia30 = [r for r in TINY.pedidos.values() if r.dia_recolha.day == 30]
    ordem = {3: 0, 2: 1, 1: 2}                                   # o P3 fecha mais cedo
    rota = [("pickup", r.item_id) for r in sorted(dia30, key=lambda r: ordem[r.pickup_loc])]
    rota.append(("warehouse", W_TINY))
    r1 = TINY.verificar_viabilidade(1, rota, datetime(2026, 10, 30, 6, 40))
    r2 = TINY.verificar_viabilidade(2, rota, datetime(2026, 10, 30, 6, 40))
    assert not r1["viavel"] and "excesso de capacidade" in primeiro_erro(r1)
    assert r2["viavel"], r2["erros"]


def teste_janela_de_entrega():
    """Encomenda 12: recolhida a tempo, mas a entrega começa depois das 14:45."""
    itens = sorted(itens_das_encomendas(TINY, {12}))
    recolha = [("pickup", i) for i in itens] + [("warehouse", W_TINY)]
    r1 = TINY.verificar_viabilidade(2, recolha, datetime(2026, 10, 30, 8, 0))
    assert r1["viavel"], r1["erros"]
    entrega = [("load", i) for i in itens] + [("delivery", i) for i in itens] + [("warehouse", W_TINY)]
    r2 = TINY.verificar_viabilidade(2, entrega, datetime(2026, 10, 30, 14, 30),
                                    chegada_armazem_previa=r1["no_armazem"])
    assert not r2["viavel"] and "entrega não cabe na janela" in primeiro_erro(r2)


def teste_permanencia_24h():
    """Item 22: recolhido cedo a 30 e carregado a 31 às 08:30 excede 24 h; recolhido mais tarde, cumpre."""
    cedo = TINY.verificar_viabilidade(2, [("pickup", 22), ("warehouse", W_TINY)], datetime(2026, 10, 30, 6, 30))
    tarde = TINY.verificar_viabilidade(2, [("pickup", 22), ("warehouse", W_TINY)], datetime(2026, 10, 30, 8, 50))
    entrega = [("load", 22), ("delivery", 22), ("warehouse", W_TINY)]
    r_cedo = TINY.verificar_viabilidade(2, entrega, datetime(2026, 10, 31, 8, 30), chegada_armazem_previa=cedo["no_armazem"])
    r_tarde = TINY.verificar_viabilidade(2, entrega, datetime(2026, 10, 31, 8, 30), chegada_armazem_previa=tarde["no_armazem"])
    assert not r_cedo["viavel"] and "excede o máximo de 24.0 h" in primeiro_erro(r_cedo)
    assert r_tarde["viavel"], r_tarde["erros"]


# ---------------------------------------------------------------------
# Soluções completas (verificar_solucao)
# ---------------------------------------------------------------------

def teste_solucao_dois_veiculos():
    """Encomenda 10 no veículo 1 e encomenda 11 no veículo 2, rotas escritas à mão: solução viável."""
    partida = datetime(2026, 10, 30, 6, 0)
    rotas = [(1, rota_a_mao(TINY, 10), partida), (2, rota_a_mao(TINY, 11), partida)]
    res = verificar_solucao(TINY, rotas, itens_objetivo=itens_das_encomendas(TINY, {10, 11}))
    assert res["viavel"], res["erros"]


def teste_solucao_com_item_esquecido():
    """Uma solução que não entrega a encomenda 10 é rejeitada."""
    rotas = [(2, rota_a_mao(TINY, 11), datetime(2026, 10, 30, 6, 30))]
    res = verificar_solucao(TINY, rotas, itens_objetivo=itens_das_encomendas(TINY, {10, 11}))
    assert not res["viavel"]
    assert any("não foi entregue" in e for e in res["erros"])


# ---------------------------------------------------------------------
# Modelo
# ---------------------------------------------------------------------

def teste_chave_ignora_historico():
    """Dois estados iguais que chegaram por caminhos diferentes têm a mesma chave."""
    t = datetime(2026, 10, 30, 9, 0)
    a = State(4, t, historico_paragens=(4, 1, 4), distancia_acumulada_km=61.2)
    b = State(4, t, historico_paragens=(4, 3, 4), distancia_acumulada_km=58.1)
    assert a.chave() == b.chave()


def teste_floyd_warshall_desigualdade_triangular():
    """As distâncias mínimas (usadas nas heurísticas) respeitam a desigualdade triangular."""
    for problem in (TINY, SMALL):
        d = problem.distancia_minima
        nos = list(problem.paragens)
        for a in nos:
            for b in nos:
                assert d[(a, b)] <= problem.distancia[(a, b)] + 1e-9
                for c in nos:
                    assert d[(a, c)] <= d[(a, b)] + d[(b, c)] + 1e-9


# ---------------------------------------------------------------------

def executar_todos():
    testes = [(nome, f) for nome, f in globals().items() if nome.startswith("teste_") and callable(f)]
    falhados = 0
    for nome, f in testes:
        try:
            f()
            print(f"  ✓ {nome}")
        except AssertionError as erro:
            falhados += 1
            print(f"  ✗ {nome}: {erro}")
    print(f"\n{len(testes) - falhados} de {len(testes)} testes passaram.")
    return falhados == 0


if __name__ == "__main__":
    import sys
    sys.exit(0 if executar_todos() else 1)
