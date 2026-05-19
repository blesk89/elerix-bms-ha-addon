# Elerix BMS – Home Assistant Add-on

Home Assistant local add-on pro cteni dat z Elerix EX-S5 baterii pres RS485 (FoxESS/PACE ASCII protokol, cip LV5200).

## Hardware

- **Baterie:** Elerix EX-S5 (LiFePO4, 48V, 100/200 Ah)
- **BMS cip:** LV5200 (FoxESS/PACE ASCII protokol)
- **Pripojeni:** USB RS485 adapter -> `/dev/ttyUSB0`
- **Vychozi parametry:** 9600 baud, adresa 2

### Multi-pack zapojeni (master/slave)

Obe baterie pouzivaji **stejnou RS485 adresu (ADR=2)**, ale lisi se hodnotou INFO pole:
- `pack_num: 1` -> slave baterie (INFO=0x01)
- `pack_num: 2` -> master baterie (INFO=0x02)

## Instalace

### 1. Pridani add-onu do HA

Zkopiruj slozku `elerix_bms/` do adresare `addons/` na tvem HA hostu:

```
\\homeassistant\addons\elerix_bms\
```

### 2. BMS cteci skript

Zkopiruj `scripts/elerix_bms.py` do:

```
\\homeassistant\config\scripts\elerix_bms.py
```

### 3. Instalace add-onu

HA -> Settings -> Add-ons -> Add-on Store -> **Local add-ons** -> Elerix BMS Reader -> Install

### 4. Konfigurace

```yaml
port: /dev/ttyUSB0
baudrate: 9600
interval: 30

# Jedna baterie:
packs:
  - addr: 2
    pack_num: 2

# Dve baterie (master/slave):
packs:
  - addr: 2
    pack_num: 1   # slave
  - addr: 2
    pack_num: 2   # master
```

## Vytvarene senzory

### Na baterii (prefix `sensor.elerix_bms_{pack_num}_`)

| Senzor | Popis | Jednotka |
|--------|-------|----------|
| `soc_pct` | Stav nabiti | % |
| `soh_pct` | Zdravi baterie | % |
| `voltage_v` | Napeti | V |
| `current_a` | Proud | A |
| `power_w` | Vykon | W |
| `remaining_ah` | Zbyvajici kapacita | Ah |
| `full_capacity_ah` | Celkova kapacita | Ah |
| `cycle_count` | Pocet cyklu | - |
| `cell_min_v` | Min. napeti clanku | V |
| `cell_max_v` | Max. napeti clanku | V |
| `cell_diff_mv` | Rozdil clanku | mV |
| `temp_env_c` | Teplota okoli | C |
| `temp_max_c` | Max. teplota | C |
| `temp_min_c` | Min. teplota | C |
| `warning_status` | Varovny stav (bitmask) | - |
| `alarm_status` | Alarmovy stav (bitmask) | - |
| `cell_01_v` ... `cell_16_v` | Napeti jednotlivych clanku | V |

### Kombinovane (vice baterii)

| Senzor | Popis |
|--------|-------|
| `sensor.elerix_bms_total_power` | Celkovy vykon |
| `sensor.elerix_bms_total_current` | Celkovy proud |
| `sensor.elerix_bms_avg_soc` | Prumerny SOC |

## Protokol

**FoxESS LV5200 RS485 Protocol** (2020.01.14)

- CID1 = `0x46` (battery data)
- CID2 = `0x42` - Cell Sample Data (clanky, kapacita, cykly, SOH)
- CID2 = `0x99` - Running Data (SOC, alarmy, I/O status, detailni statistiky)

Frame format:
```
~ VER(2) ADR(2) CID1(2) RTN(2) LENGTH(4) INFO CHKSUM(4) \r
```

## Testovano na

- Elerix EX-S5 200Ah (2x parallelne, master/slave)
- Home Assistant OS 2026.x na Raspberry Pi (aarch64)
- USB RS485 adapter na `/dev/ttyUSB0`

## Licence

MIT
