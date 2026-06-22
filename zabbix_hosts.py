#!/usr/bin/env python3
"""
Zabbix 7.2.4 - Host adi, IP adresi ve tag bilgilerini JSON olarak ceken script.

Kullanim:
    python3 zabbix_hosts.py

Gereksinim:
    pip install requests

Not:
    Zabbix 7.0+ ile API tokeni kullanmak onerilir (Users -> API tokens).
    Eski user.login/password yontemi de hala calisir, alternatif fonksiyon
    asagida verilmistir.
"""

import json
import requests

# ---------------------------------------------------------------------------
# AYARLAR - kendi ortamina gore duzenle
# ---------------------------------------------------------------------------
ZABBIX_URL = "https://zabbix.example.com/api_jsonrpc.php"  # kendi URL'in
API_TOKEN = "BURAYA_API_TOKEN_YAZ"  # Users -> API tokens'tan olusturulan token

# Eger token yerine kullanici/parola ile giris yapmak istersen:
USE_LOGIN = False
ZABBIX_USER = "Admin"
ZABBIX_PASSWORD = "sifre"


def zabbix_request(method: str, params: dict, auth_token: str = None) -> dict:
    headers = {"Content-Type": "application/json-rpc"}
    payload = {
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": 1,
    }

    # Zabbix 7.x: auth artik body'de degil, Authorization header'inda
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"

    response = requests.post(ZABBIX_URL, headers=headers, json=payload, timeout=15)
    response.raise_for_status()
    result = response.json()

    if "error" in result:
        raise RuntimeError(f"Zabbix API hatasi: {result['error']}")

    return result["result"]


def login_get_token() -> str:
    """Kullanici adi / parola ile giris yapip auth token doner."""
    result = zabbix_request(
        "user.login",
        {"username": ZABBIX_USER, "password": ZABBIX_PASSWORD},
    )
    return result


def get_hosts(auth_token: str = None) -> list:
    """
    Tum hostlari, IP adreslerini ve tag bilgilerini ceker.
    """
    params = {
        "output": ["hostid", "host", "name", "status"],
        "selectInterfaces": ["ip", "dns", "type", "main"],
        "selectTags": "extend",
        "selectInventory": ["os", "location"],  # istersen kaldirabilirsin
    }

    hosts = zabbix_request("host.get", params, auth_token)
    return hosts


def format_hosts(raw_hosts: list) -> list:
    """
    Ham API ciktisini sade bir JSON yapisina cevirir:
    [
      {
        "host": "...",
        "name": "...",
        "ip": "...",
        "tags": {"key": "value", ...}
      },
      ...
    ]
    """
    formatted = []

    for h in raw_hosts:
        # Ana interface'in (main=1) IP'sini bul, yoksa ilk interface'i al
        ip_address = None
        interfaces = h.get("interfaces", [])
        main_iface = next((i for i in interfaces if i.get("main") == "1"), None)
        if main_iface:
            ip_address = main_iface.get("ip")
        elif interfaces:
            ip_address = interfaces[0].get("ip")

        tags = {t["tag"]: t.get("value", "") for t in h.get("tags", [])}

        formatted.append(
            {
                "hostid": h.get("hostid"),
                "host": h.get("host"),
                "name": h.get("name"),
                "ip": ip_address,
                "status": "enabled" if h.get("status") == "0" else "disabled",
                "tags": tags,
            }
        )

    return formatted


def main():
    auth_token = None

    if USE_LOGIN:
        auth_token = login_get_token()
    else:
        auth_token = API_TOKEN

    raw_hosts = get_hosts(auth_token)
    result = format_hosts(raw_hosts)

    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Dosyaya kaydetmek istersen:
    # with open("hosts.json", "w", encoding="utf-8") as f:
    #     json.dump(result, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
