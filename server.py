import os
import json
import uuid
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

clientes = {}
clientes_lock = asyncio.Lock()


async def enviar_json(websocket, dados):
    await websocket.send_text(
        json.dumps(
            dados
        )
    )


@app.get("/")
async def inicio():
    return {
        "status": "HackToolsServer online"
    }


@app.get("/health")
async def health():
    return {
        "status": "ok"
    }


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    cliente_id = None
    tipo_cliente = None

    try:

        primeiro = await websocket.receive_text()

        dados = json.loads(
            primeiro
        )

        if dados.get("tipo") == "REGISTER":

            tipo_cliente = "RECEPTOR"

            cliente_id = dados.get(
                "id"
            )

            if not cliente_id:
                cliente_id = str(
                    uuid.uuid4()
                )

            usuario = dados.get(
                "usuario",
                "Desconhecido"
            )

            async with clientes_lock:

                clientes[cliente_id] = {
                    "websocket": websocket,
                    "tipo": "RECEPTOR",
                    "usuario": usuario
                }

            await enviar_json(
                websocket,
                {
                    "tipo": "REGISTERED",
                    "id": cliente_id
                }
            )

            print(
                "[SERVER] Receptor conectado:",
                cliente_id,
                usuario
            )

        elif dados.get("tipo") == "MAIN":

            tipo_cliente = "MAIN"

            await enviar_json(
                websocket,
                {
                    "tipo": "CONNECTED"
                }
            )

            print(
                "[SERVER] Main conectado."
            )

        else:

            await enviar_json(
                websocket,
                {
                    "tipo": "ERROR",
                    "mensagem": "Primeiro pacote inválido."
                }
            )

            await websocket.close()

            return

        while True:

            if tipo_cliente == "RECEPTOR":

                mensagem = await websocket.receive()

                if mensagem["type"] == "websocket.disconnect":
                    break

                if "text" in mensagem and mensagem["text"]:

                    dados = json.loads(
                        mensagem["text"]
                    )

                    destino = dados.get(
                        "destino"
                    )

                    if destino in clientes:

                        await clientes[
                            destino
                        ]["websocket"].send_text(
                            mensagem["text"]
                        )

                elif "bytes" in mensagem and mensagem["bytes"]:

                    dados = mensagem["bytes"]

                    destino = None

                    if cliente_id in clientes:

                        destino = clientes[
                            cliente_id
                        ].get(
                            "sessao"
                        )

                    if destino in clientes:

                        await clientes[
                            destino
                        ]["websocket"].send_bytes(
                            dados
                        )

            else:

                mensagem = await websocket.receive()

                if mensagem["type"] == "websocket.disconnect":
                    break

                if "text" in mensagem and mensagem["text"]:

                    dados = json.loads(
                        mensagem["text"]
                    )

                    tipo = dados.get(
                        "tipo"
                    )

                    if tipo == "LIST":

                        lista = []

                        async with clientes_lock:

                            for id_cliente, cliente in clientes.items():

                                if cliente.get("tipo") == "RECEPTOR":

                                    lista.append(
                                        {
                                            "id": id_cliente,
                                            "usuario": cliente.get(
                                                "usuario",
                                                "Desconhecido"
                                            )
                                        }
                                    )

                        await enviar_json(
                            websocket,
                            {
                                "tipo": "LIST_RESPONSE",
                                "dispositivos": lista
                            }
                        )

                        continue

                    if tipo == "SEE_REQUEST":

                        receptor_id = dados.get(
                            "id"
                        )

                        if receptor_id not in clientes:

                            await enviar_json(
                                websocket,
                                {
                                    "tipo": "ERROR",
                                    "mensagem": "Receptor não encontrado."
                                }
                            )

                            continue

                        receptor = clientes[
                            receptor_id
                        ]

                        if receptor.get("tipo") != "RECEPTOR":

                            await enviar_json(
                                websocket,
                                {
                                    "tipo": "ERROR",
                                    "mensagem": "Destino inválido."
                                }
                            )

                            continue

                        receptor["sessao"] = None

                        await enviar_json(
                            receptor["websocket"],
                            {
                                "tipo": "SEE_REQUEST",
                                "origem": "MAIN"
                            }
                        )

                        clientes[
                            receptor_id
                        ]["sessao"] = None

                        clientes[
                            receptor_id
                        ]["main"] = websocket

                        continue

                    receptor_id = dados.get(
                        "destino"
                    )

                    if receptor_id in clientes:

                        receptor = clientes[
                            receptor_id
                        ]

                        await receptor[
                            "websocket"
                        ].send_text(
                            mensagem["text"]
                        )

                elif "bytes" in mensagem and mensagem["bytes"]:

                    continue

    except WebSocketDisconnect:
        pass

    except Exception as erro:

        print(
            "[SERVER] Erro:",
            repr(erro)
        )

    finally:

        if cliente_id is not None:

            async with clientes_lock:

                if cliente_id in clientes:

                    del clientes[
                        cliente_id
                    ]

            print(
                "[SERVER] Cliente removido:",
                cliente_id
            )