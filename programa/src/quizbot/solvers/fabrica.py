# FABRICA - monta o solver final a partir do .env e do config.
#
# montar_solver() -> le ORDEM_PROVEDORES, cria um ApiSolver para cada provedor
#                    configurado (chave + modelo) e devolve um FallbackSolver.
#                    Cada provedor entra com o modelo do .env (o melhor) e, logo depois, os
#                    modelos reserva dele (Provedor.modelos_reserva, no config.py). A ordem
#                    final e impressa no registro: "[ia] ordem de tentativa: ...".
#                    Provedor sem chave ou sem modelo e pulado sem barulho.
#                    OpenRouter so entra com modelo ":free" (para nao gastar).
import os
from collections.abc import Callable

from dotenv import load_dotenv
from openai import OpenAI

from quizbot.config import (
    ARQUIVO_ENV,
    COOLDOWN_PROVEDOR,
    ORDEM_PADRAO,
    PROVEDORES,
    TIMEOUT_API,
    TIMEOUT_RAPIDO,
    Provedor,
)
from quizbot.solvers.api import ApiSolver
from quizbot.solvers.base import Solver, SolverError
from quizbot.solvers.fallback import FallbackSolver


def _criar(provedor: Provedor) -> list[ApiSolver]:
    # Devolve o solver do modelo do .env (o melhor) seguido dos modelos reserva do mesmo
    # provedor, na ordem. Lista vazia = provedor sem chave/modelo (pulado sem barulho).
    modelo = os.getenv(provedor.modelo_env, "").strip()
    chave = os.getenv(provedor.chave_env, "").strip()
    if not modelo or not chave:
        return []

    if provedor.so_free and not modelo.endswith(":free"):
        print(f"[aviso] {provedor.nome} ignorado: {provedor.modelo_env} precisa terminar em ':free'.")
        return []

    modelo_visao = os.getenv(provedor.modelo_visao_env, "").strip() or None
    if modelo_visao and provedor.so_free and not modelo_visao.endswith(":free"):
        print(f"[aviso] {provedor.nome}: {provedor.modelo_visao_env} precisa terminar em ':free'. Visao desligada.")
        modelo_visao = None

    client = OpenAI(
        base_url=provedor.base_url,
        api_key=chave,
        timeout=TIMEOUT_API,
        max_retries=0,
    )
    # Nome curto para a janela: "Gemini (Google)" vira "Gemini".
    apelido = provedor.rotulo.split(" (")[0] or provedor.nome
    solvers = [ApiSolver(provedor.nome, client, modelo, modelo_visao, provedor.max_imagens, apelido)]
    for reserva in provedor.modelos_reserva:
        if reserva == modelo:
            continue
        # Reserva so enxerga imagem se o principal tambem estiver configurado para isso.
        solvers.append(
            ApiSolver(
                provedor.nome,
                client,
                reserva,
                reserva if modelo_visao else None,
                provedor.max_imagens,
                apelido,
            )
        )
    return solvers


def montar_solver(ao_mudar_problemas: Callable[[list[str]], None] | None = None) -> Solver:
    # ao_mudar_problemas: chamado com os avisos das falhas de cada consulta (veja fallback.py).
    load_dotenv(ARQUIVO_ENV)
    ordem = os.getenv("ORDEM_PROVEDORES", ORDEM_PADRAO)

    solvers: list[Solver] = []
    for nome in (n.strip().lower() for n in ordem.split(",")):
        provedor = PROVEDORES.get(nome)
        if provedor is None:
            print(f"[aviso] provedor desconhecido em ORDEM_PROVEDORES: {nome!r}")
            continue
        solvers.extend(_criar(provedor))

    if not solvers:
        raise SolverError(
            "nenhuma chave de IA configurada. Use o atalho 'AssistenteQuiz - Configuracao' "
            "(ou o arquivo configurar.bat) e cole a sua chave."
        )
    # Ordem de tentativa, com o modelo de cada um (nenhuma chave aparece aqui).
    print("[ia] ordem de tentativa:", " > ".join(s.descricao for s in solvers))
    return FallbackSolver(
        solvers,
        cooldown=COOLDOWN_PROVEDOR,
        ao_mudar_problemas=ao_mudar_problemas,
        timeout_rapido=TIMEOUT_RAPIDO,
        timeout_final=TIMEOUT_API,
    )
