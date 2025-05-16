import requests
import time
import os

URL_API_WPP = os.getenv("URL_API_WPP")

def gerar_token(session: str, secret: str):
    url = f"{URL_API_WPP}/{session}/{secret}/generate-token"
    response = requests.post(url)
    return response.json(), response.status_code

def start_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/start-session"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    data = {
        "webhook": "",
        "waitQrCode": True
    }
    response = requests.post(url, json=data, headers=headers)
    return response.json(), response.status_code

def status_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/status-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def get_qrcode(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/qrcode-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.content, response.status_code

def check_connection(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/check-connection-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    return response.json(), response.status_code

def close_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/close-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)  # Aguarda se necessário
    return response.json(), response.status_code

def logout_session(session: str, token: str):
    url = f"{URL_API_WPP}/{session}/logout-session"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.post(url, headers=headers)
    time.sleep(3)
    return response.json(), response.status_code

