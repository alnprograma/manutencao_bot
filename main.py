from flask import Flask, request
import requests
import sqlite3
import os

# === CONFIGURAÇÕES DO TELEGRAM ===
TOKEN = "8269161965:AAGJ8YMTErLaPw7zWIfxuNHf71wI2YimLyI"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# === BANCO DE DADOS ===
DB_PATH = "manutencoes.db"
OWNER_FILE = "owner_chat_id.txt"

app = Flask(__name__)

# ------------------- BANCO DE DADOS -------------------
def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS manutencoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT NOT NULL,
            tipo TEXT NOT NULL,
            descricao TEXT NOT NULL,
            data TEXT NOT NULL,
            km INTEGER NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def adicionar_manutencao(placa, tipo, descricao, data, km):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO manutencoes (placa, tipo, descricao, data, km) VALUES (?, ?, ?, ?, ?)",
              (placa.upper(), tipo, descricao, data, km))
    conn.commit()
    conn.close()

def ultima_manutencao(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, tipo, descricao, data, km FROM manutencoes WHERE placa=? ORDER BY id DESC LIMIT 1", (placa.upper(),))
    row = c.fetchone()
    conn.close()
    return row

def historico_manutencoes(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT tipo, descricao, data, km FROM manutencoes WHERE placa=? ORDER BY id DESC", (placa.upper(),))
    rows = c.fetchall()
    conn.close()
    return rows

def editar_manutencao(placa, novo_tipo, nova_descricao, nova_data, novo_km):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM manutencoes WHERE placa=? ORDER BY id DESC LIMIT 1", (placa.upper(),))
    row = c.fetchone()
    if row:
        c.execute("UPDATE manutencoes SET tipo=?, descricao=?, data=?, km=? WHERE id=?", 
                  (novo_tipo, nova_descricao, nova_data, novo_km, row[0]))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# ------------------- OWNER -------------------
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

# ------------------- TELEGRAM -------------------
def enviar_mensagem(chat_id, texto):
    target = chat_id if chat_id else get_owner_chat_id()
    if not target:
        print("⚠️ Nenhum owner configurado; não foi possível enviar a mensagem.")
        return False
    try:
        resp = requests.post(f"{BASE_URL}/sendMessage", data={"chat_id": target, "text": texto})
        return resp.ok
    except Exception as e:
        print("⚠️ Erro ao enviar mensagem:", e)
        return False

# ------------------- WEBHOOK -------------------
@app.route(f"/{TOKEN}", methods=["POST"])
def webhook():
    criar_banco()
    update = request.json
    message = update.get("message")
    if not message:
        return "ok"
    
    chat_id = message["chat"]["id"]
    text = message.get("text", "")
    if not text:
        return "ok"

    text_lower = text.lower().strip()

    # Registrar este chat como owner
    if text_lower.startswith("/register") or text_lower.startswith("/me"):
        set_owner_chat_id(chat_id)
        enviar_mensagem(chat_id, "✅ Chat registrado como owner.")
        return "ok"

    if text_lower.startswith("/id"):
        enviar_mensagem(chat_id, f"Seu chat_id é: {chat_id}")
        return "ok"

    # Registrar manutenção
    if all(x in text_lower for x in ["placa:", "tipo:", "descricao:", "data:", "km:"]):
        try:
            partes = text_lower.replace(",", "").split()
            placa = partes[partes.index("placa:")+1]
            tipo = partes[partes.index("tipo:")+1]
            descricao_index_start = partes.index("descricao:")+1
            data_index = partes.index("data:")
            descricao = " ".join(partes[descricao_index_start:data_index])
            data = partes[data_index+1]
            km = int(partes[partes.index("km:")+1])

            adicionar_manutencao(placa, tipo, descricao, data, km)
            msg = f"✅ Manutenção registrada:\n🚗 Placa: {placa.upper()}\n🔧 Tipo: {tipo}\n📝 Descrição: {descricao}\n📅 Data: {data}\n📏 KM: {km}"
            enviar_mensagem(chat_id, msg)
            if chat_id != get_owner_chat_id():
                enviar_mensagem(None, f"📢 Nova manutenção registrada!\n{msg}")
        except Exception:
            enviar_mensagem(chat_id, "❌ Erro ao registrar manutenção.\nUse:\nplaca: XXX1234 , tipo: troca_oleo , descricao: filtro trocado , data: 19/09/2025 , km: 12345")
        return "ok"

    # Editar última manutenção
    if text_lower.startswith("/editar"):
        try:
            partes = text_lower.split()
            placa = partes[2]
            tipo = partes[4]
            descricao_index_start = partes.index("descricao")+1
            data_index = partes.index("data")
            descricao = " ".join(partes[descricao_index_start:data_index])
            data = partes[data_index+1]
            km = int(partes[partes.index("km")+1])
            if editar_manutencao(placa, tipo, descricao, data, km):
                enviar_mensagem(chat_id, f"✏️ Última manutenção da placa {placa.upper()} atualizada.")
            else:
                enviar_mensagem(chat_id, f"🚫 Nenhum registro encontrado para {placa.upper()}")
        except Exception:
            enviar_mensagem(chat_id, "❌ Erro ao editar. Use:\n/editar placa XXX1234 tipo troca_oleo descricao filtro trocado data 20/09/2025 km 12345")
        return "ok"

    # Última manutenção (só digitando a placa)
    if len(text.replace(" ","")) in [7,8]:  # placas padrão 3L+4N ou 4L+3N
        registro = ultima_manutencao(text)
        if registro:
            enviar_mensagem(chat_id, f"📌 Última manutenção da placa {text.upper()}:\n🔧 {registro[1]}\n📝 {registro[2]}\n📅 {registro[3]}\n📏 KM: {registro[4]}")
        else:
            enviar_mensagem(chat_id, f"🚫 Nenhuma manutenção registrada para {text.upper()}")
        return "ok"

    # Histórico
    if text_lower.startswith("/historico"):
        try:
            _, placa = text_lower.split()
            registros = historico_manutencoes(placa)
            if registros:
                resposta = f"📋 Histórico da placa {placa.upper()}:\n"
                for r in registros:
                    resposta += f"🔧 {r[0]} - 📝 {r[1]} - 📅 {r[2]} - 📏 KM: {r[3]}\n"
                enviar_mensagem(chat_id, resposta)
            else:
                enviar_mensagem(chat_id, f"🚫 Nenhum registro para {placa.upper()}")
        except:
            enviar_mensagem(chat_id, "❌ Use: /historico PLACA")
        return "ok"

    # Ajuda
    enviar_mensagem(chat_id, "🤖 Comandos:\n"
                             "• Registrar manutenção:\nplaca: XXX1234 , tipo: troca_oleo , descricao: filtro trocado , data: 19/09/2025 , km: 12345\n"
                             "• Última manutenção: digite apenas a PLACA\n"
                             "• Histórico: /historico PLACA\n"
                             "• Editar última manutenção: /editar placa XXX1234 tipo troca_oleo descricao filtro trocado data 20/09/2025 km 12345\n"
                             "• Registrar este chat como owner: /register\n"
                             "• Ver seu chat id: /id")
    return "ok"

@app.route("/")
def index():
    return "Bot rodando!"

if __name__ == "__main__":
    criar_banco()
    app.run(host="0.0.0.0", port=8080)
