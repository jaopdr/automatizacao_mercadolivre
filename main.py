import os
import time
import json
import requests
import pandas as pd
from tkinter import Tk, Button, Label, messagebox
from tkinter.scrolledtext import ScrolledText
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from dotenv import load_dotenv

# === GUI inicial ===
janela = Tk()
janela.title("Automação Mercado Livre")

log_text = ScrolledText(janela, width=100, height=20, state='disabled', wrap='word')
log_text.pack(padx=10, pady=10)

autenticado = False
botao_continuar = None

def log(msg):
    log_text.config(state='normal')
    log_text.insert('end', msg + '\n')
    log_text.see('end')
    log_text.config(state='disabled')
    janela.update()

def confirmar_autenticacao():
    global autenticado
    autenticado = True
    log("[✓] Autenticação manual confirmada. Continuando...")
    if botao_continuar:
        botao_continuar.pack_forget()

# === Variáveis .env ===
load_dotenv()
TOLI_USER = os.getenv("TOLI_USER")
TOLI_PASS = os.getenv("TOLI_PASS").strip('"')
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# === ChromeDriver setup ===
chrome_options = Options()
driver = webdriver.Chrome(options=chrome_options)

def digitar_com_pausa(elemento, texto, pausa=0.05):
    for char in texto:
        elemento.send_keys(char)
        time.sleep(pausa)

def login_toli():
    log("[+] Acessando site da Toli...")
    driver.get("https://portal.tolidistribuidora.com.br")

    log("[+] Preenchendo campos de login...")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "P9998_USERNAME")))
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "P9998_CNPJ")))

    usuario_input = driver.find_element(By.ID, "P9998_USERNAME")
    usuario_input.clear()
    usuario_input.send_keys(TOLI_USER)

    cnpj_input = driver.find_element(By.ID, "P9998_CNPJ")
    cnpj_input.click()
    cnpj_input.clear()
    cnpj_input.send_keys(Keys.CONTROL + "a")
    cnpj_input.send_keys(Keys.DELETE)
    digitar_com_pausa(cnpj_input, TOLI_PASS)

    driver.find_element(By.ID, "btnEntrar").click()

    log("[!] Aguardando autenticação de 2 fatores (faça no navegador)...")
    global botao_continuar
    botao_continuar = Button(janela, text="Continuar após autenticação", command=confirmar_autenticacao)
    botao_continuar.pack(pady=10)

    while not autenticado:
        janela.update()
        time.sleep(0.1)

def renovar_token():
    log("[↻] Renovando token de acesso...")
    global ML_ACCESS_TOKEN, ML_REFRESH_TOKEN

    data = {
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": ML_REFRESH_TOKEN
    }

    res = requests.post("https://api.mercadolibre.com/oauth/token", data=data)
    if res.status_code == 200:
        token_data = res.json()
        ML_ACCESS_TOKEN = token_data["access_token"]
        ML_REFRESH_TOKEN = token_data.get("refresh_token", ML_REFRESH_TOKEN)
        log("[✓] Novo token obtido com sucesso.")

        with open(".env", "r") as f:
            linhas = f.readlines()

        with open(".env", "w") as f:
            for linha in linhas:
                if linha.startswith("ML_ACCESS_TOKEN="):
                    f.write(f"ML_ACCESS_TOKEN={ML_ACCESS_TOKEN}\n")
                elif linha.startswith("ML_REFRESH_TOKEN="):
                    f.write(f"ML_REFRESH_TOKEN={ML_REFRESH_TOKEN}\n")
                else:
                    f.write(linha)
        log("[📁] .env atualizado.")
    else:
        log(f"❌ Erro ao renovar token: {res.status_code} {res.text}")
        messagebox.showerror("Erro", "Falha ao renovar token do Mercado Livre.")

def extrair_produtos():
    log("[📦] Extraindo produtos da Toli...")
    produtos = []
    cards = driver.find_elements(By.CLASS_NAME, "produto-card")
    for card in cards:
        nome = card.find_element(By.CLASS_NAME, "titulo").text
        preco = card.find_element(By.CLASS_NAME, "preco").text.replace("R$", "").replace(",", ".")
        imagem = card.find_element(By.TAG_NAME, "img").get_attribute("src")
        produtos.append({
            "title": nome,
            "price_toli": float(preco),
            "image": imagem,
            "description": "Produto da Toli",
            "stock": 10
        })
    log(f"[✓] {len(produtos)} produtos extraídos.")
    return produtos

def buscar_preco_ml(titulo):
    url = f"https://api.mercadolibre.com/sites/MLB/search?q={titulo}"
    res = requests.get(url)
    if res.status_code == 200:
        resultados = res.json().get("results")
        if resultados:
            return float(resultados[0].get("price", 0))
    return 0.0

def comparar_e_gerar_planilha(produtos):
    log("[🔎] Comparando preços com Mercado Livre...")
    for p in produtos:
        preco_ml = buscar_preco_ml(p['title'])
        p['price_ml'] = preco_ml
        p['margem'] = preco_ml - p['price_toli']
        p['vale_a_pena'] = p['margem'] > 20

    df = pd.DataFrame(produtos)
    df.to_excel("comparativo_produtos.xlsx", index=False)
    log("[📁] Planilha 'comparativo_produtos.xlsx' salva com sucesso.")
    messagebox.showinfo("Planilha Gerada", "Arquivo salvo com sucesso.")
    return produtos

def publicar_ml(produto):
    global ML_ACCESS_TOKEN

    item = {
        "title": produto["title"],
        "category_id": "MLB3530",
        "price": produto["price_toli"] + 30,
        "currency_id": "BRL",
        "available_quantity": produto["stock"],
        "buying_mode": "buy_it_now",
        "listing_type_id": "gold_special",
        "condition": "new",
        "description": {
            "plain_text": produto["description"]
        },
        "pictures": [{"source": produto["image"]}]
    }

    url = f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}"
    res = requests.post(url, json=item)

    if res.status_code == 401:
        log("[!] Token expirado. Renovando...")
        renovar_token()
        url = f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}"
        res = requests.post(url, json=item)

    if res.status_code == 201:
        log(f"[↑] Produto publicado: {produto['title']}")
        return True
    else:
        log(f"[✖] Falha ao publicar: {produto['title']} ({res.status_code})")
        return False

def enviar_valem(produtos):
    enviados = [p for p in produtos if p['vale_a_pena']]
    for p in enviados:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluído", f"{len(enviados)} produtos enviados.")
    log(f"[✓] {len(enviados)} produtos publicados (valem a pena).")

def enviar_todos(produtos):
    for p in produtos:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluído", "Todos os produtos foram enviados.")
    log("[✓] Todos os produtos foram enviados.")

def excluir_todos_ml():
    global ML_ACCESS_TOKEN

    confirmacao = messagebox.askyesno("Confirmação", "Tem certeza que deseja excluir TODOS os produtos do Mercado Livre?")
    if not confirmacao:
        return

    log("[🗑️] Buscando produtos ativos...")
    res = requests.get(f"https://api.mercadolibre.com/users/me?access_token={ML_ACCESS_TOKEN}")
    if res.status_code != 200:
        messagebox.showerror("Erro", "Erro ao obter ID do usuário.")
        return

    user_id = res.json().get("id")
    search_url = f"https://api.mercadolibre.com/users/{user_id}/items/search?access_token={ML_ACCESS_TOKEN}&status=active"
    res = requests.get(search_url)

    if res.status_code != 200:
        messagebox.showerror("Erro", "Erro ao buscar itens.")
        return

    item_ids = res.json().get("results", [])
    log(f"[ℹ️] Encontrados {len(item_ids)} itens ativos.")

    deletados = 0
    for item_id in item_ids:
        url = f"https://api.mercadolibre.com/items/{item_id}?access_token={ML_ACCESS_TOKEN}"
        res = requests.delete(url)
        if res.status_code == 200:
            deletados += 1
        elif res.status_code == 401:
            renovar_token()
            res = requests.delete(url)
            if res.status_code == 200:
                deletados += 1

    messagebox.showinfo("Exclusão Concluída", f"{deletados} produtos excluídos.")
    log(f"[✓] {deletados} produtos excluídos do Mercado Livre.")

def executar_fluxo():
    login_toli()
    produtos = extrair_produtos()
    produtos = comparar_e_gerar_planilha(produtos)

    Label(janela, text="Escolha uma ação:").pack(pady=10)
    Button(janela, text="Enviar apenas os que valem a pena", command=lambda: enviar_valem(produtos)).pack(pady=5)
    Button(janela, text="Enviar todos os produtos", command=lambda: enviar_todos(produtos)).pack(pady=5)
    Button(janela, text="Excluir TODOS os produtos do Mercado Livre", command=excluir_todos_ml).pack(pady=5)

    driver.quit()

# === Inicia o processo ===
executar_fluxo()
janela.mainloop()