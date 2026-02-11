from drivers import redpitaya_scpi as scpi

IP = "169.254.4.198"
rp = scpi.scpi(IP)

# reset
rp.tx_txt("ACQ:RST")

# časová základňa – meníš podľa frekvencie
rp.tx_txt("ACQ:DEC 64")   # väčšie číslo = pomalšie, viac detailu

# trigger
rp.tx_txt("ACQ:TRIG:LEV 0")
rp.tx_txt("ACQ:TRIG CH1_PE")

rp.tx_txt("ACQ:START")
rp.tx_txt("ACQ:TRIG NOW")

# čakaj trigger
while True:
    rp.tx_txt("ACQ:TRIG:STAT?")
    if rp.rx_txt().strip() == "TD":
        break

# načítaj dáta
rp.tx_txt("ACQ:SOUR1:DATA?")
data_str = rp.rx_txt().strip("{}\n\r ")
samples = [float(x) for x in data_str.split(",") if x]

print("Samples:", len(samples))

period = []
start = None

for i in range(1, len(samples)):
    if samples[i-1] < 0 and samples[i] >= 0:
        if start is None:
            start = i
        else:
            period = samples[start:i]
            break

print ("One period samples:", len(period))