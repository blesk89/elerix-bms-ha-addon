## 2.3.3

- Oprava pádu daemonu při timeoutu na HA REST API — `TimeoutError`/`OSError` už jsou odchyceny stejně jako `URLError`
- Přidána pojistka (try/except) kolem hlavního cyklu, aby jedna neočekávaná chyba nezastavila čtení BMS natrvalo

## 2.3.2

- Odstraněny DEBUG výpisy z logů (TX/RX bajty)

## 2.3.1

- Oprava vypadávání RS485 spojení: `read_until('\r')` místo `read(512)` — nečeká zbytečně 3s timeout
- Přidán `inter_byte_timeout=0.2s` pro okamžité vrácení dat po konci PACE frame
- Retry 1× při `no_response` nebo výjimce

## 2.3.0

- SOH výpočet z naměřené kapacity vs. nominální
- Nové senzory: teploty MOSFET (DSG/CHG), I/O status, AFE balance
- Parametr `nominal_capacity_ah` v konfiguraci

## 2.1.0

- Počáteční vydání: čtení BMS přes RS485, FoxESS/PACE protokol, LV5200
- Podpora více packů na stejné adrese (`pack_num`)
- Senzory: SOC, napětí, proud, výkon, kapacita, teploty, napětí článků
