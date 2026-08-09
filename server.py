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
                    "usuario": usuario,
                    "main": None,
                    "main_receptor": None
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

                # =========================
                # MAIN -> LIST
                # =========================

                if tipo_cliente == "MAIN" and tipo == "LIST":

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

                # =========================
                # MAIN -> SEE_REQUEST
                # =========================

                if tipo_cliente == "MAIN" and tipo == "SEE_REQUEST":
                
                    receptor_id = dados.get(
                        "id"
                    )
                
                    async with clientes_lock:
                
                        receptor = clientes.get(
                            receptor_id
                        )
                
                        if receptor is None:
                
                            await enviar_json(
                                websocket,
                                {
                                    "tipo": "ERROR",
                                    "mensagem": "Receptor não encontrado."
                                }
                            )
                
                            continue
                
                        if receptor.get("tipo") != "RECEPTOR":
                
                            await enviar_json(
                                websocket,
                                {
                                    "tipo": "ERROR",
                                    "mensagem": "Destino inválido."
                                }
                            )
                
                            continue
                
                        receptor["main"] = websocket
                        receptor["main_receptor"] = receptor_id
                
                        websocket_receptor = receptor[
                            "websocket"
                        ]
                
                    print(
                        "[SERVER] SEE_REQUEST ->",
                        receptor_id
                    )
                
                    await enviar_json(
                        websocket_receptor,
                        {
                            "tipo": "SEE_REQUEST",
                            "origem": "MAIN"
                        }
                    )
                
                    continue

                # =========================
                # RECEPTOR -> MAIN
                # =========================

                if tipo_cliente == "RECEPTOR":
                
                    async with clientes_lock:
                
                        receptor = clientes.get(
                            cliente_id
                        )
                
                        if receptor is None:
                            continue
                
                        main = receptor.get(
                            "main"
                        )
                
                    if main is not None:
                
                        await main.send_text(
                            mensagem["text"]
                        )
                
                    continue

                # =========================
                # MAIN -> RECEPTOR
                # =========================

                if tipo_cliente == "MAIN":
                
                    receptor_id = dados.get(
                        "destino"
                    )
                
                    async with clientes_lock:
                
                        receptor = clientes.get(
                            receptor_id
                        )
                
                        if receptor is None:
                            continue
                
                        if receptor.get("tipo") != "RECEPTOR":
                            continue
                
                        websocket_receptor = receptor[
                            "websocket"
                        ]
                
                    await websocket_receptor.send_text(
                        mensagem["text"]
                    )
                
                    continue

            elif "bytes" in mensagem and mensagem["bytes"]:
            
                if tipo_cliente == "RECEPTOR":
            
                    async with clientes_lock:
            
                        receptor = clientes.get(
                            cliente_id
                        )
            
                        if receptor is None:
                            continue
            
                        main = receptor.get(
                            "main"
                        )
            
                    if main is not None:
            
                        await main.send_bytes(
                            mensagem["bytes"]
                        )

                # MAIN -> RECEPTOR
                elif tipo_cliente == "MAIN":

                    receptor_id = dados.get(
                        "destino"
                    )

                    if receptor_id in clientes:

                        receptor = clientes[
                            receptor_id
                        ]

                        await receptor[
                            "websocket"
                        ].send_bytes(
                            mensagem["bytes"]
                        )

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
