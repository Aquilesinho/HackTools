import os
import json
import uuid
import asyncio
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

app = FastAPI()

clientes = {}
clientes_lock = asyncio.Lock()

agendamentos = []
agendamentos_lock = asyncio.Lock()

FUNCOES_AGENDAVEIS = {
    "popup"
}


# ==========================================================
# ENVIO JSON
# ==========================================================

async def enviar_json(websocket, dados):
    await websocket.send_text(
        json.dumps(dados)
    )


# ==========================================================
# ROTAS
# ==========================================================

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


# ==========================================================
# ADICIONAR AGENDAMENTO
# ==========================================================

async def adicionar_agendamento(dados):

    funcao = dados.get("funcao")

    if funcao not in FUNCOES_AGENDAVEIS:
        return {
            "tipo": "ERROR",
            "mensagem": "Função não permitida para agendamento."
        }

    receptor_id = dados.get("id")

    if not receptor_id:
        return {
            "tipo": "ERROR",
            "mensagem": "ID do receptor não informado."
        }

    try:

        momento = datetime.strptime(
            dados["data"] + " " + dados["hora"],
            "%d/%m/%Y %H:%M:%S"
        )

    except Exception:

        return {
            "tipo": "ERROR",
            "mensagem": "Data ou hora inválida."
        }

    # Verifica se o receptor existe
    async with clientes_lock:

        receptor = clientes.get(
            receptor_id
        )

        if receptor is None:

            return {
                "tipo": "ERROR",
                "mensagem": "Receptor não encontrado."
            }

        if receptor.get("tipo") != "RECEPTOR":

            return {
                "tipo": "ERROR",
                "mensagem": "Destino inválido."
            }

    agendamento = {

        "id": str(
            uuid.uuid4()
        ),

        "momento": momento.timestamp(),

        "data": dados["data"],

        "hora": dados["hora"],

        "funcao": funcao,

        # IMPORTANTE:
        # Guarda o receptor correto
        "receptor_id": receptor_id,

        "args": dados.get(
            "args",
            []
        ),

        "kwargs": dados.get(
            "kwargs",
            {}
        ),

        "imports": dados.get(
            "imports",
            []
        ),

        "dependencias": dados.get(
            "dependencias",
            []
        )
    }

    async with agendamentos_lock:

        agendamentos.append(
            agendamento
        )

    print(
        "[SERVER] Agendamento criado:",
        agendamento["id"],
        "-> receptor:",
        receptor_id,
        funcao,
        dados["data"],
        dados["hora"]
    )

    return {

        "tipo": "SCHEDULED",

        "id": agendamento["id"],

        "receptor_id": receptor_id
    }


# ==========================================================
# EXECUTAR AGENDAMENTO
# ==========================================================

async def executar_agendamento(agendamento):

    receptor_id = agendamento.get(
        "receptor_id"
    )

    if not receptor_id:

        print(
            "[SERVER] Agendamento sem receptor:",
            agendamento["id"]
        )

        return

    # Procura SOMENTE o receptor correto
    async with clientes_lock:

        receptor = clientes.get(
            receptor_id
        )

    if receptor is None:

        print(
            "[SERVER] Receptor não conectado:",
            receptor_id,
            "| agendamento:",
            agendamento["id"]
        )

        return

    if receptor.get("tipo") != "RECEPTOR":

        print(
            "[SERVER] Destino não é um receptor:",
            receptor_id
        )

        return

    websocket = receptor.get(
        "websocket"
    )

    if websocket is None:

        print(
            "[SERVER] WebSocket do receptor não encontrado:",
            receptor_id
        )

        return

    pacote = {

        "tipo": "IN",

        "funcao": agendamento["funcao"],

        "args": agendamento["args"],

        "kwargs": agendamento["kwargs"],

        "imports": agendamento["imports"],

        "dependencias": agendamento["dependencias"],

        "agendamento_id": agendamento["id"]
    }

    try:

        await enviar_json(
            websocket,
            pacote
        )

        print(
            "[SERVER] Agendamento executado:",
            agendamento["id"],
            "->",
            receptor_id,
            receptor.get(
                "usuario",
                "Desconhecido"
            )
        )

    except Exception as erro:

        print(
            "[SERVER] Erro ao executar agendamento:",
            repr(erro)
        )


# ==========================================================
# VERIFICAR AGENDAMENTOS
# ==========================================================

async def verificar_agendamentos():

    while True:

        agora = datetime.now().timestamp()

        executar = []

        async with agendamentos_lock:

            restantes = []

            for agendamento in agendamentos:

                if agendamento["momento"] <= agora:

                    executar.append(
                        agendamento
                    )

                else:

                    restantes.append(
                        agendamento
                    )

            agendamentos.clear()

            agendamentos.extend(
                restantes
            )

        # Executa somente os agendamentos vencidos
        for agendamento in executar:

            await executar_agendamento(
                agendamento
            )

        await asyncio.sleep(
            0.5
        )


# ==========================================================
# WEBSOCKET
# ==========================================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):

    await websocket.accept()

    cliente_id = None
    tipo_cliente = None

    try:

        # ==================================================
        # PRIMEIRO PACOTE
        # ==================================================

        primeiro = await websocket.receive_text()

        dados = json.loads(
            primeiro
        )

        # ==================================================
        # REGISTER -> RECEPTOR
        # ==================================================

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

        # ==================================================
        # MAIN
        # ==================================================

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

        # ==================================================
        # LOOP
        # ==================================================

        while True:

            mensagem = await websocket.receive()

            if mensagem["type"] == "websocket.disconnect":

                break

            # ==================================================
            # MENSAGEM DE TEXTO
            # ==================================================

            if "text" in mensagem and mensagem["text"]:

                dados = json.loads(
                    mensagem["text"]
                )

                tipo = dados.get(
                    "tipo"
                )

                # ==================================================
                # MAIN -> LIST
                # ==================================================

                if (
                    tipo_cliente == "MAIN"
                    and tipo == "LIST"
                ):

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

                # ==================================================
                # MAIN -> SCHEDULE
                # ==================================================

                if (
                    tipo_cliente == "MAIN"
                    and tipo == "SCHEDULE"
                ):

                    resposta = await adicionar_agendamento(
                        dados
                    )

                    await enviar_json(
                        websocket,
                        resposta
                    )

                    continue

                # ==================================================
                # MAIN -> SEE_REQUEST
                # ==================================================

                if (
                    tipo_cliente == "MAIN"
                    and tipo == "SEE_REQUEST"
                ):

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

                        # Vincula esse receptor ao MAIN
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

                # ==================================================
                # RECEPTOR -> MAIN
                # ==================================================

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

                        try:

                            await main.send_text(
                                mensagem["text"]
                            )

                        except Exception as erro:

                            print(
                                "[SERVER] Erro RECEPTOR -> MAIN:",
                                repr(erro)
                            )

                    continue

                # ==================================================
                # MAIN -> RECEPTOR
                # ==================================================

                if tipo_cliente == "MAIN":

                    async with clientes_lock:

                        receptor = None

                        for id_cliente, cliente in clientes.items():

                            if cliente.get("tipo") != "RECEPTOR":

                                continue

                            if cliente.get("main") is websocket:

                                receptor = cliente

                                break

                        if receptor is None:

                            await enviar_json(
                                websocket,
                                {
                                    "tipo": "ERROR",
                                    "mensagem": "Nenhum receptor associado a este MAIN."
                                }
                            )

                            continue

                        websocket_receptor = receptor[
                            "websocket"
                        ]

                        receptor_id = receptor.get(
                            "main_receptor"
                        )

                    print(
                        "[SERVER] AÇÃO -> RECEPTOR:",
                        receptor_id,
                        dados
                    )

                    try:

                        await websocket_receptor.send_text(
                            mensagem["text"]
                        )

                    except Exception as erro:

                        print(
                            "[SERVER] Erro MAIN -> RECEPTOR:",
                            repr(erro)
                        )

                    continue

            # ==================================================
            # MENSAGEM BINÁRIA
            # ==================================================

            elif "bytes" in mensagem and mensagem["bytes"]:

                # ==================================================
                # RECEPTOR -> MAIN
                # ==================================================

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

                        try:

                            await main.send_bytes(
                                mensagem["bytes"]
                            )

                        except Exception as erro:

                            print(
                                "[SERVER] Erro FRAME -> MAIN:",
                                repr(erro)
                            )

                # ==================================================
                # MAIN -> RECEPTOR
                # ==================================================

                elif tipo_cliente == "MAIN":

                    print(
                        "[SERVER] MAIN enviou bytes, mas ações devem ser JSON."
                    )

                    continue

    except WebSocketDisconnect:

        print(
            "[SERVER] WebSocket desconectado:",
            cliente_id
        )

    except Exception as erro:

        print(
            "[SERVER] Erro:",
            repr(erro)
        )

    finally:

        # ==================================================
        # REMOVE RECEPTOR
        # ==================================================

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


# ==========================================================
# STARTUP
# ==========================================================

@app.on_event("startup")
async def iniciar_agendador():

    asyncio.create_task(
        verificar_agendamentos()
    )

    print(
        "[SERVER] Agendador iniciado."
    )
