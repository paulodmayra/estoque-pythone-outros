import streamlit as st
import requests
import time
import socket

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
        for _ in response.iter_content(1024):
            pass
        end_time = time.time()
        duration_seconds = end_time - start_time
        bits_loaded = file_size_bytes * 8
        speed_bps = bits_loaded / duration_seconds
        return speed_bps
    except Exception:
        return None

# Função para testar upload speed (simulação enviando dados para httpbin)
def test_upload_speed():
    data = b"x" * 5_000_000  # 5MB de dados
    start_time = time.time()
    try:
        response = requests.post("https://httpbin.org/post", data=data)
        end_time = time.time()
        duration_seconds = end_time - start_time
        bits_sent = len(data) * 8
        speed_bps = bits_sent / duration_seconds
        return speed_bps
    except Exception:
        return None

# Função para medir latência (ping simples)
def test_latency(host="8.8.8.8", port=53):
    try:
        start_time = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        sock.connect((host, port))
        end_time = time.time()
        sock.close()
        latency_ms = (end_time - start_time) * 1000
        return latency_ms
    except Exception:
        return None

# Interface Streamlit
st.title("Teste de Velocidade da Internet e IP Público")

if st.button("Iniciar Teste"):
    st.write("Obtendo IP público...")
    ip = get_public_ip()
    st.write(f"Seu IP público é: {ip}")
    
    st.write("Testando latência...")
    latency = test_latency()
    if latency:
        st.info(f"Latência estimada: {latency:.2f} ms")
    else:
        st.error("Não foi possível medir a latência.")
    
    st.write("Testando velocidade de download...")
    download_speed = test_download_speed()
    if download_speed:
        st.success(f"Velocidade estimada de download: {format_speed(download_speed)}")
    else:
        st.error("Não foi possível medir a velocidade de download.")
    
    st.write("Testando velocidade de upload...")
    upload_speed = test_upload_speed()
    if upload_speed:
        st.success(f"Velocidade estimada de upload: {format_speed(upload_speed)}")
    else:
        st.error("Não foi possível medir a velocidade de upload.")
