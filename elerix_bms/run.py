#!/usr/bin/env python3
"""
Elerix BMS Reader add-on daemon
Reads BMS data and posts individual HA sensor entities per metric per battery.
Supports multiple batteries on the same RS485 bus (configurable addresses list).
"""

import json
import os
import subprocess
import time
import urllib.request
import urllib.error

OPTIONS_FILE = "/data/options.json"
BMS_SCRIPT   = "/elerix_bms.py"

with open(OPTIONS_FILE) as f:
    opts = json.load(f)

PORT      = opts.get("port", "/dev/ttyUSB0")
BAUDRATE  = opts.get("baudrate", 9600)
INTERVAL  = opts.get("interval", 30)
NOMINAL_CAPACITY_AH = opts.get("nominal_capacity_ah", 100)

# Build PACKS list: [{addr, pack_num}]
# New format: packs: [{addr: 2, pack_num: 1}, {addr: 2, pack_num: 2}]
# Legacy format: addresses: [2] → each addr queries with pack_num=None (INFO=addr)
if opts.get("packs"):
    PACKS = opts["packs"]
else:
    addresses = opts.get("addresses") or [opts.get("address", 2)]
    PACKS = [{"addr": a, "pack_num": None} for a in addresses]

SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
HA_API_BASE = "http://supervisor/core/api/states"

# Sensor definitions: (key_in_data, friendly_suffix, unit, device_class, state_class)
SENSORS = [
    ("soc_pct",          "SOC",                  "%",   "battery",     "measurement"),
    ("voltage_v",        "Napětí",                "V",   "voltage",     "measurement"),
    ("current_a",        "Proud",                 "A",   "current",     "measurement"),
    ("power_w",          "Výkon",                 "W",   "power",       "measurement"),
    ("remaining_ah",     "Zbývající kapacita",    "Ah",  None,          "measurement"),
    ("full_capacity_ah", "Celková kapacita",       "Ah",  None,          "measurement"),
    ("cycle_count",      "Počet cyklů",           "",    None,          "total_increasing"),
    ("soh_pct",          "Zdraví baterie SOH",    "%",   None,          "measurement"),
    ("cell_min_v",       "Min. článek",           "V",   "voltage",     "measurement"),
    ("cell_max_v",       "Max. článek",           "V",   "voltage",     "measurement"),
    ("cell_diff_mv",     "Rozdíl článků",         "mV",  "voltage",     "measurement"),
    ("temp_env_c",       "Teplota okolí",         "°C",  "temperature", "measurement"),
    ("temp_max_c",       "Max. teplota",          "°C",  "temperature", "measurement"),
    ("temp_min_c",       "Min. teplota",          "°C",  "temperature", "measurement"),
    ("warning_status",   "Varovný stav",          "",    None,          "measurement"),
    ("alarm_status",     "Alarmový stav",         "",    None,          "measurement"),
    ("temp_bms_c",        "Teplota BMS desky",    "°C",  "temperature", "measurement"),
    ("temp_dsg_mosfet_c", "Teplota DSG MOSFET",   "°C",  "temperature", "measurement"),
    ("temp_chg_mosfet_c", "Teplota CHG MOSFET",   "°C",  "temperature", "measurement"),
    ("io_status1",        "I/O Status 1",          "",    None,          "measurement"),
    ("io_status2",        "I/O Status 2",          "",    None,          "measurement"),
    ("afe_balance",       "Balancování článků",    "",    None,          "measurement"),
]


def post_sensor(entity_id: str, state, attributes: dict) -> None:
    payload = json.dumps({
        "state": str(state),
        "attributes": attributes,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{HA_API_BASE}/{entity_id}",
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {SUPERVISOR_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        print(f"[WARN] POST {entity_id} failed: {e}", flush=True)


def post_battery_sensors(data: dict, addr: int, pack_num: int = None) -> None:
    # Compute SOH from full_capacity_ah and nominal capacity
    if "full_capacity_ah" in data and NOMINAL_CAPACITY_AH > 0:
        data["soh_pct"] = round(data["full_capacity_ah"] / NOMINAL_CAPACITY_AH * 100, 1)

    # Use pack_num as sensor suffix if set (multi-pack at same addr), else addr
    suffix = pack_num if pack_num is not None else addr
    prefix = f"elerix_bms_{suffix}"

    # Individual metric sensors
    for key, fname, unit, dev_class, state_class in SENSORS:
        val = data.get(key)
        if val is None:
            continue
        attrs = {"friendly_name": f"Baterie {suffix} — {fname}"}
        if unit:
            attrs["unit_of_measurement"] = unit
        if dev_class:
            attrs["device_class"] = dev_class
        if state_class:
            attrs["state_class"] = state_class
        post_sensor(f"sensor.{prefix}_{key}", val, attrs)

    # Per-cell voltage sensors
    cells = data.get("cell_voltages_v", [])
    for i, v in enumerate(cells, 1):
        post_sensor(
            f"sensor.{prefix}_cell_{i:02d}_v",
            v,
            {
                "friendly_name": f"Baterie {suffix} — Článek {i}",
                "unit_of_measurement": "V",
                "device_class": "voltage",
                "state_class": "measurement",
            },
        )

    # Main aggregate sensor (state = SOC, all data as attributes)
    soc = data.get("soc_pct", "unknown")
    main_attrs = {
        "friendly_name": f"Baterie {suffix} — data",
        "unit_of_measurement": "%",
        "device_class": "battery",
        "state_class": "measurement",
        **{k: v for k, v in data.items() if not isinstance(v, list)},
    }
    # Cell voltages as numbered attributes
    for i, v in enumerate(cells, 1):
        main_attrs[f"cell_{i:02d}_v"] = v
    post_sensor(f"sensor.{prefix}", soc, main_attrs)


def post_combined_sensors(all_data: list) -> None:
    """Post combined sensors when multiple batteries are present."""
    if len(all_data) < 2:
        return
    total_power   = sum(d.get("power_w", 0) for d in all_data)
    total_current = sum(d.get("current_a", 0) for d in all_data)
    socs = [d["soc_pct"] for d in all_data if "soc_pct" in d]
    avg_soc = round(sum(socs) / len(socs), 1) if socs else None

    post_sensor("sensor.elerix_bms_total_power", round(total_power, 1),
                {"friendly_name": "Baterie celkový výkon", "unit_of_measurement": "W",
                 "device_class": "power", "state_class": "measurement"})
    post_sensor("sensor.elerix_bms_total_current", round(total_current, 1),
                {"friendly_name": "Baterie celkový proud", "unit_of_measurement": "A",
                 "device_class": "current", "state_class": "measurement"})
    if avg_soc is not None:
        post_sensor("sensor.elerix_bms_avg_soc", avg_soc,
                    {"friendly_name": "Baterie průměrný SOC", "unit_of_measurement": "%",
                     "device_class": "battery", "state_class": "measurement"})


def read_bms(addr: int, pack_num: int = None) -> dict:
    try:
        cmd = ["python3", BMS_SCRIPT, PORT, str(BAUDRATE), str(addr)]
        if pack_num is not None:
            cmd.append(str(pack_num))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        label = f"addr={addr}" + (f" pack={pack_num}" if pack_num is not None else "")
        if result.stderr.strip():
            print(f"[DEBUG] {label}: {result.stderr.strip()[:200]}", flush=True)
        if result.returncode != 0 or not result.stdout.strip():
            return {"error": f"script_exit_{result.returncode}"}
        return json.loads(result.stdout.strip())
    except subprocess.TimeoutExpired:
        return {"error": "script_timeout"}
    except Exception as e:
        return {"error": str(e)}


def main():
    print(f"[INFO] Elerix BMS Reader started — port={PORT} baud={BAUDRATE} "
          f"packs={PACKS} interval={INTERVAL}s", flush=True)

    while True:
        try:
            all_ok = []
            for pack in PACKS:
                addr     = pack["addr"]
                pack_num = pack.get("pack_num")
                label    = f"addr={addr}" + (f" pack={pack_num}" if pack_num is not None else "")
                data = read_bms(addr, pack_num)
                if "error" in data:
                    print(f"[WARN] {label} error: {data['error']}", flush=True)
                    continue
                soc  = data.get("soc_pct", "?")
                volt = data.get("voltage_v") or data.get("pack_volt_v", "?")
                curr = data.get("current_a", "?")
                pwr  = data.get("power_w", "?")
                print(f"[INFO] {label}: SOC={soc}%  V={volt}V  I={curr}A  P={pwr}W", flush=True)
                post_battery_sensors(data, addr, pack_num)
                all_ok.append(data)

            if len(all_ok) > 1:
                post_combined_sensors(all_ok)
        except Exception as e:
            print(f"[ERROR] cycle failed, continuing: {e}", flush=True)

        time.sleep(INTERVAL)


if __name__ == "__main__":
    main()
