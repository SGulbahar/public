"""
Kural Tabanlı Anomali Motoru
Noise Reduction:
  - Minimum sample size
  - Cooldown (10 dakika)
  - SYS vs BIZ esik ayrimi
  - Deduplication (pencere bazli)
"""
import logging
import time
from dataclasses import dataclass
from engine.settings import engine_settings

logger = logging.getLogger(__name__)

MIN_TX_COUNT = 10
COOLDOWN_SECONDS = 600


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

        key = service + ":" + channel

        # Minimum sample size kontrolu
        if tx_count < MIN_TX_COUNT:
            return []

        # Cooldown kontrolu
        if self._in_cooldown(key):
            return []

        anomalies = []

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
                details=f"Maksimum elapsed {int(elapsed_max)}ms. Esik: {engine_settings.rule_elapsed_disaster}ms. Islem sayisi: {tx_count}",
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
                details=f"Ortalama elapsed {int(elapsed_mean)}ms. Esik: {engine_settings.rule_elapsed_high}ms. Islem sayisi: {tx_count}",
            ))

        # Kural 3: SYS Error Rate Disaster (daha dusuk esik)
        sys_disaster_threshold = engine_settings.rule_error_rate_disaster * 0.6
        sys_high_threshold = engine_settings.rule_error_rate_high * 0.6

        if sys_error_rate >= sys_disaster_threshold and sys_error_count >= MIN_TX_COUNT:
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
                details=f"SYS hata orani %{sys_error_rate*100:.1f}. Esik: %{sys_disaster_threshold*100:.0f}. Sayi: {sys_error_count}",
            ))
        elif sys_error_rate >= sys_high_threshold and sys_error_count >= MIN_TX_COUNT:
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
                details=f"SYS hata orani %{sys_error_rate*100:.1f}. Esik: %{sys_high_threshold*100:.0f}. Sayi: {sys_error_count}",
            ))

        # Kural 4: BIZ Error Rate (daha yuksek esik)
        biz_disaster_threshold = engine_settings.rule_error_rate_disaster
        biz_high_threshold = engine_settings.rule_error_rate_high * 1.5

        if biz_error_rate >= biz_disaster_threshold:
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
                details=f"BIZ hata orani %{biz_error_rate*100:.1f}. Esik: %{biz_disaster_threshold*100:.0f}",
            ))
        elif biz_error_rate >= biz_high_threshold:
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
                details=f"BIZ hata orani %{biz_error_rate*100:.1f}. Esik: %{biz_high_threshold*100:.0f}",
            ))

        # Kural 5: Servis Down
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
                        details=f"{int(zero_duration/60)} dakikadir islem yok. Esik: {engine_settings.rule_service_down_minutes} dk",
                    ))
        else:
            self._service_zero_start.pop(key, None)

        # Deduplication - pencerede en yuksek severity'yi sec
        if len(anomalies) > 1:
            anomalies = self._deduplicate(anomalies)

        # Cooldown baslat
        if anomalies:
            self._set_cooldown(key)

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

    @staticmethod
    def _deduplicate(anomalies: list) -> list:
        sev_order = {"WARNING": 1, "HIGH": 2, "DISASTER": 3}
        best = max(anomalies, key=lambda a: sev_order.get(a.severity, 1))
        return [best]

    def cooldown_stats(self) -> dict:
        now = time.time()
        active = sum(1 for t in self._cooldown.values() if now - t < COOLDOWN_SECONDS)
        return {"active_cooldowns": active, "total_keys": len(self._cooldown)}
