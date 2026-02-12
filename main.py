import time
import requests
import numpy as np
from drivers import redpitaya_scpi as scpi

# --- KONFIGURÁCIA ---
IP = "169.254.4.198"
TOKEN = "-0NGryDI1atHgmjh3dNMBWrX8KfDczg1GX7p8TGyvHnGt0w8p_wgVHqT6kTLvafOLrTF5-_PV46SzlSldp5Fw=="
INFLUX_URL = "http://localhost:8086/api/v2/write?org=MojeLab&bucket=Bc.%20praca&precision=ns"
HEADERS = {"Authorization": f"Token {TOKEN}"}

rp = scpi.scpi(IP)

def capture_to_influx(seconds=60):
    rp.tx_txt("ACQ:RST")
    rp.tx_txt("ACQ:DEC 64")
    
    fs = 125e6 / 64
    dt_ns = int((1/fs) * 1e9)
    
    start_loop = time.time()
    print("Zber beží... Sleduj InfluxDB.")

    while (time.time() - start_loop) < seconds:
        rp.tx_txt("ACQ:START")
        rp.tx_txt("ACQ:TRIG NOW")
        
        # Čakanie na naplnenie buffera (cca 8ms pri DEC 64)
        time.sleep(0.01) 
        
        rp.tx_txt("ACQ:SOUR1:DATA?")
        raw = rp.rx_txt().strip("{}\n\r ")
        
        if not raw: continue
        
        samples = raw.split(",")
        t_start = time.time_ns()
        
        # Tvorba Line Protocolu
        lines = [f"osciloskop,chan=ch1 volt={v} {t_start + (i * dt_ns)}" 
                 for i, v in enumerate(samples) if v]
        
        # Odoslanie do Influxu
        res = requests.post(INFLUX_URL, data="\n".join(lines), headers=HEADERS)
        if res.status_code != 204:
            print(f"Chyba: {res.status_code}, {res.text}")

    print("Zber dokončený.")

capture_to_influx(60)