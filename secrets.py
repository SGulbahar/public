"""
Secret Manager
==============
Entegrasyon şifrelerini Fernet ile şifreleyip DB'de saklar.

Kullanim:
    from app.security.secrets import secret_manager
    
    # Sifre kaydet
    await secret_manager.secrets_kaydet('zabbix', {'password': 'abc123'})
    
    # Sifre oku
    secrets = await secret_manager.secrets_oku('zabbix')
    password = secrets.get('password')
"""
import json
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


class SecretManager:
    def __init__(self):
        self._fernet = None
        self._init_fernet()

    def _init_fernet(self):
        """Fernet instance olusturur."""
        try:
            from cryptography.fernet import Fernet
            key = os.environ.get("LUMEN_SECRET_KEY", "")
            if not key:
                logger.warning("LUMEN_SECRET_KEY tanimlanmamis — sifreli alanlar calismiyor")
                return
            self._fernet = Fernet(key.encode() if isinstance(key, str) else key)
            logger.info("Secret Manager hazir")
        except Exception as e:
            logger.error(f"Secret Manager init hatasi: {e}")

    def sifrele(self, deger: str) -> str:
        """String degeri sifreler, base64 string dondurur."""
        if not self._fernet or not deger:
            return deger
        try:
            return self._fernet.encrypt(deger.encode()).decode()
        except Exception as e:
            logger.error(f"Sifreleme hatasi: {e}")
            return deger

    def coz(self, sifrelenmis: str) -> str:
        """Sifreli string'i cozer."""
        if not self._fernet or not sifrelenmis:
            return sifrelenmis
        try:
            return self._fernet.decrypt(sifrelenmis.encode()).decode()
        except Exception:
            # Sifreli degil, direkt dondur
            return sifrelenmis

    def secrets_sifrele(self, secrets: dict) -> dict:
        """Dict icindeki tum degerleri sifreler."""
        return {k: self.sifrele(str(v)) if v else v for k, v in secrets.items()}

    def secrets_coz(self, secrets: dict) -> dict:
        """Dict icindeki tum sifrelenmis degerleri cozer."""
        return {k: self.coz(str(v)) if v else v for k, v in secrets.items()}


# Singleton
secret_manager = SecretManager()
