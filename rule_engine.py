"""
Kural Tabanli Anomali Motoru
- Minimum ornek boyutu
- Soguma suresi (cooldown)
- SYS ve BIZ esik ayrimi
- Tekillestime (deduplication)
- Hata kodu kayan pencere (sliding window)
- p95/p99 elapsed (anlik spike false positive engeli)
- Minimum yavas islem sayisi
- Servis whitelist destegi
"""
import logging
import time
from collections import defaultdict
from dataclasses import dataclass
from engine.settings import engine_settings

logger = logging.getLogger(__name__)

MIN_TX_COUNT = 20
MIN_SLOW_TX_COUNT = 3
COOLDOWN_SECONDS = 600
SYS_ERROR_CODE_THRESHOLD = 10
BIZ_ERROR_CODE_THRESHOLD = 30
SLIDING_WINDOW_SECONDS = 1800
ELAPSED_P99_DISASTER = 30000
ELAPSED_P95_HIGH = 15000

# Whitelist: {(service, channel_code, rule_name)} seti
# '*' wildcard destegi var
_WHITELIST: set = set()


def whitelist_yukle(kayitlar: list):
    """DB'den gelen whitelist kayitlarini yukle."""
    global _WHITELIST
    _WHITELIST = set()
    for r in kayitlar:
        _WHITELIST.add((r['service_name'], r['channel_code'], r['rule_name']))
    logger.info(f"Whitelist yuklendi: {len(_WHITELIST)} kural")


def whitelist_kontrol(service: str, channel: str, rule_name: str) -> bool:
    """True donerse bu anomali whitelist'te — uretme."""
    checks = [
        (service, channel, rule_name),
        (service, channel, '*'),
        (service, '*', rule_name),
        (service, '*', '*'),
        ('*', channel, rule_name),
        ('*', '*', rule_name),
        ('*', '*', '*'),
    ]
    for key in checks:
        if key in _WHITELIST:
            logger.debug(f"Whitelist eslesti: {service}/{channel}/{rule_name} -> {key}")
            return True
    return False


@dataclass
class RuleAnomaly:
    rule_name: str
    channel_code: str
    service: str
    severity: str
    score: float
    count: int
    elapsed_mean: float
    error_rate: float
    result_code: int
    summary: str
    details: str


class RuleEngine:
    def __init__(self):
        self._cooldown: dict = {}
        self._service_zero_start: dict = {}
        self._error_code_cooldown: dict = {}
        self._error_code_window: dict = defaultdict(list)
        logger.info("Kural Motoru baslatildi.")

    def detect(self, features: dict) -> list:
        service = features.get("service", "unknown")
        channel = features.get("channel_code", "unknown")
        tx_count = features.get("tx_count", 0)
        error_rate = features.get("error_rate", 0)
        elapsed_mean = features.get("elapsed_mean", 0)
        elapsed_p95 = features.get("elapsed_p95", 0)
        elapsed_p99 = features.get("elapsed_p99", 0)
        slow_count_disaster = features.get("slow_count_disaster", 0)
        slow_count_high = features.get("slow_count_high", 0)
        sys_error_count = features.get("sys_error_count", 0)
        sys_error_rate = features.get("sys_error_rate", 0)
        biz_error_rate = features.get("biz_error_rate", 0)
        biz_error_count = features.get("biz_error_count", 0)
        result_codes = features.get("result_codes", {})

        key = service + ":" + channel

        if tx_count < MIN_TX_COUNT:
            self._update_error_code_window(service, channel, result_codes)
            return []

        anomalies = []

        if not self._in_cooldown(key):

            # Kural 1: p99 elapsed DISASTER
            if elapsed_p99 >= ELAPSED_P99_DISASTER and slow_count_disaster >= MIN_SLOW_TX_COUNT:
                if not whitelist_kontrol(service, channel, "elapsed_p99_disaster"):
                    anomalies.append(RuleAnomaly(
                        rule_name="elapsed_p99_disaster",
                        channel_code=channel, service=service,
                        severity="DISASTER", score=elapsed_p99,
                        count=tx_count, elapsed_mean=elapsed_mean,
                        error_rate=error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Kritik gecikme: p99={int(elapsed_p99)}ms ({slow_count_disaster} islem)",
                        details=f"{slow_count_disaster} islem {ELAPSED_P99_DISASTER}ms esigini asti. p99={int(elapsed_p99)}ms. Toplam: {tx_count}",
                    ))

            # Kural 2: p95 elapsed HIGH
            elif elapsed_p95 >= ELAPSED_P95_HIGH and slow_count_high >= MIN_SLOW_TX_COUNT:
                if not whitelist_kontrol(service, channel, "elapsed_p95_high"):
                    anomalies.append(RuleAnomaly(
                        rule_name="elapsed_p95_high",
                        channel_code=channel, service=service,
                        severity="HIGH", score=elapsed_p95,
                        count=tx_count, elapsed_mean=elapsed_mean,
                        error_rate=error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Yuksek gecikme: p95={int(elapsed_p95)}ms ({slow_count_high} islem)",
                        details=f"{slow_count_high} islem {ELAPSED_P95_HIGH}ms esigini asti. p95={int(elapsed_p95)}ms. Toplam: {tx_count}",
                    ))

            # Kural 3: SYS hata orani
            sys_disaster = engine_settings.rule_error_rate_disaster * 0.6
            sys_high = engine_settings.rule_error_rate_high * 0.6

            if sys_error_rate >= sys_disaster and sys_error_count >= MIN_TX_COUNT:
                if not whitelist_kontrol(service, channel, "sys_error_rate_disaster"):
                    anomalies.append(RuleAnomaly(
                        rule_name="sys_error_rate_disaster",
                        channel_code=channel, service=service,
                        severity="DISASTER", score=sys_error_rate,
                        count=sys_error_count, elapsed_mean=elapsed_mean,
                        error_rate=sys_error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Kritik sistem hatasi: %{sys_error_rate*100:.1f}",
                        details=f"SYS hata orani %{sys_error_rate*100:.1f}. Sayi: {sys_error_count}",
                    ))
            elif sys_error_rate >= sys_high and sys_error_count >= MIN_TX_COUNT:
                if not whitelist_kontrol(service, channel, "sys_error_rate_high"):
                    anomalies.append(RuleAnomaly(
                        rule_name="sys_error_rate_high",
                        channel_code=channel, service=service,
                        severity="HIGH", score=sys_error_rate,
                        count=sys_error_count, elapsed_mean=elapsed_mean,
                        error_rate=sys_error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Yuksek sistem hatasi: %{sys_error_rate*100:.1f}",
                        details=f"SYS hata orani %{sys_error_rate*100:.1f}. Sayi: {sys_error_count}",
                    ))

            # Kural 4: BIZ hata orani
            biz_disaster = engine_settings.rule_error_rate_disaster
            biz_high = engine_settings.rule_error_rate_high * 1.5

            if biz_error_rate >= biz_disaster and biz_error_count >= MIN_TX_COUNT:
                if not whitelist_kontrol(service, channel, "biz_error_rate_disaster"):
                    anomalies.append(RuleAnomaly(
                        rule_name="biz_error_rate_disaster",
                        channel_code=channel, service=service,
                        severity="DISASTER", score=biz_error_rate,
                        count=biz_error_count, elapsed_mean=elapsed_mean,
                        error_rate=biz_error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Kritik is hatasi: %{biz_error_rate*100:.1f}",
                        details=f"BIZ hata orani %{biz_error_rate*100:.1f}.",
                    ))
            elif biz_error_rate >= biz_high and biz_error_count >= MIN_TX_COUNT:
                if not whitelist_kontrol(service, channel, "biz_error_rate_high"):
                    anomalies.append(RuleAnomaly(
                        rule_name="biz_error_rate_high",
                        channel_code=channel, service=service,
                        severity="HIGH", score=biz_error_rate,
                        count=biz_error_count, elapsed_mean=elapsed_mean,
                        error_rate=biz_error_rate, result_code=0,
                        summary=f"{service} [{channel}] - Yuksek is hatasi: %{biz_error_rate*100:.1f}",
                        details=f"BIZ hata orani %{biz_error_rate*100:.1f}.",
                    ))

            if len(anomalies) > 1:
                anomalies = self._deduplicate(anomalies)
            if anomalies:
                self._set_cooldown(key)

        # Kural 5: Hata kodu sliding window
        self._update_error_code_window(service, channel, result_codes)
        ec_anomalies = self._check_error_code_window(service, channel, elapsed_mean)
        anomalies.extend(ec_anomalies)

        # Kural 6: Servis down
        if tx_count == 0:
            now = time.time()
            if key not in self._service_zero_start:
                self._service_zero_start[key] = now
            else:
                zero_duration = now - self._service_zero_start[key]
                threshold = engine_settings.rule_service_down_minutes * 60
                if zero_duration >= threshold:
                    if not whitelist_kontrol(service, channel, "service_down"):
                        anomalies.append(RuleAnomaly(
                            rule_name="service_down",
                            channel_code=channel, service=service,
                            severity="DISASTER", score=zero_duration,
                            count=0, elapsed_mean=0, error_rate=0, result_code=0,
                            summary=f"{service} [{channel}] - Servis yanit vermiyor ({int(zero_duration/60)} dk)",
                            details=f"{int(zero_duration/60)} dakikadir islem yok.",
                        ))
        else:
            self._service_zero_start.pop(key, None)

        return anomalies

    def _update_error_code_window(self, service, channel, result_codes):
        now = time.time()
        for rc, count in result_codes.items():
            if rc == 0:
                continue  # Basarili islem, spike kontrolune dahil etme
            ec_key = service + ":" + channel + ":rc" + str(rc)
            self._error_code_window[ec_key].append((now, count))
            self._error_code_window[ec_key] = [
                (t, c) for t, c in self._error_code_window[ec_key]
                if now - t <= SLIDING_WINDOW_SECONDS
            ]

    def _check_error_code_window(self, service, channel, elapsed_mean) -> list:
        anomalies = []
        now = time.time()
        prefix = service + ":" + channel + ":rc"
        for ec_key, entries in list(self._error_code_window.items()):
            if not ec_key.startswith(prefix):
                continue
            if self._in_error_code_cooldown(ec_key):
                continue
            window_count = sum(c for t, c in entries if now - t <= SLIDING_WINDOW_SECONDS)
            if window_count == 0:
                continue
            try:
                rc = int(ec_key.split(":rc")[1])
            except Exception:
                continue
            if rc < 7500 and window_count >= SYS_ERROR_CODE_THRESHOLD:
                if not whitelist_kontrol(service, channel, "sys_error_code_spike"):
                    severity = "DISASTER" if window_count >= SYS_ERROR_CODE_THRESHOLD * 3 else "HIGH"
                    anomalies.append(RuleAnomaly(
                        rule_name="sys_error_code_spike",
                        channel_code=channel, service=service,
                        severity=severity, score=float(window_count),
                        count=window_count, elapsed_mean=elapsed_mean,
                        error_rate=0, result_code=rc,
                        summary=f"{service} [{channel}] - SYS Hata Kodu Spike: {rc} (30dk {window_count} kez)",
                        details=f"Sistem hata kodu {rc} son 30 dakikada {window_count} kez goruldu. Esik: {SYS_ERROR_CODE_THRESHOLD}.",
                    ))
                    self._set_error_code_cooldown(ec_key)
                    self._error_code_window[ec_key].clear()
            elif rc >= 7500 and window_count >= BIZ_ERROR_CODE_THRESHOLD:
                if not whitelist_kontrol(service, channel, "biz_error_code_spike"):
                    severity = "HIGH" if window_count >= BIZ_ERROR_CODE_THRESHOLD * 2 else "WARNING"
                    anomalies.append(RuleAnomaly(
                        rule_name="biz_error_code_spike",
                        channel_code=channel, service=service,
                        severity=severity, score=float(window_count),
                        count=window_count, elapsed_mean=elapsed_mean,
                        error_rate=0, result_code=rc,
                        summary=f"{service} [{channel}] - BIZ Hata Kodu Spike: {rc} (30dk {window_count} kez)",
                        details=f"Is hata kodu {rc} son 30 dakikada {window_count} kez goruldu. Esik: {BIZ_ERROR_CODE_THRESHOLD}.",
                    ))
                    self._set_error_code_cooldown(ec_key)
                    self._error_code_window[ec_key].clear()
        return anomalies

    def _in_cooldown(self, key: str) -> bool:
        if key not in self._cooldown:
            return False
        if time.time() - self._cooldown[key] < COOLDOWN_SECONDS:
            return True
        del self._cooldown[key]
        return False

    def _set_cooldown(self, key: str):
        self._cooldown[key] = time.time()

    def _in_error_code_cooldown(self, key: str) -> bool:
        if key not in self._error_code_cooldown:
            return False
        if time.time() - self._error_code_cooldown[key] < COOLDOWN_SECONDS:
            return True
        del self._error_code_cooldown[key]
        return False

    def _set_error_code_cooldown(self, key: str):
        self._error_code_cooldown[key] = time.time()

    @staticmethod
    def _deduplicate(anomalies: list) -> list:
        sev_order = {"WARNING": 1, "HIGH": 2, "DISASTER": 3}
        best = max(anomalies, key=lambda a: sev_order.get(a.severity, 1))
        return [best]

    def cooldown_stats(self) -> dict:
        now = time.time()
        active = sum(1 for t in self._cooldown.values() if now - t < COOLDOWN_SECONDS)
        ec_active = sum(1 for t in self._error_code_cooldown.values() if now - t < COOLDOWN_SECONDS)
        return {
            "active_cooldowns": active,
            "active_error_code_cooldowns": ec_active,
            "window_tracked_codes": len(self._error_code_window),
            "whitelist_rules": len(_WHITELIST),
        }
