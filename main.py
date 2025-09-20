import time
import requests
import sqlite3
import os

# === CONFIGURAÇÕES DO TELEGRAM ===
TOKEN = "8269161965:AAGJ8YMTErLaPw7zWIfxuNHf71wI2YimLyI"
BASE_URL = f"https://api.telegram.org/bot{TOKEN}"

# === BANCO DE DADOS ===
DB_PATH = "manutencoes.db"
OWNER_FILE = "owner_chat_id.txt"  # arquivo onde gravamos o chat_id do dono

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

            # COMANDO: registrar este chat como owner
            if lower_text.startswith("/register") or lower_text.startswith("/me"):
                set_owner_chat_id(chat_id)
                enviar_mensagem(chat_id, "✅ Chat registrado como owner. Agora o bot enviará notificações para este chat.")
                continue

            if lower_text.startswith("/id"):
                enviar_mensagem(chat_id, f"Seu chat_id é: {chat_id}")
                continue

            # Registrar manutenção
            if "placa:" in lower_text and "tipo:" in lower_text and "descricao:" in lower_text and "data:" in lower_text and "km:" in lower_text:
                try:
                    partes = lower_text.replace(",", "").split()
                    placa = partes[1]
                    tipo = partes[3]
                    descricao_index_start = partes.index("descricao")+1
                    data_index = partes.index("data")
                    descricao = " ".join(partes[descricao_index_start:data_index])
                    data = partes[data_index+1]
                    km = int(partes[partes.index("km")+1])

                    adicionar_manutencao(placa, tipo, descricao, data, km)

                    msg_registro = f"✅ Manutenção registrada:\n🚗 Placa: {placa.upper()}\n🔧 Tipo: {tipo}\n📝 Descrição: {descricao}\n📅 Data: {data}\n📏 KM: {km}"
                    enviar_mensagem(chat_id, msg_registro)

                    # 🔔 Notificação automática para o owner
                    if chat_id != get_owner_chat_id():
                        enviar_mensagem(None, f"📢 Nova manutenção registrada!\n{msg_registro}")

                except Exception:
                    enviar_mensagem(chat_id, "❌ Erro ao registrar manutenção.\nUse:\nplaca: XXX1234 , tipo: troca_oleo , descricao: filtro trocado , data: 19/09/2025 , km: 12345")
                continue

            # Editar última manutenção
            if lower_text.startswith("/editar"):
                try:
                    partes = lower_text.split()
                    placa = partes[2]
                    tipo = partes[4]
                    descricao_index_start = partes.index("descricao")+1
                    data_index = partes.index("data")
                    descricao = " ".join(partes[descricao_index_start:data_index])
                    data = partes[data_index+1]
                    km = int(partes[partes.index("km")+1])

                    if editar_manutencao(placa, tipo, descricao, data, km):
                        enviar_mensagem(chat_id, f"✏️ Última manutenção da placa {placa.upper()} foi atualizada:\n🔧 {tipo}\n📝 {descricao}\n📅 {data}\n📏 KM: {km}")
                    else:
                        enviar_mensagem(chat_id, f"🚫 Nenhum registro encontrado para {placa.upper()}")
                except Exception:
                    enviar_mensagem(chat_id, "❌ Erro ao editar.\nUse:\n/editar placa XXX1234 tipo troca_oleo descricao filtro trocado data 20/09/2025 km 12345")
                continue

            # Última manutenção (só digitando a placa)
            if len(text.replace(" ", "")) in [7,8]:  # placas padrão 3 letras+4 números ou 4 letras+3 números
                registro = ultima_manutencao(text)
                if registro:
                    enviar_mensagem(chat_id, f"📌 Última manutenção da placa {text.upper()}:\n🔧 {registro[1]}\n📝 {registro[2]}\n📅 {registro[3]}\n📏 KM: {registro[4]}")
                else:
                    enviar_mensagem(chat_id, f"🚫 Nenhuma manutenção registrada para {text.upper()}")
                continue

            # Histórico
            if lower_text.startswith("/historico"):
                try:
                    _, placa = lower_text.split()
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
                continue

            # Ajuda
            enviar_mensagem(chat_id, "🤖 Comandos:\n"
                                     "• Registrar manutenção:\nplaca: XXX1234 , tipo: troca_oleo , descricao: filtro trocado , data: 19/09/2025 , km: 12345\n"
                                     "• Última manutenção: digite apenas a PLACA\n"
                                     "• Histórico: /historico PLACA\n"
                                     "• Editar última manutenção: /editar placa XXX1234 tipo troca_oleo descricao filtro trocado data 20/09/2025 km 12345\n"
                                     "• Registrar este chat como owner: /register\n"
                                     "• Ver seu chat id: /id")

        time.sleep(1)

if __name__ == "__main__":
    main()
