"""
LLM RCA (Kok Neden Analizi) Modulu
/v1/chat/completions endpoint'i ile OpenAI uyumlu API
"""
import logging
import httpx
from typing import Optional

logger = logging.getLogger(__name__)


class LLMRCAService:
    def __init__(self):
        self.enabled = False
        self.rca_enabled = True
        self.base_url = ""
        self.api_key = ""
        self.model = "openai/gpt-oss-120b"
        self.timeout = 30
        self.max_tokens = 500
        self.min_severity = "HIGH"
        logger.info("LLM RCA servisi baslatildi")

    def ayarlari_yukle(self, settings: dict):
        self.enabled = settings.get("llm_enabled", "false") == "true"
        self.rca_enabled = settings.get("llm_rca_enabled", "true") == "true"
        self.base_url = settings.get("llm_base_url", "").rstrip("/")
        self.api_key = settings.get("llm_api_key", "")
        self.model = settings.get("llm_model", "openai/gpt-oss-120b")
        self.timeout = int(settings.get("llm_timeout", 30))
        self.max_tokens = int(settings.get("llm_max_tokens", 500))
        self.min_severity = settings.get("llm_min_severity", "HIGH")
        logger.info(
            f"LLM ayarlari yuklendi: enabled={self.enabled}, "
            f"model={self.model}, base_url={'var' if self.base_url else 'yok'}"
        )

    def _siddet_sirasi(self, severity: str) -> int:
        return {"WARNING": 1, "HIGH": 2, "DISASTER": 3}.get(severity, 0)

    def _prompt_olustur(self, anomali: dict, rag_context: str = None) -> str:
        severity_tr = {"DISASTER": "KRİTİK", "HIGH": "YÜKSEK", "WARNING": "UYARI"}.get(
            anomali.get("severity", ""), anomali.get("severity", "")
        )
        category_tr = {
            "SYS": "Sistem Hatası",
            "BIZ": "İş Hatası",
            "PERFORMANCE": "Performans Anomalisi"
        }.get(anomali.get("result_category", ""), anomali.get("result_category", ""))

        rd = anomali.get("result_distribution", {})
        rd_str = ""
        if rd:
            rd_parts = []
            for rc, cnt in sorted(rd.items(), key=lambda x: -x[1]):
                label = "Başarılı" if str(rc) == "0" else ("SYS" if int(rc) < 7500 else "BIZ")
                rd_parts.append(f"{rc}({label}):{cnt} adet")
            rd_str = ", ".join(rd_parts)

        rag_bolum = ""
        if rag_context:
            rag_bolum = f"""

Gecmis Veri ve Baglam:
{rag_context}"""

        prompt = f"""Bankacılık AIOps sistemi olarak görev yapıyorsun. Aşağıdaki anomali için spesifik kök neden analizi yap.

=== MEVCUT ANOMALİ ===
Servis: {anomali.get('service', '-')}
Kanal: {anomali.get('channel_code', '-')}
Şiddet: {severity_tr} | Kategori: {category_tr}
Özet: {anomali.get('summary', '-')}
Hata Oranı: %{(anomali.get('error_rate', 0) * 100):.1f} | Yanıt Süresi: {anomali.get('elapsed_mean', 0):.0f}ms | İşlem: {anomali.get('tx_count', 0)}
{f'Result Dağılımı: {rd_str}' if rd_str else ''}{rag_bolum}

=== GÖREV ===
Yukarıdaki verilere dayanarak:

ÖNEMLİ: Analiz sırası şu şekilde olmalı:
- Önce servis adı ve anomali özeti neyden bahsediyorsa onu dikkate al
- Hata kodu açıklaması yalnızca referans — servis bağlamıyla çelişiyorsa özeti esas al
- Geçmiş veri varsa onu kullan, yoksa mevcut veriye dayan

1. **Kök Neden** (1-2 cümle): Servis adı, anomali özeti ve geçmiş pattern'i birlikte değerlendirerek spesifik neden yaz.

2. **Tekrarlayan mı?** (1 cümle): Geçmiş veriye göre yeni mi yoksa bilinen bir pattern mi?

3. **Aksiyon** (2 madde max): Hangi ekip, ne yapmalı — somut ve uygulanabilir.

Yanıt kısa, teknik ve Türkçe olsun."""

        return prompt

    async def rca_analiz(self, anomali: dict, rag_context: str = None) -> Optional[str]:
        if not self.enabled or not self.rca_enabled:
            return None

        severity = anomali.get("severity", "WARNING")
        if self._siddet_sirasi(severity) < self._siddet_sirasi(self.min_severity):
            return None

        if not self.base_url:
            logger.warning("LLM base_url tanimli degil")
            return None

        try:
            prompt = self._prompt_olustur(anomali, rag_context=rag_context)
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": "Sen bir bankacılık sistemleri uzmanısın. Anomali analizlerini kısa, teknik ve Türkçe yapıyorsun."
                    },
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": 0.3,
            }

            async with httpx.AsyncClient(timeout=self.timeout, verify=False) as client:
                yanit = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers
                )

            if yanit.status_code == 200:
                data = yanit.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                if content:
                    logger.info(f"LLM RCA analizi tamamlandi: {anomali.get('service')}")
                    return content.strip()
            else:
                logger.error(f"LLM API hatasi: {yanit.status_code} {yanit.text[:200]}")
                return None

        except Exception as e:
            logger.error(f"LLM RCA hatasi: {e}")
            return None

    async def baglanti_test(self) -> dict:
        if not self.base_url:
            return {"status": "error", "message": "Base URL tanimli degil"}
        try:
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            payload = {
                "model": self.model,
                "messages": [{"role": "user", "content": "Merhaba, baglanti testi."}],
                "max_tokens": 10,
                "temperature": 0.1,
            }

            async with httpx.AsyncClient(timeout=10, verify=False) as client:
                yanit = await client.post(
                    f"{self.base_url}/v1/chat/completions",
                    json=payload,
                    headers=headers
                )

            if yanit.status_code == 200:
                return {"status": "ok", "model": self.model, "base_url": self.base_url}
            else:
                return {"status": "error", "message": f"HTTP {yanit.status_code}: {yanit.text[:200]}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}


llm_rca_service = LLMRCAService()
