"""
CatBoost Anomali Tespiti - Egitim Scripti
=========================================
baseline_stats tablosundan normal davranis ogrenilir.
Etiket gerektirmez — One-Class Classification yaklasimi.

Calistirma:
  python train_catboost.py --dsn postgresql://... --output /app/data/models/catboost
  python train_catboost.py --dsn postgresql://... --dry-run  # Veri analizi yapar, egitmez

Gereksinimler:
  pip install catboost scikit-learn asyncpg pandas numpy
"""
import argparse
import asyncio
import json
import logging
import os
import pickle
from datetime import datetime
from pathlib import Path

import asyncpg
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, roc_auc_score
from sklearn.preprocessing import LabelEncoder

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


# ── Konfigürasyon ─────────────────────────────────────────
CONFIG = {
    # Minimum ornek sayisi (az ornekli servis/kanal atlenir)
    "min_sample_count": 50,

    # Normal veri esigi — bu sample_count uzerindeki kayitlar guclu normal
    "strong_normal_threshold": 500,

    # Anomali ornegi uretmek icin sapma katsayisi
    # mean + N*std degerini anomali olarak isaretler
    "anomaly_sigma": 3.5,

    # CatBoost parametreleri
    "catboost_params": {
        "iterations": 500,
        "learning_rate": 0.05,
        "depth": 6,
        "loss_function": "Logloss",
        "eval_metric": "AUC",
        "random_seed": 42,
        "verbose": 100,
        "early_stopping_rounds": 50,
        "class_weights": [1, 10],  # Anomali azinlik sinifi agirlandirildi
    },

    # Feature listesi
    "cat_features": ["service", "channel_code"],
    "num_features": [
        "mean_error", "std_error", "mean_elapsed", "std_elapsed",
        "sample_count_log", "hour_bucket", "weekday",
        "error_cv",        # Coefficient of variation — varyasyon katsayisi
        "elapsed_cv",
        "hour_sin", "hour_cos",  # Sirkular saat encoding
        "day_sin", "day_cos",    # Sirkular gun encoding
    ],
}


async def veri_cek(dsn: str) -> pd.DataFrame:
    """baseline_stats tablosundan normal davranis verisini ceker."""
    logger.info("DB'den baseline verisi cekiliyor...")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("""
            SELECT
                service,
                channel_code,
                COALESCE(weekday, 0) as weekday,
                COALESCE(hour_bucket, 0) as hour_bucket,
                COALESCE(mean_error, 0) as mean_error,
                COALESCE(std_error, 0) as std_error,
                COALESCE(mean_elapsed, 0) as mean_elapsed,
                COALESCE(std_elapsed, 0) as std_elapsed,
                COALESCE(sample_count, 0) as sample_count
            FROM baseline_stats
            WHERE sample_count >= $1
              AND mean_elapsed > 0
        """, CONFIG["min_sample_count"])

        df = pd.DataFrame([dict(r) for r in rows])
        logger.info(f"Cekilen kayit: {len(df)} satir, {df['service'].nunique()} servis")
        return df
    finally:
        await conn.close()


async def anomali_ornekleri_cek(dsn: str) -> pd.DataFrame:
    """
    anomaly_events tablosundan gercek anomali orneklerini ceker.
    Onaylanan anomaliler + false positive degiller.
    """
    logger.info("Gercek anomali ornekleri cekiliyor...")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch("""
            SELECT
                service,
                channel_code,
                EXTRACT(DOW FROM detected_at)::int as weekday,
                EXTRACT(HOUR FROM detected_at AT TIME ZONE 'Europe/Istanbul')::int as hour_bucket,
                COALESCE(error_rate, 0) as mean_error,
                0.1 as std_error,
                COALESCE(elapsed_mean, 0) as mean_elapsed,
                50.0 as std_elapsed,
                COALESCE(tx_count, 30) as sample_count
            FROM anomaly_events
            WHERE is_false_positive = false
              AND detected_at >= NOW() - INTERVAL '90 days'
        """)

        df = pd.DataFrame([dict(r) for r in rows])
        logger.info(f"Gercek anomali ornegi: {len(df)} satir")
        return df
    finally:
        await conn.close()


def feature_engineering(df: pd.DataFrame) -> pd.DataFrame:
    """Feature engineering uygular."""
    df = df.copy()

    # Log scale sample count
    df["sample_count_log"] = np.log1p(df["sample_count"])

    # Coefficient of variation (std/mean) — normalize edilmis varyasyon
    df["error_cv"] = np.where(
        df["mean_error"] > 0,
        df["std_error"] / (df["mean_error"] + 1e-8),
        0
    )
    df["elapsed_cv"] = np.where(
        df["mean_elapsed"] > 0,
        df["std_elapsed"] / (df["mean_elapsed"] + 1e-8),
        0
    )

    # Sirkular encoding — saat ve gun icin
    df["hour_sin"] = np.sin(2 * np.pi * df["hour_bucket"] / 24)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour_bucket"] / 24)
    df["day_sin"] = np.sin(2 * np.pi * df["weekday"] / 7)
    df["day_cos"] = np.cos(2 * np.pi * df["weekday"] / 7)

    # NaN temizle
    df = df.fillna(0)

    return df


def sentetik_anomali_uret(df_normal: pd.DataFrame, oran: float = 0.3) -> pd.DataFrame:
    """
    Normal veri uzerinden sentetik anomali ornekleri uretir.
    Gercek anomali ornegi yoksa veya azsa kullanilir.

    Yontem: Her servis/kanal icin mean + N*std degerini anomali olarak isaretle.
    """
    logger.info("Sentetik anomali ornekleri uretiliyor...")
    anomaliler = []

    sigma = CONFIG["anomaly_sigma"]

    for (service, channel), grp in df_normal.groupby(["service", "channel_code"]):
        if len(grp) < 3:
            continue

        # Yuksek hata oranli anomali
        anomali = grp.sample(1).copy()
        anomali["mean_error"] = min(1.0, grp["mean_error"].mean() + sigma * grp["std_error"].mean() + 0.3)
        anomali["std_error"] = grp["std_error"].mean() * 0.5
        anomaliler.append(anomali)

        # Yuksek elapsed anomali
        anomali2 = grp.sample(1).copy()
        anomali2["mean_elapsed"] = grp["mean_elapsed"].mean() + sigma * grp["std_elapsed"].mean() + 1000
        anomali2["std_elapsed"] = grp["std_elapsed"].mean() * 0.5
        anomaliler.append(anomali2)

    if not anomaliler:
        return pd.DataFrame()

    df_anomali = pd.concat(anomaliler, ignore_index=True)
    # Oranlama — cok fazla anomali olmasin
    n_hedef = int(len(df_normal) * oran)
    if len(df_anomali) > n_hedef:
        df_anomali = df_anomali.sample(n_hedef, random_state=42)

    logger.info(f"Sentetik anomali: {len(df_anomali)} ornek")
    return df_anomali


def veri_hazirla(df_normal: pd.DataFrame, df_anomali: pd.DataFrame) -> tuple:
    """Egitim verisini hazirlar."""
    df_normal = feature_engineering(df_normal)
    df_anomali = feature_engineering(df_anomali)

    df_normal["label"] = 0
    df_anomali["label"] = 1

    df_all = pd.concat([df_normal, df_anomali], ignore_index=True)
    df_all = df_all.sample(frac=1, random_state=42).reset_index(drop=True)

    all_features = CONFIG["cat_features"] + CONFIG["num_features"]
    X = df_all[all_features]
    y = df_all["label"]

    logger.info(f"Toplam egitim verisi: {len(df_all)} ornek")
    logger.info(f"  Normal: {(y==0).sum()} ({(y==0).mean()*100:.1f}%)")
    logger.info(f"  Anomali: {(y==1).sum()} ({(y==1).mean()*100:.1f}%)")

    return X, y


def model_egit(X: pd.DataFrame, y: pd.Series) -> CatBoostClassifier:
    """CatBoost modeli egitir."""
    logger.info("Model egitimi basliyor...")

    X_train, X_val, y_train, y_val = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    # Kategorik feature indexleri
    cat_feature_indices = [X.columns.get_loc(f) for f in CONFIG["cat_features"]]

    model = CatBoostClassifier(**CONFIG["catboost_params"])
    model.fit(
        X_train, y_train,
        cat_features=cat_feature_indices,
        eval_set=(X_val, y_val),
        use_best_model=True,
    )

    # Degerlendirme
    y_pred = model.predict(X_val)
    y_prob = model.predict_proba(X_val)[:, 1]

    logger.info("\nValidation Sonuclari:")
    logger.info(classification_report(y_val, y_pred, target_names=["Normal", "Anomali"]))
    try:
        auc = roc_auc_score(y_val, y_prob)
        logger.info(f"ROC AUC: {auc:.4f}")
    except Exception:
        pass

    # Feature importance
    fi = pd.Series(
        model.get_feature_importance(),
        index=CONFIG["cat_features"] + CONFIG["num_features"]
    ).sort_values(ascending=False)
    logger.info(f"\nTop 10 Feature Importance:\n{fi.head(10).to_string()}")

    return model


def model_kaydet(model: CatBoostClassifier, output_dir: str, meta: dict):
    """Modeli ve metadata'yi kaydeder."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # CatBoost native format
    model_path = os.path.join(output_dir, "catboost_anomaly.cbm")
    model.save_model(model_path)

    # Pickle backup
    pkl_path = os.path.join(output_dir, "catboost_anomaly.pkl")
    with open(pkl_path, "wb") as f:
        pickle.dump(model, f)

    # Metadata
    meta["saved_at"] = datetime.utcnow().isoformat()
    meta["model_path"] = model_path
    meta["features"] = CONFIG["cat_features"] + CONFIG["num_features"]
    meta["cat_features"] = CONFIG["cat_features"]
    meta_path = os.path.join(output_dir, "catboost_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2, ensure_ascii=False)

    logger.info(f"Model kaydedildi: {model_path}")
    logger.info(f"Metadata: {meta_path}")
    return model_path


async def main():
    parser = argparse.ArgumentParser(description="CatBoost Anomali Tespiti Egitim Scripti")
    parser.add_argument("--dsn", required=True, help="PostgreSQL DSN (postgresql://user:pass@host:port/db)")
    parser.add_argument("--output", default="/app/data/models/catboost", help="Model cikti dizini")
    parser.add_argument("--dry-run", action="store_true", help="Sadece veri analizi yap, egitme")
    parser.add_argument("--use-real-anomalies", action="store_true", help="anomaly_events tablosundan gercek anomali kullan")
    parser.add_argument("--anomaly-sigma", type=float, default=3.5, help="Sentetik anomali sigma katsayisi")
    args = parser.parse_args()

    CONFIG["anomaly_sigma"] = args.anomaly_sigma

    logger.info("=" * 60)
    logger.info("Lumen AIOps — CatBoost Egitim Scripti")
    logger.info("=" * 60)

    # Veri cek
    df_normal = await veri_cek(args.dsn)

    if df_normal.empty:
        logger.error("baseline_stats tablosunda yeterli veri yok!")
        return

    if args.dry_run:
        logger.info("\n=== DRY RUN — Veri Analizi ===")
        logger.info(f"Toplam satir: {len(df_normal)}")
        logger.info(f"Benzersiz servis: {df_normal['service'].nunique()}")
        logger.info(f"Benzersiz kanal: {df_normal['channel_code'].nunique()}")
        logger.info(f"Mean error istatistikleri:\n{df_normal['mean_error'].describe()}")
        logger.info(f"Mean elapsed istatistikleri:\n{df_normal['mean_elapsed'].describe()}")
        logger.info(f"Sample count dagilimi:\n{df_normal['sample_count'].describe()}")
        logger.info("\nEn fazla ornege sahip servisler:")
        top = df_normal.groupby("service")["sample_count"].sum().sort_values(ascending=False).head(10)
        logger.info(top.to_string())
        return

    # Anomali ornekleri hazirla
    if args.use_real_anomalies:
        df_anomali = await anomali_ornekleri_cek(args.dsn)
        if len(df_anomali) < 100:
            logger.warning(f"Gercek anomali az ({len(df_anomali)}), sentetik ile tamamlaniyor...")
            df_sentetik = sentetik_anomali_uret(df_normal, oran=0.2)
            df_anomali = pd.concat([df_anomali, df_sentetik], ignore_index=True)
    else:
        df_anomali = sentetik_anomali_uret(df_normal, oran=0.3)

    if df_anomali.empty:
        logger.error("Anomali ornegi uretmek basarisiz!")
        return

    # Egitim verisi hazirla
    X, y = veri_hazirla(df_normal, df_anomali)

    # Model egit
    model = model_egit(X, y)

    # Kaydet
    meta = {
        "training_date": datetime.utcnow().isoformat(),
        "normal_samples": int((y == 0).sum()),
        "anomaly_samples": int((y == 1).sum()),
        "total_services": df_normal["service"].nunique(),
        "anomaly_sigma": CONFIG["anomaly_sigma"],
        "use_real_anomalies": args.use_real_anomalies,
    }
    model_kaydet(model, args.output, meta)

    logger.info("\nEgitim tamamlandi!")
    logger.info(f"Modeli engine'e yuklemek icin engine'i yeniden baslatiniz.")


if __name__ == "__main__":
    asyncio.run(main())
