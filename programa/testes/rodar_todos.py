# RODAR TODOS OS TESTES - roda cada teste_*.py desta pasta, um por vez, e mostra o resumo.
#
# Uso (na raiz do projeto, com o Python do projeto):
#     .\.venv\Scripts\python.exe programa\testes\rodar_todos.py              # todos
#     .\.venv\Scripts\python.exe programa\testes\rodar_todos.py revisao      # so os que tem "revisao" no nome
#
# Um teste passou quando termina sem erro (cada um confere o que importa com "assert").
# Precisam do Chrome ou do Edge instalado (os que simulam o Moodle abrem um navegador sem janela).
# Alguns testes mostram janelinhas rapidamente: e normal. Nenhum usa a sua memoria, a nuvem, o .env
# ou as chaves de verdade (usam pastas temporarias e valores falsos).
import os
import pathlib
import subprocess
import sys
import time

PASTA = pathlib.Path(__file__).resolve().parent
RAIZ = PASTA.parents[1]  # a raiz do projeto
TEMPO_MAXIMO = 300  # segundos por teste


def main() -> int:
    filtro = sys.argv[1].lower() if len(sys.argv) > 1 else ""
    testes = sorted(t for t in PASTA.glob("teste_*.py") if filtro in t.name.lower())
    if not testes:
        print(f"nenhum teste encontrado (filtro: {filtro!r})")
        return 1
    ambiente = {**os.environ, "PYTHONPATH": str(RAIZ / "programa" / "src"), "PYTHONIOENCODING": "utf-8"}
    falharam: list[tuple[str, str]] = []
    inicio_geral = time.monotonic()
    for teste in testes:
        inicio = time.monotonic()
        try:
            resultado = subprocess.run(
                [sys.executable, str(teste)], cwd=RAIZ, env=ambiente, capture_output=True,
                text=True, encoding="utf-8", errors="replace", timeout=TEMPO_MAXIMO,
            )
            passou = resultado.returncode == 0
            saida = (resultado.stdout + resultado.stderr).strip()
        except subprocess.TimeoutExpired:
            passou, saida = False, f"passou de {TEMPO_MAXIMO} s (travou?)"
        print(f"{'ok    ' if passou else 'FALHOU'} {teste.name:<28} {time.monotonic() - inicio:5.1f} s")
        if not passou:
            falharam.append((teste.name, "\n".join(saida.splitlines()[-12:])))
    print(f"\n{len(testes) - len(falharam)} de {len(testes)} passaram em {time.monotonic() - inicio_geral:.0f} s")
    for nome, fim_da_saida in falharam:
        print(f"\n=== {nome} (ultimas linhas) ===\n{fim_da_saida}")
    return 1 if falharam else 0


if __name__ == "__main__":
    raise SystemExit(main())
