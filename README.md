# Elerix BMS – Home Assistant Add-on

Home Assistant custom add-on pro čtení dat z Elerix EX-S5 baterií přes RS485 (FoxESS/PACE ASCII protokol, čip LV5200).

## Hardware

- **Baterie:** Elerix EX-S5 (LiFePO4, 48V, 100/200 Ah)
- **BMS čip:** LV5200 (FoxESS/PACE ASCII protokol)
- **Připojení:** USB RS485 adapter -> `/dev/ttyUSB0`
- **Výchozí parametry:** 9600 baud, adresa 2

### Multi-pack zapojení (master/slave)

Obě baterie používají **stejnou RS485 adresu (ADR=2)**, ale liší se hodnotou INFO pole:
- `pack_num: 1` -> slave baterie (INFO=0x01)
- `pack_num: 2` -> master baterie (INFO=0x02)

## Instalace

### 1. Přidání repository do HA

HA -> Settings -> Add-ons -> Add-on Store -> ⋮ (tři tečky) -> **Repositories** -> přidat:

```
https://github.com/blesk89/elerix-bms-ha-addon
```

### 2. Instalace add-onu

HA -> Settings -> Add-ons -> Add-on Store -> **Elerix BMS Reader** -> Install

### 3. Konfigurace

```yaml
port: /dev/ttyUSB0
baudrate: 9600
interval: 30

# Jedna baterie:
packs:
  - addr: 2
    pack_num: 2

# Dvě baterie (master/slave):
packs:
  - addr: 2
    pack_num: 1   # slave
  - addr: 2
    pack_num: 2   # master
```

## Vytvářené senzory

### Na baterii (prefix `sensor.elerix_bms_{pack_num}_`)

| Senzor | Popis | Jednotka |
|--------|-------|----------|
| `soc_pct` | Stav nabití | % |
| `soh_pct` | Zdraví baterie | % |
| `voltage_v` | Napětí | V |
| `current_a` | Proud | A |
| `power_w` | Výkon | W |
| `remaining_ah` | Zbývající kapacita | Ah |
| `full_capacity_ah` | Celková kapacita | Ah |
| `cycle_count` | Počet cyklů | - |
| `cell_min_v` | Min. napětí článků | V |
| `cell_max_v` | Max. napětí článků | V |
| `cell_diff_mv` | Rozdíl článků | mV |
| `temp_env_c` | Teplota okolí | C |
| `temp_max_c` | Max. teplota | C |
| `temp_min_c` | Min. teplota | C |
| `warning_status` | Varovný stav (bitmask) | - |
| `alarm_status` | Alarmový stav (bitmask) | - |
| `cell_01_v` ... `cell_16_v` | Napětí jednotlivých článků | V |

### Kombinované (více baterií)

| Senzor | Popis |
|--------|-------|
| `sensor.elerix_bms_total_power` | Celkový výkon |
| `sensor.elerix_bms_total_current` | Celkový proud |
| `sensor.elerix_bms_avg_soc` | Průměrný SOC |

## Protokol

**FoxESS LV5200 RS485 Protocol** (2020.01.14)

- CID1 = `0x46` (battery data)
- CID2 = `0x42` - Cell Sample Data (články, kapacita, cykly, SOH)
- CID2 = `0x99` - Running Data (SOC, alarmy, I/O status, detailní statistiky)

Frame format:
```
~ VER(2) ADR(2) CID1(2) RTN(2) LENGTH(4) INFO CHKSUM(4) \r
```

## Testováno na

- Elerix EX-S5 200Ah (2x paralelně, master/slave)
- Home Assistant OS 2026.x na Raspberry Pi (aarch64)
- USB RS485 adapter na `/dev/ttyUSB0`

## Licence

MIT
