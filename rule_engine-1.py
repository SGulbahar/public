"""
Kural Tabanlı Anomali Motoru
Noise Reduction:
  - Minimum sample size (20 tx)
  - Cooldown (10 dakika)
  - SYS vs BIZ esik ayrimi
  - Deduplication
  - Hata kodu sapma tespiti
"""
import logging
import time
from dataclasses import dataclass
from engine.settings import engine_settings

logger = logging.getLogger(__name__)

MIN_TX_COUNT = 20
COOLDOWN_SECONDS = 600
SYS_ERROR_CODE_THRESHOLD = 10
BIZ_ERROR_CODE_THRESHOLD = 30


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
        logger.info("Kural Motoru baslatildi.")

    def detect(self, features: dict) -> list:
        service = features.get("service", "unknown")
        channel = features.get("channel_code", "unknown")
        tx_count = features.get("tx_count", 0)
        error_rate = features.get("error_rate", 0)
        elapsed_mean = features.get("elapsed_mean", 0)
        elapsed_max = features.get("elapsed_max", 0)
        sys_error_count = features.get("sys_error_count", 0)
        sys_error_rate = features.get("sys_error_rate", 0)
        biz_error_rate = features.get("biz_error_rate", 0)
        result_codes = features.get("result_codes", {})

        key = service + ":" + channel

        # Minimum sample size
        if tx_count < MIN_TX_COUNT:
            return []

        anomalies = []

        # Cooldown kontrolu (elapsed ve error rate kurallari icin)
        if not self._in_cooldown(key):

            # Kural 1: Elapsed Disaster
            if elapsed_max >= engine_settings.rule_elapsed_disaster:
                anomalies.append(RuleAnomaly(
                    rule_name="elapsed_disaster",
                    channel_code=channel,
                    service=service,
                    severity="DISASTER",
                    score=elapsed_max,
                    count=tx_count,
                    elapsed_mean=elapsed_mean,
                    error_rate=error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Kritik gecikme: {int(elapsed_max)}ms",
                    details=f"Maksimum elapsed {int(elapsed_max)}ms. Esik: {engine_settings.rule_elapsed_disaster}ms. Islem: {tx_count}",
                ))

            # Kural 2: Elapsed High
            elif elapsed_mean >= engine_settings.rule_elapsed_high:
                anomalies.append(RuleAnomaly(
                    rule_name="elapsed_high",
                    channel_code=channel,
                    service=service,
                    severity="HIGH",
                    score=elapsed_mean,
                    count=tx_count,
                    elapsed_mean=elapsed_mean,
                    error_rate=error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Yuksek gecikme: {int(elapsed_mean)}ms ortalama",
                    details=f"Ortalama elapsed {int(elapsed_mean)}ms. Esik: {engine_settings.rule_elapsed_high}ms. Islem: {tx_count}",
                ))

            # Kural 3: SYS Error Rate
            sys_disaster = engine_settings.rule_error_rate_disaster * 0.6
            sys_high = engine_settings.rule_error_rate_high * 0.6

            if sys_error_rate >= sys_disaster and sys_error_count >= MIN_TX_COUNT:
                anomalies.append(RuleAnomaly(
                    rule_name="sys_error_rate_disaster",
                    channel_code=channel,
                    service=service,
                    severity="DISASTER",
                    score=sys_error_rate,
                    count=sys_error_count,
                    elapsed_mean=elapsed_mean,
                    error_rate=sys_error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Kritik sistem hatasi: %{sys_error_rate*100:.1f}",
                    details=f"SYS hata orani %{sys_error_rate*100:.1f}. Sayi: {sys_error_count}",
                ))
            elif sys_error_rate >= sys_high and sys_error_count >= MIN_TX_COUNT:
                anomalies.append(RuleAnomaly(
                    rule_name="sys_error_rate_high",
                    channel_code=channel,
                    service=service,
                    severity="HIGH",
                    score=sys_error_rate,
                    count=sys_error_count,
                    elapsed_mean=elapsed_mean,
                    error_rate=sys_error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Yuksek sistem hatasi: %{sys_error_rate*100:.1f}",
                    details=f"SYS hata orani %{sys_error_rate*100:.1f}. Sayi: {sys_error_count}",
                ))

            # Kural 4: BIZ Error Rate
            biz_disaster = engine_settings.rule_error_rate_disaster
            biz_high = engine_settings.rule_error_rate_high * 1.5

            if biz_error_rate >= biz_disaster:
                anomalies.append(RuleAnomaly(
                    rule_name="biz_error_rate_disaster",
                    channel_code=channel,
                    service=service,
                    severity="DISASTER",
                    score=biz_error_rate,
                    count=features.get("biz_error_count", 0),
                    elapsed_mean=elapsed_mean,
                    error_rate=biz_error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Kritik is hatasi: %{biz_error_rate*100:.1f}",
                    details=f"BIZ hata orani %{biz_error_rate*100:.1f}.",
                ))
            elif biz_error_rate >= biz_high:
                anomalies.append(RuleAnomaly(
                    rule_name="biz_error_rate_high",
                    channel_code=channel,
                    service=service,
                    severity="HIGH",
                    score=biz_error_rate,
                    count=features.get("biz_error_count", 0),
                    elapsed_mean=elapsed_mean,
                    error_rate=biz_error_rate,
                    result_code=0,
                    summary=f"{service} [{channel}] - Yuksek is hatasi: %{biz_error_rate*100:.1f}",
                    details=f"BIZ hata orani %{biz_error_rate*100:.1f}.",
                ))

            # Deduplication ve cooldown
            if len(anomalies) > 1:
                anomalies = self._deduplicate(anomalies)
            if anomalies:
                self._set_cooldown(key)

        # Kural 5: Hata Kodu Spike (ayri cooldown - her kod icin)
        error_code_anomalies = self._check_error_code_spikes(
            service, channel, result_codes, elapsed_mean
        )
        anomalies.extend(error_code_anomalies)

        # Kural 6: Servis Down
        if tx_count == 0:
            now = time.time()
            if key not in self._service_zero_start:
                self._service_zero_start[key] = now
            else:
                zero_duration = now - self._service_zero_start[key]
                threshold = engine_settings.rule_service_down_minutes * 60
                if zero_duration >= threshold:
                    anomalies.append(RuleAnomaly(
                        rule_name="service_down",
                        channel_code=channel,
                        service=service,
                        severity="DISASTER",
                        score=zero_duration,
                        count=0,
                        elapsed_mean=0,
                        error_rate=0,
                        result_code=0,
                        summary=f"{service} [{channel}] - Servis yanit vermiyor ({int(zero_duration/60)} dk)",
                        details=f"{int(zero_duration/60)} dakikadir islem yok.",
                    ))
        else:
            self._service_zero_start.pop(key, None)

        return anomalies

    def _check_error_code_spikes(self, service, channel, result_codes, elapsed_mean) -> list:
        """
        Belirli bir hata kodunun spike yapmasini tespit eder.
        Her hata kodu icin ayri cooldown uygulanir.
        """
        anomalies = []
        for rc, count in result_codes.items():
            ec_key = f"{service}:{channel}:rc{rc}"

            if self._in_error_code_cooldown(ec_key):
                continue

            if rc < 7500 and count >= SYS_ERROR_CODE_THRESHOLD:
                # SYS hata kodu spike
                severity = "DISASTER" if count >= SYS_ERROR_CODE_THRESHOLD * 3 else "HIGH"
                anomalies.append(RuleAnomaly(
                    rule_name="sys_error_code_spike",
                    channel_code=channel,
                    service=service,
                    severity=severity,
                    score=float(count),
                    count=count,
                    elapsed_mean=elapsed_mean,
                    error_rate=0,
                    result_code=rc,
                    summary=f"{service} [{channel}] - SYS Hata Kodu Spike: {rc} ({count} kez)",
                    details=f"Sistem hata kodu {rc} bu pencerede {count} kez goruldu. Esik: {SYS_ERROR_CODE_THRESHOLD}.",
                ))
                self._set_error_code_cooldown(ec_key)

            elif rc >= 7500 and count >= BIZ_ERROR_CODE_THRESHOLD:
                # BIZ hata kodu spike
                severity = "HIGH" if count >= BIZ_ERROR_CODE_THRESHOLD * 2 else "WARNING"
                anomalies.append(RuleAnomaly(
                    rule_name="biz_error_code_spike",
                    channel_code=channel,
                    service=service,
                    severity=severity,
                    score=float(count),
                    count=count,
                    elapsed_mean=elapsed_mean,
                    error_rate=0,
                    result_code=rc,
                    summary=f"{service} [{channel}] - BIZ Hata Kodu Spike: {rc} ({count} kez)",
                    details=f"Is hata kodu {rc} bu pencerede {count} kez goruldu. Esik: {BIZ_ERROR_CODE_THRESHOLD}.",
                ))
                self._set_error_code_cooldown(ec_key)

        return anomalies

    def _in_cooldown(self, key: str) -> bool:
        if key not in self._cooldown:
            return False
        elapsed = time.time() - self._cooldown[key]
        if elapsed < COOLDOWN_SECONDS:
            return True
        del self._cooldown[key]
        return False

    def _set_cooldown(self, key: str):
        self._cooldown[key] = time.time()

    def _in_error_code_cooldown(self, key: str) -> bool:
        if key not in self._error_code_cooldown:
            return False
        elapsed = time.time() - self._error_code_cooldown[key]
        if elapsed < COOLDOWN_SECONDS:
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
        }
