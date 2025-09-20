from flask import Flask, request
import sqlite3
import os
import requests
import re

# === CONFIGURAÇÕES DO TELEGRAM ===
TOKEN = "8269161965:AAGJ8YMTErLaPw7zWIfxuNHf71wI2YimLyI"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# === BANCO DE DADOS ===
DB_PATH = "manutencoes.db"
OWNER_FILE = "owner_chat_id.txt"

app = Flask(__name__)

# === BANCO DE DADOS ===
def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS manutencoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT NOT NULL,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def adicionar_manutencao(placa, tipo, descricao, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO manutencoes (placa, tipo, descricao, data) VALUES (?, ?, ?, ?)",
              (placa.upper(), tipo.lower(), descricao, data))
    conn.commit()
    conn.close()

def ultima_manutencao(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tipo, descricao, data FROM manutencoes WHERE placa=? ORDER BY id DESC LIMIT 1",
              (placa.upper(),))
    row = c.fetchone()
    conn.close()
    return row

def historico_manutencao(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tipo, descricao, data FROM manutencoes WHERE placa=? ORDER BY id DESC", (placa.upper(),))
    rows = c.fetchall()
    conn.close()
    return rows

def listar_todas():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT placa, tipo, descricao, data FROM manutencoes ORDER BY data DESC")
    registros = c.fetchall()
    conn.close()
    return registros

# --- Owner ---
def get_owner_chat_id():
    if not os.path.exists(OWNER_FILE):
        return None
    try:
        with open(OWNER_FILE, "r") as f:
            return int(f.read().strip())
    except:
        return None

def set_owner_chat_id(chat_id):
    with open(OWNER_FILE, "w") as f:
        f.write(str(chat_id))

def enviar_mensagem(chat_id, texto):
    target = chat_id if chat_id is not None else get_owner_chat_id()
    if not target:
        print("⚠️ Nenhum owner configurado; não foi possível enviar a mensagem.")
        return False
    try:
        resp = requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": target, "text": texto})
        return resp.ok
    except Exception as e:
        print("⚠️ Erro ao enviar mensagem:", e)
        return False

# Regex para placas
placa_regex = r"[A-Z]{3}\d{4}|[A-Z]{4}\d{3}"

# === ROTA PRINCIPAL DO WEBHOOK ===
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    criar_banco()
    update = request.get_json()

    if "message" not in update:
        return {"ok": True}

    message = update["message"]
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    if not text:
        return {"ok": True}

    text = text.strip()
    lower_text = text.lower()

    # Registrar chat como owner
    if lower_text.startswith("/register") or lower_text.startswith("/me"):
        set_owner_chat_id(chat_id)
        enviar_mensagem(chat_id, "✅ Chat registrado como owner.")
        return {"ok": True}

    if lower_text.startswith("/id"):
        enviar_mensagem(chat_id, f"Seu chat_id é: {chat_id}")
        return {"ok": True}

    # Registrar manutenção
    if "placa:" in lower_text and "tipo:" in lower_text and "descricao:" in lower_text and "data" in lower_text:
        try:
            match = re.search(
                r"placa:\s*([A-Za-z]{3}\d{4}|[A-Za-z]{4}\d{3}).*tipo:\s*([^\s,]+).*descricao:\s*(.+?)\s*,?\s*data[:\s]*([\d/]+)",
                text, re.IGNORECASE)
            if not match:
                raise ValueError("Formato inválido")

            placa = match.group(1).upper()
            tipo = match.group(2)
            descricao = match.group(3).strip()
            data_manut = match.group(4)

            adicionar_manutencao(placa, tipo, descricao, data_manut)

            msg = f"✅ Manutenção registrada:\n🚗 Placa: {placa}\n🛠 Tipo: {tipo}\n📝 Descrição: {descricao}\n📅 Data: {data_manut}"
            enviar_mensagem(chat_id, msg)

            # Notificar owner
            if chat_id != get_owner_chat_id():
                enviar_mensagem(None, f"📢 Nova manutenção registrada!\n{msg}")

        except Exception:
            enviar_mensagem(chat_id, "❌ Erro ao registrar. Use:\nplaca: XXX1234 , tipo: troca_oleo , descricao: trocou filtro e óleo , data: 19/09/2025")
        return {"ok": True}

    # Última manutenção (só a placa)
    if re.fullmatch(placa_regex, text.upper()):
        registro = ultima_manutencao(text)
        if registro:
            enviar_mensagem(chat_id,
                             f"📌 Última manutenção da placa {text.upper()}:\n🛠 {registro[1]} - 📝 {registro[2]} - 📅 {registro[3]}")
        else:
            enviar_mensagem(chat_id, f"🚫 Nenhuma manutenção registrada para {text.upper()}")
        return {"ok": True}

    # Histórico
    if lower_text.startswith("/historico"):
        try:
            _, placa = lower_text.split()
            registros = historico_manutencao(placa)
            if registros:
                resposta = f"📋 Histórico da placa {placa.upper()}:\n"
                for tipo, descricao, data in registros:
                    resposta += f"🛠 {tipo} | 📝 {descricao} | 📅 {data}\n"
                enviar_mensagem(chat_id, resposta)
            else:
                enviar_mensagem(chat_id, f"🚫 Nenhuma manutenção para {placa.upper()}")
        except:
            enviar_mensagem(chat_id, "❌ Use: /historico PLACA")
        return {"ok": True}

    # Listar todas
    if lower_text.startswith("/todas"):
        registros = listar_todas()
        if not registros:
            enviar_mensagem(chat_id, "⚠️ Nenhuma manutenção registrada ainda.")
        else:
            resposta = "📋 Todas as manutenções:\n\n"
            for placa, tipo, descricao, data in registros:
                resposta += f"🚗 {placa} | 🛠 {tipo} | 📝 {descricao} | 📅 {data}\n"
            enviar_mensagem(chat_id, resposta)
        return {"ok": True}

    # Ajuda
    enviar_mensagem(chat_id,
                    "🤖 Comandos:\n"
                    "• Registrar manutenção:\nplaca: XXX1234 , tipo: troca_oleo , descricao: trocou filtro e óleo , data: 19/09/2025\n"
                    "• Última manutenção: digite apenas a PLACA\n"
                    "• Histórico: /historico PLACA\n"
                    "• Listar todas as manutenções: /todas\n"
                    "• Registrar este chat como owner: /register\n"
                    "• Ver seu chat id: /id")

    return {"ok": True}


# === INICIAR O FLASK ===
if __name__ == "__main__":
    criar_banco()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
