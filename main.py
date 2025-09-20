import time
import requests
import sqlite3
import os

# === CONFIGURAÇÕES DO TELEGRAM ===
TOKEN = "8388692555:AAGTTvCesG7OvargMGb0vpEam90RFLqhDxk"   # coloque o token do BotFather
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# === BANCO DE DADOS ===
DB_PATH = "pneus.db"
OWNER_FILE = "owner_chat_id.txt"  # arquivo onde gravamos o chat_id do dono

def criar_banco():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS pneus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            placa TEXT NOT NULL,
            pneus TEXT NOT NULL,
            data TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def adicionar_troca(placa, pneus, data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO pneus (placa, pneus, data) VALUES (?, ?, ?)", (placa.upper(), pneus, data))
    conn.commit()
    conn.close()

def ultima_troca(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, data, pneus FROM pneus WHERE placa=? ORDER BY id DESC LIMIT 1", (placa.upper(),))
    row = c.fetchone()
    conn.close()
    return row

def historico_trocas(placa):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT data, pneus FROM pneus WHERE placa=? ORDER BY id DESC", (placa.upper(),))
    rows = c.fetchall()
    conn.close()
    return rows

def editar_troca(placa, novos_pneus, nova_data):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id FROM pneus WHERE placa=? ORDER BY id DESC LIMIT 1", (placa.upper(),))
    row = c.fetchone()
    if row:
        c.execute("UPDATE pneus SET pneus=?, data=? WHERE id=?", (novos_pneus, nova_data, row[0]))
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False

# --- Owner (para enviar mensagens pro seu chat mesmo sem update ativo) ---
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

# enviar mensagem: se chat_id for None, usa owner salvo
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

# === Loop de long polling ===
def main():
    criar_banco()
    offset = None  # controla a última mensagem lida

    print("🤖 Bot iniciado (long polling). Envie /register para salvar seu chat_id como owner.")

    while True:
        try:
            resp = requests.get(f"{BASE_URL}/getUpdates", params={"offset": offset, "timeout": 20}).json()
        except Exception as e:
            print("⚠️ Erro ao conectar no Telegram:", e)
            time.sleep(5)
            continue
        
        for update in resp.get("result", []):
            offset = update["update_id"] + 1
            message = update.get("message", {})
            chat_id = message.get("chat", {}).get("id")
            text = message.get("text", "")
            if not text:
                continue

            text = text.strip()
            lower_text = text.lower()

            # COMANDO: registrar este chat como o "owner"
            if lower_text.startswith("/register") or lower_text.startswith("/me"):
                set_owner_chat_id(chat_id)
                enviar_mensagem(chat_id, "✅ Chat registrado como owner. Agora o bot enviará notificações para este chat.")
                continue

            if lower_text.startswith("/id"):
                enviar_mensagem(chat_id, f"Seu chat_id é: {chat_id}")
                continue

            # Registrar troca
            if "placa:" in lower_text and "pneus:" in lower_text and "data" in lower_text:
                try:
                    partes = lower_text.replace(",", "").split()
                    placa = partes[1]
                    qtd = partes[3]
                    tipo = partes[4]
                    data_troca = partes[6]

                    pneus = f"{qtd} {tipo}"
                    adicionar_troca(placa, pneus, data_troca)

                    msg_registro = f"✅ Troca registrada:\n🚗 Placa: {placa.upper()}\n🛞 Pneus: {pneus}\n📅 Data: {data_troca}"
                    enviar_mensagem(chat_id, msg_registro)

                    # 🔔 Notificação automática para o owner
                    if chat_id != get_owner_chat_id():
                        enviar_mensagem(None, f"📢 Nova troca registrada!\n{msg_registro}")

                except Exception:
                    enviar_mensagem(chat_id, "❌ Erro ao registrar troca. Use:\nplaca: XXX1234 , pneus: 2 dianteiro , data: 19/09/2025")
                continue

            # Editar última troca
            if lower_text.startswith("/editar"):
                try:
                    partes = lower_text.split()
                    placa = partes[2]
                    qtd = partes[4]
                    tipo = partes[5]
                    nova_data = partes[7]

                    novos_pneus = f"{qtd} {tipo}"
                    if editar_troca(placa, novos_pneus, nova_data):
                        enviar_mensagem(chat_id, f"✏️ Última troca da placa {placa.upper()} foi atualizada:\n🛞 {novos_pneus}\n📅 {nova_data}")
                    else:
                        enviar_mensagem(chat_id, f"🚫 Nenhum registro encontrado para {placa.upper()}")
                except Exception:
                    enviar_mensagem(chat_id, "❌ Erro ao editar. Use:\n/editar placa XXX1234 pneus 4 traseiro data 20/09/2025")
                continue

            # Última troca (só digitando a placa)
            if len(text) == 7:
                registro = ultima_troca(text)
                if registro:
                    enviar_mensagem(chat_id, f"📌 Última troca da placa {text.upper()}:\n📅 {registro[1]} - 🛞 {registro[2]}")
                else:
                    enviar_mensagem(chat_id, f"🚫 Nenhuma troca registrada para {text.upper()}")
                continue

            # Histórico
            if lower_text.startswith("/historico"):
                try:
                    _, placa = lower_text.split()
                    registros = historico_trocas(placa)
                    if registros:
                        resposta = f"📋 Histórico da placa {placa.upper()}:\n"
                        for r in registros:
                            resposta += f"📅 {r[0]} - 🛞 {r[1]}\n"
                        enviar_mensagem(chat_id, resposta)
                    else:
                        enviar_mensagem(chat_id, f"🚫 Nenhum registro para {placa.upper()}")
                except:
                    enviar_mensagem(chat_id, "❌ Use: /historico PLACA")
                continue

            # Ajuda
            enviar_mensagem(chat_id, "🤖 Comandos:\n"
                                     "• Registrar troca:\nplaca: XXX1234 , pneus: 2 dianteiro , data: 19/09/2025\n"
                                     "• Última troca: digite apenas a PLACA\n"
                                     "• Histórico: /historico PLACA\n"
                                     "• Editar última troca: /editar placa XXX1234 pneus 4 traseiro data 20/09/2025\n"
                                     "• Registrar este chat como owner: /register\n"
                                     "• Ver seu chat id: /id")

        time.sleep(1)

if __name__ == "__main__":
    main()
