import requests

code = "TG-6875a11607ab6100017fee80-377245789"  # <- seu code
client_id = "1663341505604856"
client_secret = "JjX45g1kRq2RLnNURpsQa9FuodHyEb2J"
redirect_uri = "https://webhook.site/30a14bb9-5a32-468a-a7bd-2523f5c812b5"

data = {
    "grant_type": "authorization_code",
    "client_id": client_id,
    "client_secret": client_secret,
    "code": code,
    "redirect_uri": redirect_uri
}

res = requests.post("https://api.mercadolibre.com/oauth/token", data=data)

if res.status_code == 200:
    token_data = res.json()
    print("✅ Access Token:", token_data["access_token"])
    print("🔁 Refresh Token:", token_data["refresh_token"])
else:
    print("❌ Erro ao obter token:", res.status_code, res.text)