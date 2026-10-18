# FABRICA - monta o solver final a partir do .env e do config.
#
# montar_solver() -> le ORDEM_PROVEDORES, cria um ApiSolver para cada provedor
#                    configurado (chave + modelo) e devolve um FallbackSolver.
#                    Provedor sem chave ou sem modelo e pulado sem barulho.
#                    OpenRouter so entra com modelo ":free" (para nao gastar).
import os

from dotenv import load_dotenv
from openai import OpenAI

from quizbot.config import (
    COOLDOWN_PROVEDOR,
    ORDEM_PADRAO,
    PROVEDORES,
    TIMEOUT_API,
    Provedor,
)
from quizbot.solvers.api import ApiSolver
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fallback import FallbackSolver


def _criar(provedor: Provedor) -> ApiSolver | None:
    modelo = os.getenv(provedor.modelo_env, "").strip()
    chave = os.getenv(provedor.chave_env, "").strip()
    if not modelo or not chave:
        return None

    if provedor.so_free and not modelo.endswith(":free"):
        print(f"[aviso] {provedor.nome} ignorado: {provedor.modelo_env} precisa terminar em ':free'.")
        return None

    client = OpenAI(
        base_url=provedor.base_url,
        api_key=chave,
        timeout=TIMEOUT_API,
        max_retries=0,
    )
    return ApiSolver(provedor.nome, client, modelo)


def montar_solver() -> Solver:
    load_dotenv()
    ordem = os.getenv("ORDEM_PROVEDORES", ORDEM_PADRAO)

    solvers: list[Solver] = []
    for nome in (n.strip().lower() for n in ordem.split(",")):
        provedor = PROVEDORES.get(nome)
        if provedor is None:
            print(f"[aviso] provedor desconhecido em ORDEM_PROVEDORES: {nome!r}")
            continue
        solver = _criar(provedor)
        if solver is not None:
            solvers.append(solver)

    if not solvers:
        raise SolverError("nenhum provedor configurado. Preencha o .env (veja o .env.example).")
    print("Provedores ativos:", ", ".join(s.nome for s in solvers))
    return FallbackSolver(solvers, cooldown=COOLDOWN_PROVEDOR)
