import csv
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy import text
from app.database import AsyncSessionLocal, ErrorCode

logger = logging.getLogger(__name__)
DEFAULT_CSV_PATH = Path("/app/config/error_codes.csv")


class ErrorCodeService:
    def __init__(self):
        self._cache = {}
        self._loaded = False

    async def load(self, csv_path=DEFAULT_CSV_PATH):
        if not csv_path.exists():
            logger.warning(f"error_codes.csv bulunamadi: {csv_path}")
            return 0
        records = self._parse_csv(csv_path)
        if not records:
            logger.warning("error_codes.csv bos veya gecersiz format")
            return 0
        await self._upsert_db(records)
        self._populate_cache(records)
        self._loaded = True
        sys_count = sum(1 for r in records if r['category'] == 'SYS')
        biz_count = sum(1 for r in records if r['category'] == 'BIZ')
        logger.info(f"Hata kodlari yuklendi: {len(records)} kayit ({sys_count} SYS, {biz_count} BIZ)")
        return len(records)

    async def reload(self, csv_path=DEFAULT_CSV_PATH):
        self._cache.clear()
        self._loaded = False
        return await self.load(csv_path)

    def describe(self, code):
        entry = self._cache.get(code)
        return entry['description'] if entry else f"Kod: {code}"

    def category(self, code):
        entry = self._cache.get(code)
        if entry:
            return entry['category']
        if code == 0:
            return "SUCCESS"
        elif code < 7500:
            return "SYS"
        else:
            return "BIZ"

    def enrich_summary(self, result_code, count, service):
        if result_code == 0:
            return f"{service} - {count} basarili islem"
        cat = self.category(result_code)
        desc = self.describe(result_code)
        return f"{service} - {count}x {cat}: {desc} ({result_code})"

    def is_loaded(self):
        return self._loaded

    def cache_size(self):
        return len(self._cache)

    @staticmethod
    def _parse_csv(csv_path):
        records = []
        try:
            with open(csv_path, 'r', encoding='utf-8', errors='replace') as f:
                reader = csv.reader(f, quotechar='"', delimiter=',')
                for i, row in enumerate(reader):
                    if i == 0:
                        continue
                    if not row or len(row) < 2:
                        continue
                    try:
                        code_str = row[0].strip().strip('"').strip()
                        if not code_str or not code_str.isdigit():
                            continue
                        code = int(code_str)
                        desc = row[1].strip().strip('"').strip()
                        if not desc:
                            continue
                        if code == 0:
                            cat = "SUCCESS"
                        elif code < 7500:
                            cat = "SYS"
                        else:
                            cat = "BIZ"
                        records.append({
                            'result_code': code,
                            'description': desc,
                            'category': cat,
                        })
                    except Exception as e:
                        logger.debug(f"Satir {i} atildi: {e}")
                        continue
        except Exception as e:
            logger.error(f"CSV parse hatasi: {e}")
        return records

    async def _upsert_db(self, records):
        async with AsyncSessionLocal() as db:
            try:
                for r in records:
                    await db.execute(
                        text("""
                            INSERT INTO error_codes (result_code, description, category)
                            VALUES (:code, :desc, :cat)
                            ON CONFLICT (result_code) DO UPDATE
                            SET description = EXCLUDED.description,
                                category = EXCLUDED.category,
                                loaded_at = NOW()
                        """),
                        {'code': r['result_code'], 'desc': r['description'], 'cat': r['category']}
                    )
                await db.commit()
            except Exception as e:
                await db.rollback()
                logger.error(f"DB upsert hatasi: {e}")

    def _populate_cache(self, records):
        for r in records:
            self._cache[r['result_code']] = {
                'description': r['description'],
                'category': r['category'],
            }


error_code_service = ErrorCodeService()
