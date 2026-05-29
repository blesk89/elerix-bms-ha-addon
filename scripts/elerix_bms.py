#!/usr/bin/env python3
"""
Elerix EX-S5 BMS RS485 reader - FoxESS/PACE ASCII protocol, LV5200 chip

Usage: python3 elerix_bms.py [port] [baudrate] [address]
Default: /dev/ttyUSB0, 9600, 2

Returns JSON with all available battery data.
"""

import serial
import json
import sys
import time

PORT    = sys.argv[1] if len(sys.argv) > 1 else "/dev/ttyUSB0"
BAUD    = int(sys.argv[2]) if len(sys.argv) > 2 else 9600
ADDRESS = int(sys.argv[3]) if len(sys.argv) > 3 else 2


def lchksum(lenid: int) -> int:
    s = ((lenid >> 10) & 0xF) + ((lenid >> 6) & 0xF) + \
        ((lenid >> 2) & 0xF) + (lenid & 0x3)
    s = (~s + 1) & 0xF
    return (s << 12) | lenid


def chksum(frame_str: str) -> str:
    s = sum(ord(c) for c in frame_str)
    s = (~s + 1) & 0xFFFF
    return f"{s:04X}"


def make_request(addr: int, cid2: int, ver: str = "20", pack_num: int = None) -> bytes:
    adr    = f"{addr:02X}"
    cid2s  = f"{cid2:02X}"
    # pack_num allows querying specific pack in multi-pack systems (both at same ADR)
    # INFO=0x01 = pack 1 (slave), INFO=0x02 = pack 2 (master), None = use addr
    info   = f"{pack_num:02X}" if pack_num is not None else f"{addr:02X}"
    lenid  = lchksum(len(info) // 2)
    length = f"{lenid:04X}"
    body   = ver + adr + "46" + cid2s + length + info
    return f"~{body}{chksum(body)}\r".encode("ascii")


def _extract_payload_data(raw: bytes):
    """Decode PACE frame, check RTN, return data bytes or None."""
    try:
        text = raw.decode("ascii", errors="ignore").strip()
        if not text.startswith("~"):
            return None, f"bad_frame:{raw[:20].hex()}"
        payload = text[1:].replace("\r", "")
        rtn = payload[6:8]
        if rtn != "00":
            return None, f"bms_rtn:{rtn}"
        info_hex = payload[12:-4]
        data_hex = info_hex[4:]  # skip INFOFLAG(1B) + CmdValue(1B)
        if len(data_hex) % 2:
            data_hex = data_hex[:-1]
        return bytes.fromhex(data_hex), None
    except Exception as e:
        return None, str(e)


def parse_cell_sample(raw: bytes) -> dict:
    """CID2=0x42 — cell voltages, temperatures, current, voltage, capacity, cycles."""
    data, err = _extract_payload_data(raw)
    if err:
        return {"error": err}
    try:
        idx = 0
        result = {}

        ncells = data[idx]; idx += 1
        cells = []
        for i in range(ncells):
            v = int.from_bytes(data[idx:idx+2], "big"); idx += 2
            cells.append(round(v / 1000, 3))
        result["cell_voltages_v"] = cells
        result["cell_count"] = ncells

        ntemps = data[idx]; idx += 1
        # Temps: [0]=BMS board, [1]=avg cells 1-4, [2]=avg cells 5-8,
        #        [3]=avg cells 9-12, [4]=avg cells 13-16
        temp_names = ["temp_bms_c", "temp_cells14_c", "temp_cells58_c",
                      "temp_cells912_c", "temp_cells1316_c"]
        temps_c = []
        for i in range(ntemps):
            t = int.from_bytes(data[idx:idx+2], "big"); idx += 2
            temps_c.append(round((t - 2731) / 10, 1))
        result["temperatures_c"] = temps_c
        for i, name in enumerate(temp_names):
            if i < len(temps_c):
                result[name] = temps_c[i]

        cur = int.from_bytes(data[idx:idx+2], "big", signed=False)
        if cur > 32767: cur -= 65536
        result["current_a"] = round(cur / 10, 1); idx += 2

        volt = int.from_bytes(data[idx:idx+2], "big")
        result["voltage_v"] = round(volt / 1000, 3); idx += 2

        remain1 = int.from_bytes(data[idx:idx+2], "big")
        result["remaining_ah"] = round(remain1 / 100, 1); idx += 2

        user_items = data[idx]; idx += 1

        full1 = int.from_bytes(data[idx:idx+2], "big")
        result["full_capacity_ah"] = round(full1 / 100, 1); idx += 2

        cycles = int.from_bytes(data[idx:idx+2], "big")
        result["cycle_count"] = cycles; idx += 2

        # High-precision capacity for batteries > 65Ah (3-byte fields)
        if user_items >= 4 and idx + 6 <= len(data):
            remain2 = int.from_bytes(data[idx:idx+3], "big")
            result["remaining_ah"] = round(remain2 / 1000, 1); idx += 3
            full2 = int.from_bytes(data[idx:idx+3], "big")
            result["full_capacity_ah"] = round(full2 / 1000, 1); idx += 3

        if idx + 2 <= len(data):
            soc = int.from_bytes(data[idx:idx+2], "big")
            if soc <= 1000:
                result["soc_pct"] = round(soc / 10, 1); idx += 2

        if idx + 2 <= len(data):
            soh = int.from_bytes(data[idx:idx+2], "big")
            if soh <= 1000:
                result["soh_pct"] = round(soh / 10, 1)

        if cells:
            result["cell_min_v"]   = min(cells)
            result["cell_max_v"]   = max(cells)
            result["cell_diff_mv"] = round((max(cells) - min(cells)) * 1000, 1)
        if temps_c:
            result["temp_max_c"] = max(temps_c)
            result["temp_min_c"] = min(temps_c)

        return result
    except Exception as e:
        return {"error": str(e)}


def parse_running_data(raw: bytes) -> dict:
    """CID2=0x99 — Running Data: all 16 cells, 7 temps, SOC, alarms, I/O status."""
    data, err = _extract_payload_data(raw)
    if err:
        return {}
    try:
        idx = 0
        result = {}

        # 16 cell voltages (fixed)
        cell_qty = data[idx]; idx += 1
        cells = []
        for i in range(cell_qty):
            v = int.from_bytes(data[idx:idx+2], "big"); idx += 2
            cells.append(round(v / 1000, 3))
        result["cell_voltages_v"] = cells
        result["cell_count"] = cell_qty
        if cells:
            result["cell_min_v"]   = min(cells)
            result["cell_max_v"]   = max(cells)
            result["cell_diff_mv"] = round((max(cells) - min(cells)) * 1000, 1)

        # 7 temperatures (accuracy=1, formula: raw-2731 = °C)
        temp_qty = data[idx]; idx += 1
        temp_labels = ["temp_cell1_c", "temp_cell2_c", "temp_cell3_c", "temp_cell4_c",
                       "temp_dsg_mosfet_c", "temp_chg_mosfet_c", "temp_env_c"]
        temps_c = []
        for i in range(temp_qty):
            t = int.from_bytes(data[idx:idx+2], "big"); idx += 2
            tc = t - 2731
            temps_c.append(tc)
            if i < len(temp_labels):
                result[temp_labels[i]] = tc
        if temps_c:
            result["temp_max_c"] = max(temps_c)
            result["temp_min_c"] = min(temps_c)

        # Current (same encoding as 0x42, /10 → A)
        cur = int.from_bytes(data[idx:idx+2], "big", signed=False)
        if cur > 32767: cur -= 65536
        result["current_a"] = round(cur / 10, 1); idx += 2

        # Stack voltage (/1000 → V)
        sv = int.from_bytes(data[idx:idx+2], "big")
        result["voltage_v"] = round(sv / 1000, 3); idx += 2

        # Remain capacity (accuracy=1, /10 → Ah)
        rc = int.from_bytes(data[idx:idx+2], "big")
        result["remaining_ah_est"] = round(rc / 10, 1); idx += 2

        # Skip: self_define(1) + rev(2+2+3+3) = 11 bytes
        idx += 11

        # Pack voltage
        pv = int.from_bytes(data[idx:idx+2], "big")
        result["pack_volt_v"] = round(pv / 1000, 3); idx += 2

        # SOC (/10 → %)
        if idx + 2 <= len(data):
            soc = int.from_bytes(data[idx:idx+2], "big")
            result["soc_pct"] = round(soc / 10, 1); idx += 2

        # Max/min cell voltage + cell numbers
        if idx + 6 <= len(data):
            result["cell_max_v"]   = round(int.from_bytes(data[idx:idx+2], "big") / 1000, 3); idx += 2
            result["cell_min_v"]   = round(int.from_bytes(data[idx:idx+2], "big") / 1000, 3); idx += 2
            result["cell_max_num"] = data[idx]; idx += 1
            result["cell_min_num"] = data[idx]; idx += 1

        # Max/min temp + temp numbers (acc=1, raw-2731)
        if idx + 6 <= len(data):
            result["temp_max_c"]    = int.from_bytes(data[idx:idx+2], "big") - 2731; idx += 2
            result["temp_min_c"]    = int.from_bytes(data[idx:idx+2], "big") - 2731; idx += 2
            result["temp_max_num"]  = data[idx]; idx += 1
            result["temp_min_num"]  = data[idx]; idx += 1

        # Cell delta voltage (/1000 → V → report in mV)
        if idx + 2 <= len(data):
            delta = int.from_bytes(data[idx:idx+2], "big")
            result["cell_diff_mv"] = round(delta / 1000 * 1000, 1); idx += 2

        # I/O status bytes
        if idx + 2 <= len(data):
            result["io_status1"] = data[idx]; idx += 1
            result["io_status2"] = data[idx]; idx += 1

        # Afe balance status (2 bytes, bitmask)
        if idx + 2 <= len(data):
            result["afe_balance"] = int.from_bytes(data[idx:idx+2], "big"); idx += 2

        # Warning status (2 bytes, bitmask — 0 = ok)
        if idx + 2 <= len(data):
            result["warning_status"] = int.from_bytes(data[idx:idx+2], "big"); idx += 2

        # Alarm status (3 bytes, bitmask — 0 = ok)
        if idx + 3 <= len(data):
            result["alarm_status"] = int.from_bytes(data[idx:idx+3], "big"); idx += 3

        return result
    except Exception as e:
        print(f"[DEBUG] parse_running_data error: {e}", file=sys.stderr)
        return {}


def query(port: str, baud: int, addr: int, cid2: int,
          timeout: float = 3.0, ver: str = "20", parser=None, pack_num: int = None,
          retries: int = 1) -> dict:
    if parser is None:
        parser = parse_cell_sample
    pn = pack_num if pack_num is not None else addr
    for attempt in range(retries + 1):
        try:
            # inter_byte_timeout: return as soon as no new byte for 200ms — avoids
            # waiting the full `timeout` for a frame that ends well before 512 bytes
            ser = serial.Serial(port, baud, bytesize=8, parity="N",
                                stopbits=1, timeout=timeout,
                                inter_byte_timeout=0.2)
            time.sleep(0.1)
            ser.reset_input_buffer()
            req = make_request(addr, cid2, ver=ver, pack_num=pack_num)
            print(f"[DEBUG] TX cid2={hex(cid2)} addr={addr} pack={pn} ver={ver}: {req}", file=sys.stderr, flush=True)
            ser.write(req)
            resp = ser.read_until(b'\r', size=512)
            ser.close()
            print(f"[DEBUG] RX {len(resp)} bytes", file=sys.stderr, flush=True)
            if not resp:
                if attempt < retries:
                    print(f"[WARN] no_response attempt {attempt+1}, retrying...", file=sys.stderr, flush=True)
                    time.sleep(0.5)
                    continue
                return {"error": "no_response"}
            return parser(resp)
        except Exception as e:
            if attempt < retries:
                print(f"[WARN] query error attempt {attempt+1}: {e}, retrying...", file=sys.stderr, flush=True)
                time.sleep(0.5)
                continue
            return {"error": str(e)}


def read_battery(port: str, baud: int, addr: int, ver: str = "20", pack_num: int = None) -> dict:
    """Query one battery and return merged result from 0x42 + 0x99.

    pack_num: for multi-pack systems where multiple packs share the same ADR.
              INFO=0x01 = pack 1 (slave), INFO=0x02 = pack 2 (master).
              If None, uses addr value (single-pack default).
    """
    # Primary: cell sample data (capacity, cycles, SOH)
    result = query(port, baud, addr, 0x42, ver=ver, parser=parse_cell_sample, pack_num=pack_num)
    if "error" in result:
        return result

    # Secondary: running data (all 16 cells, SOC, alarms, detailed stats)
    running = query(port, baud, addr, 0x99, ver=ver, parser=parse_running_data, pack_num=pack_num)
    if running:
        # Running data takes priority for cells, temps, current, voltage, SOC
        result.update(running)

    # Compute derived values
    v = result.get("voltage_v") or result.get("pack_volt_v", 0)
    i = result.get("current_a", 0)
    result["power_w"] = round(v * i, 1)

    full = result.get("full_capacity_ah", 0)
    remain = result.get("remaining_ah", 0)
    if full > 0:
        result["soc_calc_pct"] = round(remain / full * 100, 1)

    # SOH fallback: compute from measured full_capacity vs nominal 100 Ah
    if "soh_pct" not in result and full > 0:
        nominal_ah = int(sys.argv[5]) if len(sys.argv) > 5 else 100
        result["soh_pct"] = round(full / nominal_ah * 100, 1)

    result["addr"] = addr
    if pack_num is not None:
        result["pack_num"] = pack_num
    return result


def main():
    if len(sys.argv) > 2:
        pack_num = int(sys.argv[4]) if len(sys.argv) > 4 else None
        result = read_battery(PORT, BAUD, ADDRESS, pack_num=pack_num)
    else:
        # Discovery mode
        found = None
        for baud in [9600, 19200, 115200]:
            for addr in [0, 1, 2, 3]:
                r = query(PORT, baud, addr, 0x42)
                if "error" not in r:
                    found = read_battery(PORT, baud, addr)
                    found["baudrate"] = baud
                    break
            if found:
                break
        result = found or {"error": "no_response", "port": PORT}

    print(json.dumps(result))


if __name__ == "__main__":
    main()
