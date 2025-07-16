import os
import time
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
janela.title("Automacao Mercado Livre")
log_text = ScrolledText(janela, width=100, height=20, state='disabled', wrap='word')
log_text.pack(padx=10, pady=10)
autenticado = False
botao_continuar = None

# === Funcoes auxiliares ===
def log(msg):
    log_text.config(state='normal')
    log_text.insert('end', msg + '\n')
    log_text.see('end')
    log_text.config(state='disabled')
    janela.update()

def confirmar_autenticacao():
    global autenticado
    autenticado = True
    log("[✓] Autenticacao manual confirmada. Continuando...")
    if botao_continuar:
        botao_continuar.pack_forget()

def digitar_com_pausa(elemento, texto, pausa=0.05):
    for char in texto:
        elemento.send_keys(char)
        time.sleep(pausa)

# === Variaveis .env ===
load_dotenv()
TOLI_USER = os.getenv("TOLI_USER")
TOLI_PASS = os.getenv("TOLI_PASS").strip('"')
ML_ACCESS_TOKEN = os.getenv("ML_ACCESS_TOKEN")
ML_REFRESH_TOKEN = os.getenv("ML_REFRESH_TOKEN")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")

# === Webdriver setup ===
chrome_options = Options()
driver = webdriver.Chrome(options=chrome_options)

# === Autenticacao Toli ===
def login_toli():
    log("[+] Acessando site da Toli...")
    driver.get("https://portal.tolidistribuidora.com.br")
    WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "P9998_USERNAME")))
    driver.find_element(By.ID, "P9998_USERNAME").send_keys(TOLI_USER)
    input_cnpj = driver.find_element(By.ID, "P9998_CNPJ")
    input_cnpj.click()
    input_cnpj.clear()
    input_cnpj.send_keys(Keys.CONTROL + "a", Keys.DELETE)
    digitar_com_pausa(input_cnpj, TOLI_PASS)
    driver.find_element(By.ID, "btnEntrar").click()
    log("[!] Aguardando autenticacao de 2 fatores (faça no navegador)...")
    global botao_continuar
    botao_continuar = Button(janela, text="Continuar apos autenticacao", command=confirmar_autenticacao)
    botao_continuar.pack(pady=10)
    while not autenticado:
        janela.update()
        time.sleep(0.1)

# === Scroll ===
def scroll_ate_carregar_todos():
    altura_anterior = 0
    tentativas_sem_novidade = 0
    while tentativas_sem_novidade < 5:
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        altura_atual = driver.execute_script("return document.body.scrollHeight;")
        if altura_atual == altura_anterior:
            tentativas_sem_novidade += 1
        else:
            tentativas_sem_novidade = 0
            altura_anterior = altura_atual

# === Extracao Produtos ===
def extrair_produtos():
    log("[📦] Extraindo produtos da Toli...")
    produtos = []
    cards = driver.find_elements(By.CSS_SELECTOR, "li.a-CardView-item")
    for card in cards:
        try:
            nome = card.find_element(By.CSS_SELECTOR, "a.a-CardView-subTitle").text.strip()
            preco_txt = card.find_element(By.XPATH, ".//span[contains(text(),'R$')]").text
            preco_float = float(preco_txt.replace("R$", "").replace(".", "").replace(",", "."))
            imagem = card.find_element(By.CSS_SELECTOR, "div#container_img img").get_attribute("src")
            try:
                marca = card.find_element(By.ID, "span_marca").text.strip()
                if not marca:
                    marca = "Generico"
            except:
                marca = "Generico"
            produtos.append({
                "title": nome,
                "price_toli": preco_float,
                "image": imagem,
                "description": "Produto da Toli",
                "stock": 10,
                "brand": marca
            })
        except Exception as e:
            log(f"[!] Erro ao extrair um card: {e}")
    log(f"[✓] {len(produtos)} produtos extraidos.")
    return produtos

# === Buscar preco e categoria ML ===
def buscar_preco_ml(titulo):
    url = f"https://api.mercadolibre.com/sites/MLB/search?q={titulo}"
    res = requests.get(url)
    if res.status_code == 200:
        results = res.json().get("results", [])
        return float(results[0].get("price", 0)) if results else 0.0
    return 0.0

def buscar_categoria_ml(titulo):
    url_domain = f"https://api.mercadolibre.com/sites/MLB/domain_discovery/search?q={titulo}&limit=1"
    res = requests.get(url_domain)
    if res.status_code == 200:
        resultado = res.json()
        if resultado:
            return resultado[0]["category_id"]
    url_predictor = f"https://api.mercadolibre.com/sites/MLB/category_predictor/predict?title={titulo}"
    res = requests.get(url_predictor)
    if res.status_code == 200:
        return res.json().get("id", "MLB3530")
    return "MLB3530"

# === Token ===
def renovar_token():
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
        with open(".env", "r") as f:
            linhas = f.readlines()
        with open(".env", "w") as f:
            for ln in linhas:
                if ln.startswith("ML_ACCESS_TOKEN="):
                    f.write(f"ML_ACCESS_TOKEN={ML_ACCESS_TOKEN}\n")
                elif ln.startswith("ML_REFRESH_TOKEN="):
                    f.write(f"ML_REFRESH_TOKEN={ML_REFRESH_TOKEN}\n")
                else:
                    f.write(ln)

# === Planilha ===
def comparar_e_gerar_planilha(produtos):
    log("[🧾] Gerando planilha comparativa...")
    for p in produtos:
        p['price_ml'] = buscar_preco_ml(p['title'])
        p['margem'] = p['price_ml'] - p['price_toli']
        p['vale_a_pena'] = p['margem'] > 20
    df = pd.DataFrame(produtos)
    colunas = ['title', 'brand', 'price_toli', 'price_ml', 'margem', 'vale_a_pena', 'stock', 'description', 'image']
    df = df[[col for col in colunas if col in df.columns]]
    df.to_excel("comparativo_produtos.xlsx", index=False)
    log("[📁] Planilha 'comparativo_produtos.xlsx' salva.")
    messagebox.showinfo("Planilha Gerada", "Arquivo salvo com sucesso.")
    return produtos

# === Publicacao ===
def publicar_ml(produto):
    global ML_ACCESS_TOKEN
    categoria = buscar_categoria_ml(produto["title"])
    atributos = [
        {"id": "BRAND", "value_name": produto.get("brand", "Generico")},
        {"id": "FAMILY_NAME", "value_name": produto["title"].split()[0].capitalize()}
    ]
    item = {
        "title": produto["title"],
        "category_id": categoria,
        "price": produto["price_toli"] + 30,
        "currency_id": "BRL",
        "available_quantity": produto["stock"],
        "buying_mode": "buy_it_now",
        "listing_type_id": "gold_special",
        "condition": "new",
        "description": {"plain_text": produto["description"]},
        "pictures": [{"source": produto["image"]}],
        "attributes": atributos
    }
    res = requests.post(f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}", json=item)
    if res.status_code == 401:
        renovar_token()
        res = requests.post(f"https://api.mercadolibre.com/items?access_token={ML_ACCESS_TOKEN}", json=item)
    if res.status_code == 201:
        log(f"[↑] Produto publicado: {produto['title']}")
        return True
    else:
        try:
            erro = res.json()
            causa = erro.get("cause", [{}])[0]
            log(f"[✖] Falha ao publicar: {produto['title']} ({res.status_code}) -> {causa.get('code')}: {causa.get('message')}")
        except:
            log(f"[✖] Falha ao publicar: {produto['title']} ({res.status_code})")
        return False

# === Fluxos ===
def enviar_valem(produtos):
    enviados = [p for p in produtos if p['vale_a_pena']]
    for p in enviados:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluido", f"{len(enviados)} produtos enviados.")

def enviar_todos(produtos):
    for p in produtos:
        publicar_ml(p)
    messagebox.showinfo("Envio Concluido", "Todos os produtos enviados.")

def excluir_todos_ml():
    global ML_ACCESS_TOKEN
    if not messagebox.askyesno("Confirmacao", "Excluir TODOS os produtos do Mercado Livre?"):
        return
    res = requests.get(f"https://api.mercadolibre.com/users/me?access_token={ML_ACCESS_TOKEN}")
    if res.status_code != 200:
        return
    user_id = res.json()["id"]
    res = requests.get(f"https://api.mercadolibre.com/users/{user_id}/items/search", params={"access_token": ML_ACCESS_TOKEN, "status": "active"})
    item_ids = res.json().get("results", [])
    for item_id in item_ids:
        res = requests.delete(f"https://api.mercadolibre.com/items/{item_id}?access_token={ML_ACCESS_TOKEN}")
        if res.status_code == 401:
            renovar_token()
            res = requests.delete(f"https://api.mercadolibre.com/items/{item_id}?access_token={ML_ACCESS_TOKEN}")

# === Processamento Categorias ===
def processar_todas_as_categorias():
    log("[🧭] Iniciando processamento de todas as categorias...")
    url_base = driver.current_url
    total = len(driver.find_elements(By.CSS_SELECTOR, "li[id^='menu_departamentos_menubar_']"))
    produtos_totais = []

    for idx in range(total):
        try:
            categorias = driver.find_elements(By.CSS_SELECTOR, "li[id^='menu_departamentos_menubar_']")
            if idx >= len(categorias):
                continue

            categoria = categorias[idx]
            botao = WebDriverWait(categoria, 3).until(EC.element_to_be_clickable((By.TAG_NAME, "button")))
            nome_categoria = botao.text.strip()
            log(f"[→] Entrando na categoria: {nome_categoria}")
            driver.execute_script("arguments[0].scrollIntoView(true);", botao)
            botao.click()

            WebDriverWait(driver, 10).until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "div.a-Menu-content ul[role='group'] > li")))
            submenu = categoria.find_elements(By.CSS_SELECTOR, "div.a-Menu-content ul[role='group'] > li")
            if not submenu:
                log("[!] Nenhum submenu encontrado.")
                driver.get(url_base)
                time.sleep(2)
                continue

            ultimo_item = submenu[-1]
            driver.execute_script("arguments[0].scrollIntoView(true);", ultimo_item)
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable(ultimo_item)).click()

            WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li.a-CardView-item")))
            scroll_ate_carregar_todos()
            produtos = extrair_produtos()
            produtos_totais.extend(produtos)

            log(f"[✔] Finalizado categoria: {nome_categoria} ({len(produtos)} produtos)")

            driver.get(url_base)
            time.sleep(2)
        except Exception as e:
            log(f"[✖] Erro ao processar categoria {idx}: {e}")
            try:
                driver.get(url_base)
                time.sleep(2)
            except:
                continue

    log(f"[📦] Total de produtos extraídos de todas as categorias: {len(produtos_totais)}")
    return produtos_totais

# === Inicio ===
def executar_fluxo():
    login_toli()
    produtos = processar_todas_as_categorias()

    if produtos:
        produtos = comparar_e_gerar_planilha(produtos)
    else:
        log("[!] Nenhum produto extraído.")

    Label(janela, text="Escolha uma ação:").pack(pady=10)
    Button(janela, text="Enviar apenas os que valem a pena", command=lambda: enviar_valem(produtos)).pack(pady=5)
    Button(janela, text="Enviar todos os produtos", command=lambda: enviar_todos(produtos)).pack(pady=5)
    Button(janela, text="Excluir TODOS os produtos", command=excluir_todos_ml).pack(pady=5)

executar_fluxo()
janela.mainloop()