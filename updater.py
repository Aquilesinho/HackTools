import os
import time
import threading
import requests

from http.server import BaseHTTPRequestHandler
from http.server import HTTPServer


SERVIDORES = [
    "https://hacktools-fdep.onrender.com/health",
]

INTERVALO = 300
TIMEOUT = 30
TENTATIVAS = 3

PORTA = int(
    os.environ.get(
        "PORT",
        10000
    )
)


sessao = requests.Session()

sessao.headers.update({
    "User-Agent": "HackTools-KeepAlive/1.0"
})


class ServidorHTTP(BaseHTTPRequestHandler):

    def do_GET(self):

        if self.path == "/":

            dados = b"HackTools Keep-Alive ONLINE"

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

            self.wfile.write(
                dados
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

            self.wfile.write(
                dados
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

            self.wfile.write(
                dados
            )

    def log_message(self, formato, *args):
        return


def iniciar_http():

    servidor = HTTPServer(
        (
            "0.0.0.0",
            PORTA
        ),
        ServidorHTTP
    )

    print(
        "[HTTP] Servidor iniciado na porta:",
        PORTA
    )

    servidor.serve_forever()


def acessar_servidor(url):

    for tentativa in range(
        1,
        TENTATIVAS + 1
    ):

        try:

            print(
                "[KEEP-ALIVE] GET:",
                url
            )

            resposta = sessao.get(
                url,
                timeout=TIMEOUT
            )

            print(
                "[KEEP-ALIVE] Status:",
                resposta.status_code
            )

            if resposta.status_code == 200:

                return True

        except requests.exceptions.RequestException as erro:

            print(
                "[KEEP-ALIVE] Erro:",
                repr(erro)
            )

        if tentativa < TENTATIVAS:

            time.sleep(5)

    return False


def keep_alive():

    print(
        "[KEEP-ALIVE] Iniciado."
    )

    while True:

        for servidor in SERVIDORES:

            acessar_servidor(
                servidor
            )

        print(
            "[KEEP-ALIVE] Próximo ciclo em",
            INTERVALO,
            "segundos."
        )

        time.sleep(
            INTERVALO
        )


print(
    "[SYSTEM] Render updater iniciado."
)

thread_http = threading.Thread(
    target=iniciar_http,
    daemon=True
)

thread_http.start()

keep_alive()
