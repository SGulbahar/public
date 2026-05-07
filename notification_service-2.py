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
import httpx

logger = logging.getLogger(__name__)

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
            f"smtp={'var' if self.smtp_host else 'yok'}, "
            f"alicilar={len(self.smtp_to)}"
        )

    def _siddet_sirasi(self, severity: str) -> int:
        return {"WARNING": 1, "HIGH": 2, "DISASTER": 3}.get(severity, 0)

    def _cooldown_kontrol(self, anahtar: str) -> bool:
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
        siddet_tr = {"DISASTER": "KRITIK", "HIGH": "YUKSEK", "WARNING": "UYARI"}.get(severity, severity)
        mesaj = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "themeColor": renk,
            "summary": f"Lumen AIOps - {siddet_tr} Anomali: {anomali.get('service')}",
            "sections": [
                {
                    "activityTitle": f"Lumen AIOps - {siddet_tr} ANOMALi",
                    "activitySubtitle": anomali.get("service", "-"),
                    "facts": [
                        {"name": "Servis", "value": anomali.get("service", "-")},
                        {"name": "Kanal", "value": anomali.get("channel_code", "-")},
                        {"name": "Anomali Turu", "value": anomali.get("anomaly_type", "-")},
                        {"name": "Siddet", "value": siddet_tr},
                        {"name": "Ozet", "value": anomali.get("summary", "-")},
                        {"name": "Hata Orani", "value": f"%{(anomali.get('error_rate', 0) * 100):.1f}"},
                        {"name": "Ort. Yanit Suresi", "value": f"{anomali.get('elapsed_mean', 0):.0f} ms"},
                        {"name": "Islem Sayisi", "value": str(anomali.get("tx_count", 0))},
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
        siddet_tr = {"DISASTER": "KRITIK", "HIGH": "YUKSEK", "WARNING": "UYARI"}.get(severity, severity)
        konu = f"[Lumen AIOps] {siddet_tr} Anomali: {anomali.get('service', '-')} [{anomali.get('channel_code', '-')}]"

        error_rate_str = "{:.1f}".format(anomali.get('error_rate', 0) * 100)
        elapsed_str = "{:.0f}".format(anomali.get('elapsed_mean', 0))

        # CSS icerisindeki { } karakterleri {{ }} olarak yazilmali (f-string degil)
        html_govde = """<html lang="tr">
<head>
<meta charset="utf-8">
<title>Lumen AIOps Bildirim</title>
<xml><o:OfficeDocumentSettings xmlns:o="urn:schemas-microsoft-com:office:office">
<o:AllowPNG/><o:PixelsPerInch>96</o:PixelsPerInch>
</o:OfficeDocumentSettings></xml>
<style>
table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse}}
img{{-ms-interpolation-mode:bicubic;border:0}}
.cell{{padding:6px 8px;font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif;
border-top:1px solid transparent;mso-border-top-alt:1px solid transparent;
border-bottom:1px solid transparent;mso-border-bottom-alt:1px solid transparent;color:#111827}}
.label{{color:#334155;background:#fafbfc}}
</style>
</head>
<body style="margin:0;background:#fffefee7;">
<table role="presentation" width="100%"><tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="540" style="background:#fff;border:1px solid #e5e7eb;table-layout:fixed;">
<tr><td style="padding:20px 20px 8px;text-align:center;background:#f6f7ff;">
<a><img src="https://www.fibabanka.com.tr/Dosyalar/Mailing/20191024-fibabanka-duyuru/_i/figure_01.jpg" alt="Fibabanka" width="520" style="display:block;margin:0 auto;width:100%;max-width:520px"></a>
</td></tr>
<tr><td style="padding:12px 20px 6px">
<table role="presentation" width="100%">
<tr>
  <td class="cell label" width="38%" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">Servis</td>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">{service}</td>
</tr>
<tr>
  <td class="cell">Kanal</td>
  <td class="cell">{channel_code}</td>
</tr>
<tr>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">Anomali T&#252;r&#252;</td>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">{anomaly_type}</td>
</tr>
<tr>
  <td class="cell">&#214;zet</td>
  <td class="cell">{summary}</td>
</tr>
<tr>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">Hata Oran&#305;</td>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">%{error_rate}</td>
</tr>
<tr>
  <td class="cell">Ortalama Yan&#305;t S&#252;resi</td>
  <td class="cell">{elapsed_mean} ms</td>
</tr>
<tr>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">&#304;&#351;lem Say&#305;s&#305;</td>
  <td class="cell label" style="padding:6px 8px;color:#334155;font-size:14px;line-height:1.4;background:#f6f7ff;">{tx_count}</td>
</tr>
</table>
</td></tr>
<tr><td align="center" style="padding:15px 21px 21px">
<v:roundrect xmlns:v="urn:schemas-microsoft-com:vml" xmlns:w="urn:schemas-microsoft-com:office:word"
  href="https://lumenadress/" style="height:36px;width:220px;v-text-anchor:middle"
  arcsize="10%" stroke="f" fillcolor="#84cc16">
  <w:anchorlock/>
  <center style="color:#fff;font:600 13px Arial,sans-serif">Lumen AIOps Dashboard Detaylar&#305;</center>
</v:roundrect>
</td></tr>
</table>
</td></tr></table>
</body>
</html>""".format(
            service=anomali.get('service', '-'),
            channel_code=anomali.get('channel_code', '-'),
            anomaly_type=anomali.get('anomaly_type', '-'),
            summary=anomali.get('summary', '-'),
            error_rate=error_rate_str,
            elapsed_mean=elapsed_str,
            tx_count=anomali.get('tx_count', 0),
        )

        await asyncio.get_event_loop().run_in_executor(
            None, self._smtp_gonder, konu, html_govde
        )

    def _smtp_gonder(self, konu: str, html_govde: str):
        mesaj = MIMEMultipart("alternative")
        mesaj["Subject"] = konu
        mesaj["From"] = self.smtp_from
        mesaj["To"] = ", ".join(self.smtp_to)
        mesaj.attach(MIMEText(html_govde, "html", "utf-8"))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE
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
