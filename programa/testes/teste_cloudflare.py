# TESTE - o provedor Cloudflare (Workers AI), sem rede e sem chave de verdade.
#
# Confere: o endereco leva o ID da conta; sem ID valido o provedor e pulado (com aviso); o limite de
# tokens da resposta vai no pedido (so quando o provedor define); a espera ate a cota zerar (00:00
# UTC) quando o erro cita "neurons"; e a janela de configuracao aceita o ID e os nomes "@cf/...".
import io
import os
import pathlib
import sys
from contextlib import redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
sys.stdout.reconfigure(encoding="utf-8")

from quizbot.config import PROVEDORES
from quizbot.configurar import JanelaConfiguracao
from quizbot.models import Question
from quizbot.solvers import fabrica
from quizbot.solvers.api import ApiSolver, espera_da_cota

CF = PROVEDORES["cloudflare"]
CONTA = "0123456789abcdef0123456789abcdef"
os.environ.update({"CLOUDFLARE_API_KEY": "chave-falsa", "CLOUDFLARE_MODEL": CF.modelo_sugerido,
                   "CLOUDFLARE_MODEL_VISAO": CF.modelo_visao_sugerido})

# 1) o endereco leva o ID da conta e o limite de tokens chega a todos os solvers do provedor
os.environ["CLOUDFLARE_ACCOUNT_ID"] = CONTA
solvers = fabrica._criar(CF)
esperado = f"https://api.cloudflare.com/client/v4/accounts/{CONTA}/ai/v1/"
assert solvers and all(str(s._client.base_url) == esperado for s in solvers), [str(s._client.base_url) for s in solvers]
assert all(s._max_tokens == 4000 for s in solvers)
assert [s._modelo for s in solvers] == ["@cf/openai/gpt-oss-120b", "@cf/qwen/qwen3.8-27b", "@cf/openai/gpt-oss-20b"]
assert solvers[0].aceita_imagens and solvers[1].aceita_imagens and not solvers[2].aceita_imagens
print("endereco com o ID da conta, limite de tokens e ordem dos modelos ok")

# 2) sem ID (ou com ID torto) o provedor e pulado e o aviso diz o que falta
for ruim in ("", "123", "zzzz" * 8):
    os.environ["CLOUDFLARE_ACCOUNT_ID"] = ruim
    saida = io.StringIO()
    with redirect_stdout(saida):
        assert fabrica._criar(CF) == []
    assert "CLOUDFLARE_ACCOUNT_ID" in saida.getvalue(), saida.getvalue()
print("sem ID da conta valido: provedor pulado com aviso ok")


# 3) max_tokens vai no pedido quando definido, e NAO vai quando o provedor nao define
class Falso:
    def __init__(self):
        self.pedidos = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._criar))

    def _criar(self, **pedido):
        self.pedidos.append(pedido)
        msg = SimpleNamespace(content='{"indice": 1, "explicacao": "x"}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)])


q = Question("p", ("a", "b"))
falso = Falso()
ApiSolver("cloudflare", falso, "m", None, 5, None, 1.0, 4000).solve(q)
ApiSolver("groq", falso, "m").solve(q)
assert falso.pedidos[0]["max_tokens"] == 4000 and "max_tokens" not in falso.pedidos[1], falso.pedidos
print("max_tokens enviado so quando o provedor define ok")


# 4) cota do dia esgotada: espera ate 00:00 UTC (o texto exato do erro da Cloudflare nao foi visto)
class Erro429(Exception):
    status_code = 429
    body = {"errors": [{"code": 4006, "message": "you have used up your daily free allocation of 10,000 neurons"}]}


espera = espera_da_cota(Erro429("limite"))
agora = datetime.now(timezone.utc)
falta = 86400 - (agora.hour * 3600 + agora.minute * 60 + agora.second)
assert espera is not None and abs(espera - falta) < 5, (espera, falta)


class Outro429(Exception):
    status_code = 429
    body = "rate limited"


assert espera_da_cota(Outro429("rate limited")) is None  # 429 comum continua sem chute
print(f"cota de neurons esgotada: espera {espera / 3600:.1f} h ate zerar ok")

# 5) a janela de configuracao: ID da conta e nomes com "@"
valida = JanelaConfiguracao._validar
assert valida(CF, "chave", "@cf/openai/gpt-oss-120b", "@cf/google/gemma-4-26b-a4b-it", CONTA) is None
assert "ID da conta" in valida(CF, "chave", "@cf/openai/gpt-oss-120b", "", "curto")
assert valida(PROVEDORES["groq"], "chave", "openai/gpt-oss-120b", "") is None  # quem nao pede ID nao e afetado
print("janela de configuracao ok")
print("TUDO OK")
