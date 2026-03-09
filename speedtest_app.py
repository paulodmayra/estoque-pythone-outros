import streamlit as st
import requests
import time

# Função para obter IP público
def get_public_ip():
    try:
        response = requests.get("https://api.ipify.org?format=json")
        return response.json().get("ip", "Não foi possível obter o IP público.")
    except Exception:
        return "Não foi possível obter o IP público."

# Função para formatar velocidade
def format_speed(bits_per_second):
    kbps = bits_per_second / 1024
    mbps = kbps / 1024
    if mbps >= 1:
        return f"{mbps:.2f} Mbps"
    elif kbps >= 1:
        return f"{kbps:.2f} Kbps"
    else:
        return f"{bits_per_second:.2f} bps"

# Função para testar velocidade de download
def test_download_speed():
    image_url = "https://upload.wikimedia.org/wikipedia/commons/3/3f/Fronalpstock_big.jpg"
    file_size_bytes = 5242880  # ~5MB

    start_time = time.time()
    try:
        response = requests.get(image_url, stream=True)
        received_length = 0
        for chunk in response.iter_content(1024):
            if not chunk:
                break
            received_length += len(chunk)
        end_time = time.time()
        duration_seconds = end_time - start_time
        bits_loaded = file_size_bytes * 8
        speed_bps = bits_loaded / duration_seconds
        return speed_bps
    except Exception:
        return None

# Interface Streamlit
st.title("Teste de Velocidade da Internet e IP Público")

if st.button("Iniciar Teste"):
    st.write("Obtendo IP público...")
    ip = get_public_ip()
    st.write(f"Seu IP público é: {ip}")
    
    st.write("Iniciando teste de velocidade...")
    speed = test_download_speed()
    if speed:
        st.success(f"Velocidade estimada de download: {format_speed(speed)}")
    else:
        st.error("Não foi possível medir a velocidade.")
