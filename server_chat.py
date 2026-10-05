import os
import uuid
import sqlite3
from datetime import datetime

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# ============================================================
# CONFIGURAÇÃO
# ============================================================

DATABASE = "chat.db"
UPLOAD_DIR = "uploads"

os.makedirs(UPLOAD_DIR, exist_ok=True)

app = FastAPI(title="SimpleChat Server")


# ============================================================
# BANCO DE DADOS
# ============================================================

def get_db():
    db = sqlite3.connect(DATABASE)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = get_db()

    db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS friend_requests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL,

            UNIQUE(sender_id, receiver_id),

            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS friendships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id INTEGER NOT NULL,
            user2_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,

            UNIQUE(user1_id, user2_id),

            FOREIGN KEY(user1_id) REFERENCES users(id),
            FOREIGN KEY(user2_id) REFERENCES users(id)
        );

        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_id INTEGER NOT NULL,
            receiver_id INTEGER NOT NULL,

            type TEXT NOT NULL,
            content TEXT,

            created_at TEXT NOT NULL,

            FOREIGN KEY(sender_id) REFERENCES users(id),
            FOREIGN KEY(receiver_id) REFERENCES users(id)
        );
    """)

    db.commit()
    db.close()


init_db()


# ============================================================
# MODELOS
# ============================================================

class CreateUser(BaseModel):
    username: str


class FriendRequest(BaseModel):
    sender_id: int
    receiver_id: int


class FriendResponse(BaseModel):
    user_id: int
    request_id: int
    accept: bool


class SendMessage(BaseModel):
    sender_id: int
    receiver_id: int
    content: str


# ============================================================
# WEBSOCKET
# ============================================================

connected_users = {}


async def send_to_user(user_id, data):
    websocket = connected_users.get(user_id)

    if websocket:
        try:
            await websocket.send_json(data)
        except Exception:
            connected_users.pop(user_id, None)


# ============================================================
# USUÁRIOS
# ============================================================

@app.post("/users")
def create_user(data: CreateUser):
    username = data.username.strip()

    if not username:
        raise HTTPException(
            status_code=400,
            detail="Nome de usuário vazio."
        )

    if len(username) > 32:
        raise HTTPException(
            status_code=400,
            detail="Nome de usuário muito grande."
        )

    db = get_db()

    try:
        cursor = db.execute(
            """
            INSERT INTO users(username, created_at)
            VALUES (?, ?)
            """,
            (
                username,
                datetime.now().isoformat()
            )
        )

        db.commit()

        user_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        db.close()

        raise HTTPException(
            status_code=409,
            detail="Esse nome de usuário já existe."
        )

    db.close()

    return {
        "success": True,
        "id": user_id,
        "username": username
    }


@app.get("/users/{username}")
def get_user(username: str):
    db = get_db()

    user = db.execute(
        """
        SELECT id, username, created_at
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    db.close()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    return dict(user)


# ============================================================
# AMIZADES
# ============================================================

@app.post("/friends/request")
async def create_friend_request(data: FriendRequest):
    if data.sender_id == data.receiver_id:
        raise HTTPException(
            status_code=400,
            detail="Você não pode adicionar você mesmo."
        )

    db = get_db()

    sender = db.execute(
        "SELECT id FROM users WHERE id = ?",
        (data.sender_id,)
    ).fetchone()

    receiver = db.execute(
        "SELECT id FROM users WHERE id = ?",
        (data.receiver_id,)
    ).fetchone()

    if not sender or not receiver:
        db.close()

        raise HTTPException(
            status_code=404,
            detail="Usuário não encontrado."
        )

    a = min(data.sender_id, data.receiver_id)
    b = max(data.sender_id, data.receiver_id)

    friendship = db.execute(
        """
        SELECT id
        FROM friendships
        WHERE user1_id = ? AND user2_id = ?
        """,
        (a, b)
    ).fetchone()

    if friendship:
        db.close()

        raise HTTPException(
            status_code=409,
            detail="Vocês já são amigos."
        )

    existing = db.execute(
        """
        SELECT id, status
        FROM friend_requests
        WHERE
            sender_id = ?
            AND receiver_id = ?
        """,
        (
            data.sender_id,
            data.receiver_id
        )
    ).fetchone()

    if existing and existing["status"] == "pending":
        db.close()

        raise HTTPException(
            status_code=409,
            detail="Solicitação já enviada."
        )

    # Caso o outro usuário já tenha enviado uma solicitação,
    # podemos transformar isso diretamente em amizade.
    reverse = db.execute(
        """
        SELECT id
        FROM friend_requests
        WHERE
            sender_id = ?
            AND receiver_id = ?
            AND status = 'pending'
        """,
        (
            data.receiver_id,
            data.sender_id
        )
    ).fetchone()

    if reverse:
        db.execute(
            """
            UPDATE friend_requests
            SET status = 'accepted'
            WHERE id = ?
            """,
            (reverse["id"],)
        )

        db.execute(
            """
            INSERT INTO friendships(user1_id, user2_id, created_at)
            VALUES (?, ?, ?)
            """,
            (
                a,
                b,
                datetime.now().isoformat()
            )
        )

        db.commit()
        db.close()

        await send_to_user(
            data.receiver_id,
            {
                "type": "friend_accepted",
                "user_id": data.sender_id
            }
        )

        return {
            "success": True,
            "status": "accepted"
        }

    cursor = db.execute(
        """
        INSERT INTO friend_requests(
            sender_id,
            receiver_id,
            status,
            created_at
        )
        VALUES (?, ?, 'pending', ?)
        """,
        (
            data.sender_id,
            data.receiver_id,
            datetime.now().isoformat()
        )
    )

    db.commit()

    request_id = cursor.lastrowid

    db.close()

    await send_to_user(
        data.receiver_id,
        {
            "type": "friend_request",
            "request_id": request_id,
            "sender_id": data.sender_id
        }
    )

    return {
        "success": True,
        "request_id": request_id,
        "status": "pending"
    }


@app.post("/friends/respond")
async def respond_friend_request(data: FriendResponse):
    db = get_db()

    request = db.execute(
        """
        SELECT *
        FROM friend_requests
        WHERE
            id = ?
            AND receiver_id = ?
            AND status = 'pending'
        """,
        (
            data.request_id,
            data.user_id
        )
    ).fetchone()

    if not request:
        db.close()

        raise HTTPException(
            status_code=404,
            detail="Solicitação não encontrada."
        )

    if not data.accept:
        db.execute(
            """
            UPDATE friend_requests
            SET status = 'rejected'
            WHERE id = ?
            """,
            (data.request_id,)
        )

        db.commit()
        db.close()

        return {
            "success": True,
            "status": "rejected"
        }

    a = min(
        request["sender_id"],
        request["receiver_id"]
    )

    b = max(
        request["sender_id"],
        request["receiver_id"]
    )

    db.execute(
        """
        UPDATE friend_requests
        SET status = 'accepted'
        WHERE id = ?
        """,
        (data.request_id,)
    )

    db.execute(
        """
        INSERT OR IGNORE INTO friendships(
            user1_id,
            user2_id,
            created_at
        )
        VALUES (?, ?, ?)
        """,
        (
            a,
            b,
            datetime.now().isoformat()
        )
    )

    db.commit()

    other_user = request["sender_id"]

    db.close()

    await send_to_user(
        other_user,
        {
            "type": "friend_accepted",
            "user_id": data.user_id
        }
    )

    return {
        "success": True,
        "status": "accepted"
    }


@app.get("/friends/{user_id}")
def get_friends(user_id: int):
    db = get_db()

    friends = db.execute(
        """
        SELECT
            users.id,
            users.username,
            users.created_at
        FROM friendships
        JOIN users
            ON users.id =
                CASE
                    WHEN friendships.user1_id = ?
                    THEN friendships.user2_id
                    ELSE friendships.user1_id
                END
        WHERE
            friendships.user1_id = ?
            OR friendships.user2_id = ?
        ORDER BY users.username
        """,
        (
            user_id,
            user_id,
            user_id
        )
    ).fetchall()

    db.close()

    return {
        "friends": [dict(friend) for friend in friends]
    }


@app.get("/friends/requests/{user_id}")
def get_friend_requests(user_id: int):
    db = get_db()

    requests = db.execute(
        """
        SELECT
            friend_requests.id,
            friend_requests.sender_id,
            users.username AS sender_username,
            friend_requests.created_at
        FROM friend_requests
        JOIN users
            ON users.id = friend_requests.sender_id
        WHERE
            friend_requests.receiver_id = ?
            AND friend_requests.status = 'pending'
        ORDER BY friend_requests.created_at DESC
        """,
        (user_id,)
    ).fetchall()

    db.close()

    return {
        "requests": [dict(request) for request in requests]
    }


# ============================================================
# MENSAGENS
# ============================================================

def are_friends(user1, user2):
    db = get_db()

    a = min(user1, user2)
    b = max(user1, user2)

    result = db.execute(
        """
        SELECT id
        FROM friendships
        WHERE user1_id = ? AND user2_id = ?
        """,
        (a, b)
    ).fetchone()

    db.close()

    return result is not None


@app.post("/messages")
async def send_message(data: SendMessage):
    if not are_friends(
        data.sender_id,
        data.receiver_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Vocês não são amigos."
        )

    content = data.content

    if not content.strip():
        raise HTTPException(
            status_code=400,
            detail="Mensagem vazia."
        )

    db = get_db()

    created_at = datetime.now().isoformat()

    cursor = db.execute(
        """
        INSERT INTO messages(
            sender_id,
            receiver_id,
            type,
            content,
            created_at
        )
        VALUES (?, ?, 'text', ?, ?)
        """,
        (
            data.sender_id,
            data.receiver_id,
            content,
            created_at
        )
    )

    db.commit()

    message_id = cursor.lastrowid

    db.close()

    message = {
        "type": "message",
        "message": {
            "id": message_id,
            "sender_id": data.sender_id,
            "receiver_id": data.receiver_id,
            "message_type": "text",
            "content": content,
            "created_at": created_at
        }
    }

    await send_to_user(
        data.receiver_id,
        message
    )

    return message["message"]


@app.get("/messages/{user_id}/{other_user_id}")
def get_messages(
    user_id: int,
    other_user_id: int
):
    if not are_friends(
        user_id,
        other_user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Vocês não são amigos."
        )

    db = get_db()

    messages = db.execute(
        """
        SELECT
            id,
            sender_id,
            receiver_id,
            type,
            content,
            created_at
        FROM messages
        WHERE
            (
                sender_id = ?
                AND receiver_id = ?
            )
            OR
            (
                sender_id = ?
                AND receiver_id = ?
            )
        ORDER BY id ASC
        """,
        (
            user_id,
            other_user_id,
            other_user_id,
            user_id
        )
    ).fetchall()

    db.close()

    return {
        "messages": [dict(message) for message in messages]
    }


# ============================================================
# UPLOADS
# ============================================================

@app.post("/upload")
async def upload_file(
    sender_id: int,
    receiver_id: int,
    file: UploadFile = File(...)
):
    if not are_friends(
        sender_id,
        receiver_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Vocês não são amigos."
        )

    original_name = file.filename or "arquivo"

    extension = os.path.splitext(
        original_name
    )[1]

    file_id = str(uuid.uuid4())

    filename = file_id + extension

    path = os.path.join(
        UPLOAD_DIR,
        filename
    )

    with open(path, "wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)

            if not chunk:
                break

            output.write(chunk)

    message_type = "image"

    if not (file.content_type or "").startswith("image/"):
        message_type = "file"

    created_at = datetime.now().isoformat()

    db = get_db()

    cursor = db.execute(
        """
        INSERT INTO messages(
            sender_id,
            receiver_id,
            type,
            content,
            created_at
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            sender_id,
            receiver_id,
            message_type,
            filename,
            created_at
        )
    )

    db.commit()

    message_id = cursor.lastrowid

    db.close()

    message = {
        "type": "message",
        "message": {
            "id": message_id,
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "message_type": message_type,
            "content": filename,
            "filename": original_name,
            "created_at": created_at
        }
    }

    await send_to_user(
        receiver_id,
        message
    )

    return message["message"]


@app.get("/files/{filename}")
def get_file(filename: str):
    path = os.path.join(
        UPLOAD_DIR,
        filename
    )

    if not os.path.isfile(path):
        raise HTTPException(
            status_code=404,
            detail="Arquivo não encontrado."
        )

    return FileResponse(path)


# ============================================================
# WEBSOCKET
# ============================================================

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    user_id: int
):
    await websocket.accept()

    connected_users[user_id] = websocket

    await websocket.send_json({
        "type": "connected",
        "user_id": user_id
    })

    try:
        while True:
            data = await websocket.receive_json()

            # Por enquanto o WebSocket é usado principalmente
            # para eventos em tempo real.
            #
            # As mensagens também podem ser enviadas pela API
            # POST /messages.

            if data.get("type") == "ping":
                await websocket.send_json({
                    "type": "pong"
                })

    except WebSocketDisconnect:
        if connected_users.get(user_id) == websocket:
            connected_users.pop(user_id, None)

    except Exception:
        if connected_users.get(user_id) == websocket:
            connected_users.pop(user_id, None)


# ============================================================
# TESTE
# ============================================================

@app.get("/")
def root():
    return {
        "name": "SimpleChat",
        "status": "online",
        "version": "0.1.0"
    }
