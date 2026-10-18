# CONFIG - todas as configuracoes num lugar so.
#
# Guarda: seletores CSS do site (enunciado, alternativas), intervalo do polling,
# provedor de IA e modelo. A API key NAO fica aqui: fica no .env.
#
# TODO: preencher os seletores quando o site for escolhido
#       (F12 -> Inspecionar -> botao direito -> Copy -> Copy selector).
from pathlib import Path

SELETOR_ENUNCIADO = "#enunciado"
SELETOR_ALTERNATIVAS = "#alternativas .alternativa"

INTERVALO_POLLING = 1.0 

RAIZ = Path(__file__).resolve().parents[2]
URL_INICIAL = (RAIZ / "demo" / "quiz_local.html").as_uri()