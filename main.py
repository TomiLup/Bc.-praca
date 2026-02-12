import time
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS
from drivers import redpitaya_scpi as scpi

# --- KONFIGURÁCIA (Podľa tvojho dotazu) ---
TOKEN = "etdYIRq-pf7b7m6YVlmRj9kvb1A_yfaCE03nhJBXw3QMbPkOkCS0RZHavWtOCQGI66v8jVMArW-G_bXDZprQ7w=="
ORG = "99fe279016e68f6d"
BUCKET = "Osciloskop"  # Musí sedieť s from(bucket: "Osciloskop")
IP = "169.254.4.198"

client = InfluxDBClient(url="http://localhost:8086", token=TOKEN, org=ORG)
write_api = client.write_api(write_options=SYNCHRONOUS)

try:
    rp = scpi.scpi(IP)
    print("Zber štartuje...")

    # Urobíme 10-sekundový zber
    start_time = time.time()
    while (time.time() - start_time) < 10:
        rp.tx_txt("ACQ:START")
        rp.tx_txt("ACQ:TRIG NOW")
        time.sleep(0.02)
        
        rp.tx_txt("ACQ:SOUR1:DATA?")
        raw = rp.rx_txt().strip("{}\n\r ")
        
        if not raw: continue
            
        samples = raw.split(",")
        t_now = time.time_ns()
        
        batch = []
        for i, v in enumerate(samples[:1000]): # Berieme 1000 vzoriek pre rýchlosť
            # TU JE TO NAJDÔLEŽITEJŠIE: Musí to sedieť s tvojím filter(fn: ...)
            p = Point("test_signalu") \
                .field("napatie", float(v)) \
                .time(t_now + (i * 512), WritePrecision.NS)
            batch.append(p)
        
        write_api.write(bucket=BUCKET, org=ORG, record=batch)
        print(f"Odoslaný balík dát do {BUCKET}...")

    print("Hotovo!")

except Exception as e:
    print(f"Chyba: {e}")
finally:
    client.close()