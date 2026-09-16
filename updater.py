import os
import time
import threading
import requests

from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer


# =========================
# CONFIGURAÇÃO
# =========================

SERVIDORES = [
    "https://hacktools-fdep.onrender.com/",
]

INTERVALO = 600
TIMEOUT = 60
TENTATIVAS = 3

PORTA = int(os.environ.get("PORT", 10000))


# =========================
# SESSÃO HTTP
# =========================

sessao = requests.Session()

sessao.headers.update({
    "User-Agent": "RenderUpdater/1.0"
})


# =========================
# SERVIDOR HTTP
# =========================

class ServidorHTTP(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/":

            mensagem = (
                "RenderUpdater ONLINE\n"
                "Keep-Alive ativo.\n"
            )

            dados = mensagem.encode("utf-8")

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain; charset=utf-8"
            )

            self.send_header(
                "Content-Length",
                str(len(dados))
            )

            self.end_headers()

            self.wfile.write(dados)

            print(
                "[HTTP] Requisição recebida em /"
            )

        elif self.path == "/health":

            dados = b"OK"

            self.send_response(200)

            self.send_header(
                "Content-Type",
                "text/plain"
            )

            self.send_header(
                "Content-Length",
                str(len(dados))
            )

            self.end_headers()

            self.wfile.write(dados)

            print(
                "[HTTP] Health check recebido."
            )

        else:

            dados = b"404"

            self.send_response(404)

            self.send_header(
                "Content-Type",
                "text/plain"
            )

            self.send_header(
                "Content-Length",
                str(len(dados))
            )

            self.end_headers()

            self.wfile.write(dados)

    def log_message(self, formato, *args):
        return


def iniciar_http():

    servidor = HTTPServer(
        ("0.0.0.0", PORTA),
        ServidorHTTP
    )

    print()
    print("==============================")
    print("       HTTP SERVER")
    print("==============================")
    print(
        "[HTTP] Porta:",
        PORTA
    )
    print(
        "[HTTP] Host: 0.0.0.0"
    )
    print("==============================")
    print()

    servidor.serve_forever()


# =========================
# ACESSAR SERVIDOR
# =========================

def acessar_servidor(url):

    for tentativa in range(1, TENTATIVAS + 1):

        try:

            print()
            print(
                "[KEEP-ALIVE] Acessando:",
                url
            )

            print(
                "[KEEP-ALIVE] Tentativa:",
                tentativa,
                "/",
                TENTATIVAS
            )

            inicio = time.time()

            resposta = sessao.get(
                url,
                timeout=TIMEOUT
            )

            tempo = time.time() - inicio

            print(
                "[KEEP-ALIVE] Status:",
                resposta.status_code
            )

            print(
                "[KEEP-ALIVE] Tempo:",
                round(tempo, 2),
                "segundos"
            )

            return True

        except requests.exceptions.RequestException as erro:

            print(
                "[KEEP-ALIVE] Erro:",
                repr(erro)
            )

            if tentativa < TENTATIVAS:

                print(
                    "[KEEP-ALIVE] Nova tentativa em 5 segundos..."
                )

                time.sleep(5)

    print(
        "[KEEP-ALIVE] Falha definitiva:",
        url
    )

    return False


# =========================
# KEEP-ALIVE
# =========================

def keep_alive():

    print()
    print("==============================")
    print("      KEEP-ALIVE INICIADO")
    print("==============================")
    print()

    while True:

        inicio = time.time()

        sucessos = 0
        falhas = 0

        print()
        print("==============================")
        print("[KEEP-ALIVE] INICIANDO CICLO")
        print("==============================")

        for servidor in SERVIDORES:

            resultado = acessar_servidor(
                servidor
            )

            if resultado:
                sucessos += 1
            else:
                falhas += 1

        tempo_ciclo = time.time() - inicio

        print()
        print("==============================")
        print("[KEEP-ALIVE] CICLO FINALIZADO")
        print("==============================")

        print(
            "[KEEP-ALIVE] Sucessos:",
            sucessos
        )

        print(
            "[KEEP-ALIVE] Falhas:",
            falhas
        )

        print(
            "[KEEP-ALIVE] Duração:",
            round(tempo_ciclo, 2),
            "segundos"
        )

        print(
            "[KEEP-ALIVE] Aguardando",
            INTERVALO,
            "segundos..."
        )

        time.sleep(INTERVALO)


# =========================
# INICIALIZAÇÃO
# =========================

print()
print("================================")
print("        RENDER UPDATER")
print("================================")
print(
    "[SYSTEM] Porta:",
    PORTA
)
print(
    "[SYSTEM] Servidores:",
    len(SERVIDORES)
)
print(
    "[SYSTEM] Intervalo:",
    INTERVALO,
    "segundos"
)
print("================================")
print()


thread_http = threading.Thread(
    target=iniciar_http,
    daemon=True
)

thread_http.start()


keep_alive()
