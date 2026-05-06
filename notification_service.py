"""
Bildirim Servisi - Microsoft Teams ve E-posta
"""
import logging
import asyncio
import smtplib
import ssl
import time
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import httpx

logger = logging.getLogger(__name__)

# Cooldown: ayni anomali icin tekrar bildirim gonderme
_notification_cooldown: dict = {}


class NotificationService:
    def __init__(self):
        self.enabled = False
        self.min_severity = "HIGH"
        self.teams_webhook_url = ""
        self.smtp_host = ""
        self.smtp_port = 587
        self.smtp_user = ""
        self.smtp_password = ""
        self.smtp_from = ""
        self.smtp_to = []
        self.cooldown_seconds = 300
        logger.info("Bildirim servisi baslatildi")

    def ayarlari_yukle(self, settings: dict):
        self.enabled = settings.get("notification_enabled", "false") == "true"
        self.min_severity = settings.get("notification_min_severity", "HIGH")
        self.teams_webhook_url = settings.get("teams_webhook_url", "")
        self.smtp_host = settings.get("smtp_host", "")
        self.smtp_port = int(settings.get("smtp_port", 587))
        self.smtp_user = settings.get("smtp_user", "")
        self.smtp_password = settings.get("smtp_password", "")
        self.smtp_from = settings.get("smtp_from", "")
        smtp_to_raw = settings.get("smtp_to", "")
        self.smtp_to = [e.strip() for e in smtp_to_raw.split(",") if e.strip()]
        self.cooldown_seconds = int(settings.get("notification_cooldown", 300))
        logger.info(
            f"Bildirim ayarlari yuklendi: enabled={self.enabled}, "
            f"min_severity={self.min_severity}, "
            f"teams={'var' if self.teams_webhook_url else 'yok'}, "
            f"smtp={'var' if self.smtp_host else 'yok'}"
        )

    def _siddet_sirasi(self, severity: str) -> int:
        return {"WARNING": 1, "HIGH": 2, "DISASTER": 3}.get(severity, 0)

    def _cooldown_kontrol(self, anahtar: str) -> bool:
        """True donerse cooldown'da — bildirim gonderme."""
        now = time.time()
        if anahtar in _notification_cooldown:
            if now - _notification_cooldown[anahtar] < self.cooldown_seconds:
                return True
        _notification_cooldown[anahtar] = now
        return False

    async def anomali_bildir(self, anomali: dict):
        if not self.enabled:
            return

        severity = anomali.get("severity", "WARNING")
        if self._siddet_sirasi(severity) < self._siddet_sirasi(self.min_severity):
            return

        # Cooldown kontrolu
        anahtar = f"{anomali.get('service')}:{anomali.get('channel_code')}:{anomali.get('anomaly_type')}"
        if self._cooldown_kontrol(anahtar):
            logger.debug(f"Bildirim cooldown'da: {anahtar}")
            return

        logger.info(f"Bildirim gonderiliyor: {anomali.get('service')} / {severity}")

        gorevler = []
        if self.teams_webhook_url:
            gorevler.append(self._teams_gonder(anomali))
        if self.smtp_host and self.smtp_to:
            gorevler.append(self._email_gonder(anomali))

        if gorevler:
            sonuclar = await asyncio.gather(*gorevler, return_exceptions=True)
            for i, sonuc in enumerate(sonuclar):
                if isinstance(sonuc, Exception):
                    logger.error(f"Bildirim hatasi [{i}]: {sonuc}")

    async def _teams_gonder(self, anomali: dict):
        severity = anomali.get("severity", "WARNING")
        renk_map = {"DISASTER": "FF0000", "HIGH": "FF8C00", "WARNING": "FFA500"}
        renk = renk_map.get(severity, "808080")

        siddet_tr = {"DISASTER": "KRİTİK", "HIGH": "YÜKSEK", "WARNING": "UYARI"}.get(severity, severity)

        mesaj = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": renk,
            "summary": f"Lumen AIOps - {siddet_tr} Anomali: {anomali.get('service')}",
            "sections": [
                {
                    "activityTitle": f"⚠️ {siddet_tr} ANOMALİ TESPİT EDİLDİ",
                    "activitySubtitle": f"Lumen AIOps • {anomali.get('service', '-')}",
                    "facts": [
                        {"name": "Servis", "value": anomali.get("service", "-")},
                        {"name": "Kanal", "value": anomali.get("channel_code", "-")},
                        {"name": "Anomali Türü", "value": anomali.get("anomaly_type", "-")},
                        {"name": "Şiddet", "value": siddet_tr},
                        {"name": "Özet", "value": anomali.get("summary", "-")},
                        {"name": "Hata Oranı", "value": f"%{(anomali.get('error_rate', 0) * 100):.1f}"},
                        {"name": "Ort. Yanıt Süresi", "value": f"{anomali.get('elapsed_mean', 0):.0f} ms"},
                        {"name": "İşlem Sayısı", "value": str(anomali.get("tx_count", 0))},
                    ],
                    "markdown": True
                }
            ]
        }

        async with httpx.AsyncClient(timeout=10) as client:
            yanit = await client.post(
                self.teams_webhook_url,
                json=mesaj,
                headers={"Content-Type": "application/json"}
            )
            if yanit.status_code == 200:
                logger.info(f"Teams bildirimi gonderildi: {anomali.get('service')}")
            else:
                logger.error(f"Teams bildirimi basarisiz: {yanit.status_code} {yanit.text}")

    async def _email_gonder(self, anomali: dict):
        severity = anomali.get("severity", "WARNING")
        siddet_tr = {"DISASTER": "KRİTİK", "HIGH": "YÜKSEK", "WARNING": "UYARI"}.get(severity, severity)

        konu = f"[Lumen AIOps] {siddet_tr} Anomali: {anomali.get('service', '-')} [{anomali.get('channel_code', '-')}]"

        html_govde = f"""
        <html><body style="font-family: Arial, sans-serif; color: #1e293b;">
        <div style="max-width:600px;margin:0 auto;border:1px solid #e2e8f0;border-radius:8px;overflow:hidden">
            <div style="background:{'#dc2626' if severity=='DISASTER' else '#ea580c' if severity=='HIGH' else '#ca8a04'};padding:16px 20px">
                <h2 style="color:white;margin:0">⚠️ {siddet_tr} Anomali Tespit Edildi</h2>
                <p style="color:rgba(255,255,255,0.85);margin:4px 0 0">Lumen AIOps Sistemi</p>
            </div>
            <div style="padding:20px">
                <table style="width:100%;border-collapse:collapse">
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b;width:140px">Servis</td>
                        <td style="padding:8px;font-weight:600">{anomali.get('service', '-')}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b">Kanal</td>
                        <td style="padding:8px">{anomali.get('channel_code', '-')}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b">Anomali Türü</td>
                        <td style="padding:8px">{anomali.get('anomaly_type', '-')}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b">Özet</td>
                        <td style="padding:8px">{anomali.get('summary', '-')}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b">Hata Oranı</td>
                        <td style="padding:8px">%{(anomali.get('error_rate', 0) * 100):.1f}</td>
                    </tr>
                    <tr style="border-bottom:1px solid #f1f5f9">
                        <td style="padding:8px;color:#64748b">Ort. Yanıt Süresi</td>
                        <td style="padding:8px">{anomali.get('elapsed_mean', 0):.0f} ms</td>
                    </tr>
                    <tr>
                        <td style="padding:8px;color:#64748b">İşlem Sayısı</td>
                        <td style="padding:8px">{anomali.get('tx_count', 0)}</td>
                    </tr>
                </table>
                <div style="margin-top:16px;padding:12px;background:#f8fafc;border-radius:6px;font-size:12px;color:#64748b">
                    Lumen AIOps Dashboard üzerinden anomali detaylarını inceleyebilir ve onaylayabilirsiniz.
                </div>
            </div>
        </div>
        </body></html>
        """

        await asyncio.get_event_loop().run_in_executor(
            None, self._smtp_gonder, konu, html_govde
        )

    def _smtp_gonder(self, konu: str, html_govde: str):
        mesaj = MIMEMultipart("alternative")
        mesaj["Subject"] = konu
        mesaj["From"] = self.smtp_from
        mesaj["To"] = ", ".join(self.smtp_to)
        mesaj.attach(MIMEText(html_govde, "html", "utf-8"))

        context = ssl.create_default_context()
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10) as server:
                server.ehlo()
                server.starttls(context=context)
                if self.smtp_user and self.smtp_password:
                    server.login(self.smtp_user, self.smtp_password)
                server.sendmail(self.smtp_from, self.smtp_to, mesaj.as_string())
            logger.info(f"E-posta bildirimi gonderildi: {self.smtp_to}")
        except Exception as e:
            logger.error(f"E-posta hatasi: {e}")
            raise


notification_service = NotificationService()
