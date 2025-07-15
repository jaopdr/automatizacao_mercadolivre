import os
import time
import json
import requests
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from dotenv import load_dotenv
from tkinter import Tk, Button, Label, messagebox

# Carrega variáveis de ambiente do .env
load_dotenv()
TOLI_USER = os.getenv("TOLI_USER")
TOLI_PASS = os.getenv("TOLI_PASS").strip('"')
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

chrome_options = Options()
driver = webdriver.Chrome(options=chrome_options)

def renovar_token():
    print("[↻] Renovando token de acesso...")
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
        print("[✓] Novo token obtido com sucesso.")

        # Atualiza o .env
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
        print("[📁] .env atualizado.")
    else:
        print("❌ Erro ao renovar token:", res.status_code, res.text)
        messagebox.showerror("Erro", "Falha ao renovar token do Mercado Livre.")

def login_toli():
    print("[+] Acessando site da Toli...")
    driver.get("https://portal.tolidistribuidora.com.br")

    print("[+] Preenchendo campos de login...")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "P9998_USERNAME")))
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "P9998_CNPJ")))

    usuario_input = driver.find_element(By.ID, "P9998_USERNAME")
    cnpj_input = driver.find_element(By.ID, "P9998_CNPJ")

    usuario_input.clear()
    usuario_input.send_keys(TOLI_USER)

    cnpj_input.clear()
    cnpj_input.send_keys(TOLI_PASS)

    driver.find_element(By.ID, "btnEntrar").click()

    print("[!] Aguardando autenticação de 2 fatores (insira manualmente)...")
    input("Pressione Enter após confirmar o 2FA manualmente no navegador...")
    print("[✓] Login completo. Continuando a automação...")

def extrair_produtos():
    produtos = []
    cards = driver.find_elements(By.CLASS_NAME, "produto-card")  # ajuste o seletor
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
    for p in produtos:
        preco_ml = buscar_preco_ml(p['title'])
        p['price_ml'] = preco_ml
        p['margem'] = preco_ml - p['price_toli']
        p['vale_a_pena'] = p['margem'] > 20

    df = pd.DataFrame(produtos)
    df.to_excel("comparativo_produtos.xlsx", index=False)
    messagebox.showinfo("Planilha Gerada", "Arquivo 'comparativo_produtos.xlsx' salvo com sucesso.")
    return produtos

def publicar_ml(produto):
    global ML_ACCESS_TOKEN  # usa token atualizado

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
        "pictures": [
            {"source": produto["image"]}
        ]
    }

    url = f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}"
    res = requests.post(url, json=item)

    if res.status_code == 401:
        print("[!] Token expirado. Tentando renovar...")
        renovar_token()
        url = f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}"
        res = requests.post(url, json=item)

    return res.status_code == 201

def enviar_valem(produtos):
    enviados = [p for p in produtos if p['vale_a_pena']]
    for p in enviados:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluído", f"{len(enviados)} produtos enviados que valem a pena.")

def enviar_todos(produtos):
    for p in produtos:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluído", "Todos os produtos foram enviados.")

def excluir_todos_ml():
    global ML_ACCESS_TOKEN

    confirmacao = messagebox.askyesno("Confirmação", "Tem certeza que deseja excluir TODOS os produtos da sua conta do Mercado Livre?")
    if not confirmacao:
        return

    print("[🗑️] Buscando produtos ativos na conta...")
    url = f"https://api.mercadolibre.com/users/me?access_token={ML_ACCESS_TOKEN}"
    res = requests.get(url)

    if res.status_code != 200:
        messagebox.showerror("Erro", "Não foi possível obter o ID do usuário.")
        return

    user_id = res.json().get("id")

    search_url = f"https://api.mercadolibre.com/users/{user_id}/items/search?access_token={ML_ACCESS_TOKEN}&status=active"
    res = requests.get(search_url)

    if res.status_code != 200:
        messagebox.showerror("Erro", "Erro ao buscar itens ativos.")
        return

    item_ids = res.json().get("results", [])
    print(f"[ℹ️] Encontrados {len(item_ids)} itens ativos.")

    deletados = 0
    for item_id in item_ids:
        url = f"https://api.mercadolibre.com/items/{item_id}?access_token={ML_ACCESS_TOKEN}"
        res = requests.delete(url)
        if res.status_code == 200:
            deletados += 1
        elif res.status_code == 401:
            renovar_token()
            url = f"https://api.mercadolibre.com/items/{item_id}?access_token={ML_ACCESS_TOKEN}"
            res = requests.delete(url)
            if res.status_code == 200:
                deletados += 1

    messagebox.showinfo("Exclusão Concluída", f"{deletados} produtos excluídos com sucesso.")

def executar_fluxo():
    login_toli()
    produtos = extrair_produtos()
    produtos = comparar_e_gerar_planilha(produtos)

    janela = Tk()
    janela.title("Publicação Mercado Livre")
    Label(janela, text="Planilha gerada com sucesso!").pack(pady=10)
    Button(janela, text="Enviar apenas os que valem a pena", command=lambda: enviar_valem(produtos)).pack(pady=5)
    Button(janela, text="Enviar todos os produtos", command=lambda: enviar_todos(produtos)).pack(pady=5)
    Button(janela, text="Excluir TODOS os produtos do Mercado Livre", command=excluir_todos_ml).pack(pady=5)
    janela.mainloop()
    driver.quit()

if __name__ == "__main__":
    executar_fluxo()