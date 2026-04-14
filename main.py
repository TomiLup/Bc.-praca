import pyvisa
import time
import glob
import os
import socket
import pandas as pd
import matplotlib.pyplot as plt
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

# Knižnica pre Red Pitaya (ak ju nenájde, skript pobeží ďalej pre Rigol)
try:
    from drivers import redpitaya_scpi as scpi
except ImportError:
    print("UPOZORNENIE: Knižnica pre Red Pitaya nebola nájdená.")

# ==========================================
# 1. KONFIGURÁCIA ZARIADENÍ A INFLUXDB
# ==========================================
IP_RIGOL = "169.254.25.212"
IP_REDPITAYA = "169.254.4.198"

TOKEN = "lKVFJX4i3VuO8EgXENazf0VgVPmNtJj6gVDFC9BaVre4RIpCyRR8TbChsdirAuOtPoMcvaYeXyiR4BCAky8xYA=="
ORG = "MojeLab"
BUCKET = "Osciloskop"
URL = "http://localhost:8086"

valid_decimations = [1, 8, 64, 1024, 8192, 65536]

# Príprava interaktívneho grafu
plt.ion()
fig, ax = plt.subplots(figsize=(8, 4))

# ==========================================
# 2. POMOCNÉ FUNKCIE (Grafy, Archív)
# ==========================================
def format_hz(hz):
    if hz >= 1_000_000: return f"{hz / 1_000_000:.2f} MHz"
    if hz >= 1_000: return f"{hz / 1_000:.1f} kHz"
    return f"{hz:.0f} Hz"

def vykresli_data(samples, x_inc, titulok):
    ax.clear()
    cas_ms = [i * (x_inc * 1000) for i in range(len(samples))]
    ax.plot(cas_ms, samples, color='blue', linewidth=1.5)
    ax.set_title(titulok)
    ax.set_xlabel("Čas [ms]")
    ax.set_ylabel("Napätie [V]")
    ax.grid(True)
    plt.draw()
    plt.pause(0.1)

def archiv_merani():
    print("\n--- ARCHÍV MERANÍ ---")
    subory = sorted(glob.glob('meranie_*.csv'), key=os.path.getctime)
    if not subory:
        print("Žiadne merania sa nenašli.")
        return

    for i, f in enumerate(subory):
        print(f" [{i}] -> {f}")

    vyber = input("\nZadaj číslo merania (alebo Enter pre návrat) > ").strip()
    if vyber.isdigit() and int(vyber) < len(subory):
        vybrany_subor = subory[int(vyber)]
        df = pd.read_csv(vybrany_subor)
        samples = df['napatie'].tolist()
        x_inc = df['x_inc'].iloc[0] if 'x_inc' in df.columns else 0.000001
        vykresli_data(samples, x_inc, f"Archív: {vybrany_subor}")
    else:
        print("Návrat.")

# ==========================================
# 3. ZÍSKAVANIE DÁT (Špecifické pre HW)
# ==========================================
def zmeraj_rigol(osc):
    """Logika stiahnutia dát špecificky pre Rigol MSO5000"""
    try:
        freq = float(osc.query(":MEASure:ITEM? FREQuency,CHANnel1"))
        if freq > 1e15: freq = 0.0
    except:
        freq = 0.0

    osc.write(":STOP")
    osc.write(":WAVeform:SOURce CHANnel1")
    osc.write(":WAVeform:FORMat ASCii")
    
    raw_data = osc.query(":WAVeform:DATA?").strip()
    if raw_data.startswith("#"):
        dl_hlav = int(raw_data[1])
        raw_data = raw_data[2 + dl_hlav:]
        
    samples = [float(v) for v in raw_data.split(",") if v]
    x_inc = float(osc.query(":WAVeform:XINCrement?"))
    osc.write(":RUN")
    
    return samples, freq, x_inc

def zmeraj_redpitaya():
    """Logika stiahnutia dát špecificky pre Red Pitaya"""
    print("\nVyberte decimáciu:")
    for i, dec in enumerate(valid_decimations):
        print(f"  [{i}] -> DEC: {dec:<6} ({format_hz(125_000_000 / dec)})")
        
    vyber = input("Voľba [0-5] > ").strip()
    if not (vyber.isdigit() and 0 <= int(vyber) < len(valid_decimations)):
        print("Neplatný výber.")
        return None, 0, 0

    dec_nastavena = valid_decimations[int(vyber)]
    
    rp = scpi.scpi(IP_REDPITAYA)
    rp.tx_txt("ACQ:RST")
    time.sleep(0.05)

    rp.tx_txt("SOUR1:FREQ:FIX?")
    freq_str = rp.rx_txt().strip()
    freq = float(freq_str) if (freq_str and freq_str != 'ERR!') else 1000.0

    dt_ns = dec_nastavena * 8
    wait_time = (16384 * dt_ns) / 1_000_000_000
    x_inc = dt_ns / 1_000_000_000  # Prevod nanosekúnd na sekundy pre kompatibilitu s Rigolom

    rp.tx_txt(f"ACQ:DEC {dec_nastavena}")
    rp.tx_txt("ACQ:START")
    time.sleep(wait_time + 0.05)
    rp.tx_txt("ACQ:STOP")
    rp.tx_txt("ACQ:SOUR1:DATA?")
    
    raw_data = rp.rx_txt().strip("{} \n\r")
    samples = [float(v) for v in raw_data.split(",") if v != 'ERR!'][:1000]
    rp.close()
    
    return samples, freq, x_inc

# ==========================================
# 4. UNIVERZÁLNY ZÁPIS A SPRACOVANIE
# ==========================================
def spracuj_a_uloz(zariadenie, osc_objekt, write_api):
    print(f"\n--- Meriam ({zariadenie}) ---")
    
    # Smerovač podľa aktívneho zariadenia
    if zariadenie == "RIGOL":
        samples, freq, x_inc = zmeraj_rigol(osc_objekt)
    elif zariadenie == "REDPITAYA":
        samples, freq, x_inc = zmeraj_redpitaya()
    
    if not samples: return

    # Spoločné uloženie do CSV
    timestamp = time.strftime("%H%M%S")
    filename = f"meranie_{timestamp}_{zariadenie}_{int(freq)}Hz.csv"
    pd.DataFrame({'napatie': samples, 'x_inc': [x_inc] * len(samples)}).to_csv(filename, index=False)
    print(f"Uložené do: {filename}")

    # Spoločný zápis do InfluxDB
    dt_ns = x_inc * 1_000_000_000
    start_time_ns = time.time_ns()
    batch = [
        Point("osciloskop_data")
        .tag("zariadenie", zariadenie)
        .tag("frekvencia", str(int(freq)))
        .field("napatie", float(v))
        .time(int(start_time_ns + (i * dt_ns)), WritePrecision.NS)
        for i, v in enumerate(samples)
    ]
    write_api.write(bucket=BUCKET, org=ORG, record=batch)

    # Spoločné vykreslenie
    vykresli_data(samples, x_inc, f"Nové meranie: {zariadenie} ({format_hz(freq)})")

# ==========================================
# 5. HLAVNÝ PROGRAM & AUTODETEKCIA
# ==========================================
print("Prebieha autodetekcia pripojených zariadení...")
aktivne_zariadenie = None
osc = None

# Pokus 1: Je to Rigol?
rm = pyvisa.ResourceManager('@py')
try:
    osc = rm.open_resource(f"TCPIP0::{IP_RIGOL}::INSTR")
    osc.timeout = 2000
    idn = osc.query('*IDN?').strip()
    print(f" => Nájdený Rigol: {idn}")
    aktivne_zariadenie = "RIGOL"
except:
    # Pokus 2: Je to Red Pitaya? (Skúška TCP portu 5000)
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.5)
            s.connect((IP_REDPITAYA, 5000))
        print(" => Nájdená Red Pitaya (Port 5000 aktívny)!")
        aktivne_zariadenie = "REDPITAYA"
    except:
        print(" CHYBA: Na sieti sa nenašiel Rigol ani Red Pitaya.")

if aktivne_zariadenie:
    client = InfluxDBClient(url=URL, token=TOKEN, org=ORG)
    write_api = client.write_api(write_options=SYNCHRONOUS)
    
    print("\n" + "="*45)
    print(f" UNIVERZÁLNY TERMINÁL: {aktivne_zariadenie}")
    print(" [ENTER] -> Odmeraj a ulož")
    print(" [L]     -> Archív (načítať CSV)")
    print(" [Q]     -> Koniec")
    print("="*45)

    try:
        while True:
            vstup = input("\nPovel (Enter/L/Q) > ").strip().lower()
            if vstup == 'q': break
            elif vstup == '':  spracuj_a_uloz(aktivne_zariadenie, osc, write_api)
            elif vstup == 'l': archiv_merani()
    finally:
        client.close()
        if osc: osc.close()
        plt.close('all')